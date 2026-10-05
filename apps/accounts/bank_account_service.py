"""Service layer for client bank accounts."""
import logging

from django.db import transaction
from django.utils import timezone

from apps.audit.services import AuditService
from core.crypto import blind_index

from .models import BankAccount

logger = logging.getLogger('apps.accounts')


class BankAccountService:

    @staticmethod
    def _normalize(account_number) -> str:
        return ''.join(c for c in str(account_number or '') if c.isdigit())

    @staticmethod
    @transaction.atomic
    def add_account(
        client,
        *,
        bank_name: str,
        account_holder_name: str,
        account_number: str,
        account_type: str = 'cheque',
        branch_code: str = '',
        source: str = 'client_entered',
        consent_reference: str = '',
        actor=None,
        ip_address=None,
    ):
        """
        Create a BankAccount, or return the existing one if the same
        account number is already on file for this client.

        Returns (account, created: bool).
        """
        digits = BankAccountService._normalize(account_number)
        if not digits:
            raise ValueError('Account number is required.')
        if len(digits) < 6:
            raise ValueError('Account number looks too short.')
        if not bank_name:
            raise ValueError('Bank name is required.')
        if not account_holder_name:
            raise ValueError('Account holder name is required.')

        idx = blind_index(digits)
        existing = BankAccount.objects.filter(
            client=client, account_number_index=idx,
        ).first()

        if existing:
            existing.last_seen_at = timezone.now()
            existing.save(update_fields=['last_seen_at', 'updated_at'])
            logger.info('BankAccount re-used: %s', existing.id)
            return existing, False

        is_first = not BankAccount.objects.filter(client=client).exists()

        account = BankAccount.objects.create(
            client=client,
            bank_name=bank_name.strip()[:100],
            account_type=account_type or 'cheque',
            account_holder_name=account_holder_name.strip()[:200],
            account_number=digits,
            branch_code=(branch_code or '').strip()[:20],
            source=source,
            consent_reference=(consent_reference or '')[:255],
            is_primary=is_first,
            first_seen_at=timezone.now(),
            last_seen_at=timezone.now(),
        )

        AuditService.record(
            actor=actor or client,
            action='bank_account_created',
            object_type='bank_account',
            object_id=str(account.id),
            ip_address=ip_address,
            after_value={
                'bank_name': account.bank_name,
                'last4': account.account_number_last4,
                'source': account.source,
                'is_primary': account.is_primary,
            },
        )
        logger.info('BankAccount created: %s for client %s', account.id, client.id)
        return account, True

    @staticmethod
    @transaction.atomic
    def mark_primary(account: BankAccount) -> BankAccount:
        """Make this account the primary for its client; demote others."""
        BankAccount.objects.filter(
            client_id=account.client_id, is_primary=True,
        ).exclude(pk=account.pk).update(is_primary=False)

        if not account.is_primary:
            account.is_primary = True
            account.save(update_fields=['is_primary', 'updated_at'])
        return account

    @staticmethod
    def find_by_number(client, raw_account_number):
        """Find a client's account by its full number (via blind index)."""
        digits = BankAccountService._normalize(raw_account_number)
        if not digits:
            return None
        return BankAccount.objects.filter(
            client=client, account_number_index=blind_index(digits),
        ).first()

    @staticmethod
    def accounts_for(client):
        return BankAccount.objects.filter(client=client)

    @staticmethod
    @transaction.atomic
    def link_to_mandate(account: BankAccount, mandate) -> None:
        """Associate a mandate with a bank account and bump last_seen."""
        mandate.bank_account = account
        mandate.save(update_fields=['bank_account', 'updated_at'])
        account.last_seen_at = timezone.now()
        account.save(update_fields=['last_seen_at', 'updated_at'])