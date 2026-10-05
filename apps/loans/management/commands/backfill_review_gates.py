"""
One-time backfill: mark review-gate flags on applications that already
advanced past the corresponding gate before gate enforcement existed.

Run once:

    python manage.py backfill_review_gates

Safe to run twice — it only writes when a flag would change.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.loans.models import LoanApplication


# Ordering of statuses from earliest to latest. Used to determine whether
# an application has already passed a given gate.
STATUS_ORDER = [
    'draft',
    'submitted',
    'document_review',
    'kyc_review',
    'affordability_review',
    'credit_review',
    'approved',
    'contract_pending',
    'contract_accepted',
    'disbursement_pending',
    'active',
    'paid',
    'overdue',
    'defaulted',
    'restructured',
]

# Gates: enter-gate-status → (flag_field, previous-status-that-must-be-passed)
GATE_DEFINITIONS = [
    # The documents gate is entered when we reach kyc_review,
    # so any status at or past kyc_review has passed the document gate.
    ('kyc_review', 'documents_reviewed'),

    # The transactions gate is entered when we reach credit_review,
    # so any status at or past credit_review has passed it.
    ('credit_review', 'transactions_reviewed'),

    # The contract gate is entered when we reach disbursement_pending,
    # so any status at or past disbursement_pending has passed it.
    ('disbursement_pending', 'contract_verified_by_admin'),
]


def _status_index(status: str) -> int:
    try:
        return STATUS_ORDER.index(status)
    except ValueError:
        return -1


class Command(BaseCommand):
    help = (
        'Set review-gate flags on applications that already advanced past '
        'the corresponding gate. Idempotent.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would be changed without writing.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options['dry_run']

        self.stdout.write(self.style.HTTP_INFO(
            f'Backfilling review gates{" (dry run)" if dry_run else ""}...'
        ))

        total = 0
        touched = 0

        for application in LoanApplication.objects.all().iterator():
            total += 1
            current_idx = _status_index(application.status)

            updates = []
            for gate_status, flag_field in GATE_DEFINITIONS:
                gate_idx = _status_index(gate_status)
                if current_idx >= gate_idx and not getattr(application, flag_field):
                    setattr(application, flag_field, True)
                    updates.append(flag_field)

            if not updates:
                continue

            # Fill in the ancillary fields for the contract gate
            extra = []
            if 'contract_verified_by_admin' in updates:
                if not application.contract_verified_at:
                    application.contract_verified_at = timezone.now()
                    extra.append('contract_verified_at')

            updates.extend(extra)
            updates.append('updated_at')

            if not dry_run:
                application.save(update_fields=updates)
            touched += 1

            self.stdout.write(
                f'  {application.id} [{application.status}] '
                f'→ set {", ".join(updates)}'
            )

        style = self.style.SUCCESS if not dry_run else self.style.WARNING
        self.stdout.write(style(
            f'Done. Scanned {total} applications. '
            f'{touched} would be{" " if dry_run else " were "}updated.'
            if dry_run else
            f'Done. Scanned {total} applications. {touched} updated.'
        ))