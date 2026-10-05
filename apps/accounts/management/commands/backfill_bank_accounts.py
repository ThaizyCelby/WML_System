"""
Backfill BankAccount rows from existing DebitInstruction records.

Run AFTER schema migrations are applied:

    python manage.py backfill_bank_accounts --dry-run
    python manage.py backfill_bank_accounts

Idempotent — safe to run twice.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone


class Command(BaseCommand):
    help = (
        'Create BankAccount rows from inline bank details on existing '
        'DebitInstruction records and link them via the new FK.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report changes without writing.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        from apps.payments.models import DebitInstruction
        from apps.accounts.models import BankAccount

        dry_run = options['dry_run']

        self.stdout.write(self.style.HTTP_INFO(
            f'Backfilling bank accounts{" (dry run)" if dry_run else ""}...'
        ))

        created = 0
        linked = 0
        skipped = 0

        for instruction in DebitInstruction.objects.select_related('loan').iterator():
            if instruction.bank_account_id:
                skipped += 1
                continue

            client_id = instruction.loan.client_id if instruction.loan else None
            if not client_id:
                skipped += 1
                continue

            last4 = (instruction.account_number_last4 or '')[:4]

            account = None
            if last4:
                account = BankAccount.objects.filter(
                    client_id=client_id,
                    account_number_last4=last4,
                    bank_name=instruction.bank_name or '',
                ).first()

            if account is None:
                if not dry_run:
                    account = BankAccount.objects.create(
                        client_id=client_id,
                        bank_name=instruction.bank_name or 'Unknown',
                        account_type=instruction.account_type or 'cheque',
                        account_holder_name=instruction.account_holder_name or '',
                        # We cannot reconstruct the plaintext account number
                        # (only a hash exists on the mandate). Leave blank; the
                        # mandate still holds the encrypted copy.
                        account_number='',
                        account_number_last4=last4,
                        account_number_index='',
                        branch_code=instruction.branch_code or '',
                        source='mandate_created',
                        is_primary=False,
                        first_seen_at=instruction.created_at or timezone.now(),
                        last_seen_at=instruction.updated_at or timezone.now(),
                    )
                created += 1

            if not dry_run and account is not None:
                instruction.bank_account_id = account.id
                instruction.save(update_fields=['bank_account', 'updated_at'])
            linked += 1

        style = self.style.SUCCESS if not dry_run else self.style.WARNING
        verb = 'Would create' if dry_run else 'Created'
        self.stdout.write(style(
            f'Done. {verb} {created}, linked {linked}, skipped {skipped}.'
        ))