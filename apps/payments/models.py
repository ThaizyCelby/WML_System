"""Payment and debit-order models."""
import uuid
from decimal import Decimal

from django.db import models

from core.models import TimeStampedModel, UUIDPrimaryKeyModel


class DebitInstruction(UUIDPrimaryKeyModel, TimeStampedModel):
    """
    A debit-order mandate linked to a loan.

    Lifecycle:
        draft → pending_client → pending_review → active
                                              → rejected
        active → cancelled | expired
    """
    organisation = models.ForeignKey(
        'accounts.Organisation', null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='debit_instructions',
        db_index=True,
    )

    loan = models.ForeignKey(
        'loans.Loan', on_delete=models.CASCADE, related_name='debit_instructions',
    )
    provider = models.CharField(max_length=50, default='mock')
    provider_reference = models.CharField(max_length=255, blank=True, default='', db_index=True)

    # ── Banking details ──────────────────────────────────────────
    account_holder_name = models.CharField(max_length=200)
    account_number_last4 = models.CharField(max_length=4, blank=True, default='')
    account_number_encrypted = models.TextField(blank=True, default='')
    bank_name = models.CharField(max_length=100)
    branch_code = models.CharField(max_length=20, blank=True, default='')
    account_type = models.CharField(max_length=20, blank=True, default='cheque')
    bank_account = models.ForeignKey(
        'accounts.BankAccount',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='mandates',
        help_text='Structured bank account this mandate was created from.',
    )

    # ── Mandate metadata ─────────────────────────────────────────
    mandate_reference = models.CharField(max_length=100, blank=True, default='', db_index=True)
    mandate_reference_number = models.CharField(max_length=64, blank=True, default='')

    # ── Consent / signature evidence ─────────────────────────────
    mandate_signed_by = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='signed_mandates',
    )
    mandate_signed_at = models.DateTimeField(null=True, blank=True)
    mandate_ip = models.GenericIPAddressField(null=True, blank=True)
    mandate_user_agent = models.TextField(blank=True, default='')
    mandate_pdf_storage_key = models.CharField(max_length=500, blank=True, default='')
    mandate_hash = models.CharField(max_length=64, blank=True, default='')

    # ── Status + staff review ────────────────────────────────────
    status = models.CharField(
        max_length=25,
        default='draft',
        choices=[
            ('draft', 'Draft'),
            ('pending_client', 'Awaiting Client Signature'),
            ('pending_review', 'Pending Staff Review'),
            ('active', 'Active'),
            ('rejected', 'Rejected'),
            ('cancelled', 'Cancelled'),
            ('expired', 'Expired'),
        ],
        db_index=True,
    )
    is_active = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='created_mandates',
    )
    reviewed_by = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='reviewed_mandates',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True, default='')
    rejection_reason = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'debit_instructions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['loan', 'status']),
            models.Index(fields=['provider', 'provider_reference']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['organisation', 'status']),
        ]

    def __str__(self):
        return f"Mandate {self.id} — {self.status}"

    @property
    def masked_account(self):
        return f"****{self.account_number_last4}" if self.account_number_last4 else "—"


class PaymentTransaction(UUIDPrimaryKeyModel, TimeStampedModel):
    """A payment transaction, either expected or actual."""
    organisation = models.ForeignKey(
        'accounts.Organisation', null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='payment_transactions',
        db_index=True,
    )

    loan = models.ForeignKey('loans.Loan', on_delete=models.CASCADE, related_name='payment_transactions')
    repayment_schedule_id = models.UUIDField(null=True, blank=True)
    debit_instruction = models.ForeignKey(
        DebitInstruction, null=True, blank=True, on_delete=models.SET_NULL, related_name='transactions',
    )
    provider = models.CharField(max_length=50, default='mock')
    provider_transaction_id = models.CharField(max_length=255, blank=True, default='', db_index=True)
    idempotency_key = models.CharField(max_length=64, unique=True, db_index=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.CharField(
        max_length=20, default='pending',
        choices=[
            ('pending', 'Pending'),
            ('processing', 'Processing'),
            ('successful', 'Successful'),
            ('failed', 'Failed'),
            ('reversed', 'Reversed'),
            ('cancelled', 'Cancelled'),
        ],
        db_index=True,
    )
    payment_method = models.CharField(
        max_length=20, default='debit_order',
        choices=[('debit_order', 'Debit Order'), ('eft', 'EFT'), ('card', 'Card'), ('cash', 'Cash')],
    )
    raw_payload = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default='')

    # ── Retry / undisputable tracking ─────────────────────────────
    attempt_number = models.PositiveSmallIntegerField(
        default=1,
        help_text='1 = first attempt; >1 = retry.',
    )
    is_undisputable = models.BooleanField(
        default=False, db_index=True,
        help_text='Set by admin: retry via the irrevocable mandate authority.',
    )
    next_retry_at = models.DateTimeField(
        null=True, blank=True, db_index=True,
        help_text='When the retry should next be attempted.',
    )
    retry_reason = models.TextField(blank=True, default='')
    parent_transaction = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='retries',
        help_text='Original attempt this retry was created from.',
    )
    decline_code = models.CharField(max_length=50, blank=True, default='')
    decline_reason = models.TextField(blank=True, default='')
    retry_scheduled_by = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='scheduled_retries',
    )
    retry_scheduled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'payment_transactions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['loan', 'status']),
            models.Index(fields=['provider', 'provider_transaction_id']),
            models.Index(fields=['status', 'next_retry_at']),
            models.Index(fields=['organisation', 'status']),
        ]

    def __str__(self):
        return f"Txn {self.id} {self.amount} [{self.status}]"


class PaymentWebhook(UUIDPrimaryKeyModel, TimeStampedModel):
    """Log of incoming webhooks from payment providers (idempotent)."""
    provider = models.CharField(max_length=50)
    webhook_type = models.CharField(max_length=100, blank=True, default='')
    provider_event_id = models.CharField(max_length=255, blank=True, default='', db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    signature = models.CharField(max_length=255, blank=True, default='')
    processed = models.BooleanField(default=False)
    error_message = models.TextField(blank=True, default='')
    transaction = models.ForeignKey(
        PaymentTransaction, null=True, blank=True, on_delete=models.SET_NULL, related_name='webhooks',
    )

    class Meta:
        db_table = 'payment_webhooks'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['provider', 'provider_event_id'],
                name='unique_provider_event',
                condition=models.Q(provider_event_id__gt=''),
            ),
        ]


class ReconciliationRecord(UUIDPrimaryKeyModel, TimeStampedModel):
    """Result of a reconciliation between expected and actual payments."""
    loan = models.ForeignKey('loans.Loan', on_delete=models.CASCADE, related_name='reconciliation_records')
    payment_transaction = models.ForeignKey(
        PaymentTransaction, null=True, blank=True, on_delete=models.SET_NULL,
    )
    expected_amount = models.DecimalField(max_digits=15, decimal_places=2)
    actual_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    difference = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(
        max_length=20,
        choices=[
            ('matched', 'Matched'), ('missing', 'Missing'), ('partial', 'Partial'),
            ('overpayment', 'Overpayment'), ('unmatched', 'Unmatched'), ('reversed', 'Reversed'),
        ],
        db_index=True,
    )
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'reconciliation_records'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['loan', 'status'])]