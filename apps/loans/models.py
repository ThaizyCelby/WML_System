"""Loan models: LoanProduct, LoanApplication, LoanApplicationEvent, Loan, LoanAgreement."""
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from core.models import TimeStampedModel, UUIDPrimaryKeyModel


class LoanProduct(UUIDPrimaryKeyModel, TimeStampedModel):
    organisation = models.ForeignKey(
        'accounts.Organisation', null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='loan_products',
        db_index=True,
    )

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    min_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('1000.00'))
    max_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('100000.00'))
    min_term = models.PositiveIntegerField(default=1)
    max_term = models.PositiveIntegerField(default=60)
    interest_type = models.CharField(
        max_length=20,
        choices=[('flat', 'Flat'), ('simple', 'Simple'), ('amortized', 'Amortized')],
        default='flat',
    )
    interest_rate = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('30.00'))
    origination_fee_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('2.50'))
    late_payment_fee = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('50.00'))
    repayment_frequency = models.CharField(
        max_length=20,
        choices=[('daily','Daily'), ('weekly','Weekly'), ('fortnightly','Fortnightly'), ('monthly','Monthly')],
        default='monthly',
    )
    max_exposure = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('1000000.00'))
    is_active = models.BooleanField(default=True)
    eligibility_rules = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'loan_products'

    def __str__(self):
        return self.name


class LoanApplication(UUIDPrimaryKeyModel, TimeStampedModel):
    organisation = models.ForeignKey(
        'accounts.Organisation', null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='loan_applications',
        db_index=True,
    )

    client = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='loan_applications')
    product = models.ForeignKey(LoanProduct, on_delete=models.SET_NULL, null=True, blank=True, related_name='applications')
    requested_amount = models.DecimalField(max_digits=15, decimal_places=2)
    requested_term = models.PositiveIntegerField()
    status = models.CharField(
        max_length=30, default='draft',
        choices=[
            ('draft','Draft'), ('submitted','Submitted'), ('document_review','Document Review'),
            ('kyc_review','KYC Review'), ('affordability_review','Affordability Review'),
            ('credit_review','Credit Review'), ('approved','Approved'),
            ('contract_pending','Contract Pending'), ('contract_accepted','Contract Accepted'),
            ('disbursement_pending','Disbursement Pending'), ('active','Active'),
            ('paid','Paid'), ('overdue','Overdue'), ('defaulted','Defaulted'),
            ('restructured','Restructured'), ('rejected','Rejected'), ('cancelled','Cancelled'),
        ],
        db_index=True,
    )
    kyc_status_snapshot = models.CharField(max_length=30, blank=True, default='')
    affordability_result = models.JSONField(null=True, blank=True)
    credit_review_notes = models.TextField(blank=True)
    approved_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    approved_term = models.PositiveIntegerField(null=True, blank=True)
    interest_rate = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    policy_result = models.JSONField(
        null=True, blank=True,
        help_text='Cached output of the deterministic policy engine.',
    )
    policy_evaluated_at = models.DateTimeField(null=True, blank=True)

    # ── Client payday (set by client during application) ──────────
    client_payday = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text='Day of month (1-31) the client gets paid',
    )

    # ── Admin review gates ────────────────────────────────────────
    documents_reviewed = models.BooleanField(default=False)
    transactions_reviewed = models.BooleanField(default=False)

    # ── Contract verification ─────────────────────────────────────
    contract_verified_by_admin = models.BooleanField(default=False)
    contract_verified_at = models.DateTimeField(null=True, blank=True)
    contract_verified_by = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='verified_contracts',
    )

    class Meta:
        db_table = 'loan_applications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['client', 'status']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['organisation', 'status']),
        ]

    def __str__(self):
        return f"{self.client.email} - {self.status}"


class LoanApplicationEvent(UUIDPrimaryKeyModel, TimeStampedModel):
    application = models.ForeignKey(LoanApplication, on_delete=models.CASCADE, related_name='events')
    from_status = models.CharField(max_length=30)
    to_status = models.CharField(max_length=30)
    actor = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL)
    notes = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'loan_application_events'
        ordering = ['-timestamp']


class Loan(UUIDPrimaryKeyModel, TimeStampedModel):
    organisation = models.ForeignKey(
        'accounts.Organisation', null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='loans',
        db_index=True,
    )

    application = models.OneToOneField(LoanApplication, on_delete=models.CASCADE, related_name='loan')
    client = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='loans')
    product = models.ForeignKey(LoanProduct, on_delete=models.SET_NULL, null=True)
    principal_amount = models.DecimalField(max_digits=15, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=6, decimal_places=2)
    total_interest = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    fees_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    term_periods = models.PositiveIntegerField()
    repayment_frequency = models.CharField(max_length=20, default='monthly')

    # ── Collection day (set by admin) ─────────────────────────────
    collection_day = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text='Day of month (1-31) for repayments. Set by admin.',
    )

    # ── Collection tracking window (set by admin) ─────────────────
    collection_window_start = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text='Day of month (1-31) collection attempts begin.',
    )
    collection_window_end = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text='Day of month (1-31) collection attempts stop.',
    )
    max_retry_attempts = models.PositiveSmallIntegerField(
        default=3,
        help_text='Maximum undisputable retry attempts per instalment.',
    )

    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    outstanding_balance = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.CharField(
        max_length=20, default='pending',
        choices=[
            ('pending','Pending'), ('active','Active'), ('paid','Paid'),
            ('overdue','Overdue'), ('defaulted','Defaulted'),
        ],
    )

    # ── Fallout / default risk prediction ─────────────────────────
    default_risk_score = models.PositiveSmallIntegerField(
        default=0, db_index=True,
        help_text='0-100 score; higher = higher likelihood of default',
    )
    default_risk_band = models.CharField(
        max_length=20, default='low', db_index=True,
        choices=[
            ('low', 'Low'),
            ('medium', 'Medium'),
            ('high', 'High'),
            ('critical', 'Critical'),
        ],
    )
    default_risk_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'loans'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['client', 'status']),
            models.Index(fields=['organisation', 'status']),
        ]

    def __str__(self):
        return f"Loan {self.id} - {self.client.email}"

    @property
    def effective_collection_window(self):
        """
        Return (start_day, end_day) tuple. Falls back to `collection_day` if no
        window is configured, and to (1, 1) as a final default.
        """
        start = self.collection_window_start or self.collection_day or 1
        end = self.collection_window_end or start
        if end < start:
            start, end = end, start
        return start, end


class LoanAgreement(UUIDPrimaryKeyModel, TimeStampedModel):
    loan = models.OneToOneField(Loan, on_delete=models.CASCADE, related_name='agreement')
    version = models.PositiveIntegerField(default=1)
    pdf_storage_key = models.CharField(max_length=500)
    agreement_hash = models.CharField(max_length=64, help_text='SHA-256 of PDF')
    status = models.CharField(
        max_length=20, default='draft',
        choices=[
            ('draft','Draft'), ('sent','Sent to Client'),
            ('accepted','Accepted'), ('declined','Declined'), ('superseded','Superseded'),
        ],
    )
    generated_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL)
    accepted_ip = models.GenericIPAddressField(null=True, blank=True)
    accepted_user_agent = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'loan_agreements'
        ordering = ['-generated_at']

    def __str__(self):
        return f"Agreement for loan {self.loan_id} v{self.version}"