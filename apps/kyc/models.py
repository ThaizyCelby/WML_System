"""KYC models for client onboarding."""
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel, UUIDPrimaryKeyModel


class KYCDocumentRequirement(UUIDPrimaryKeyModel, TimeStampedModel):
    """
    Defines a document type required for KYC verification.
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_mandatory = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0, help_text="Display order in the checklist")

    class Meta:
        db_table = 'kyc_document_requirements'
        ordering = ['order', 'name']
        verbose_name = 'KYC Document Requirement'
        verbose_name_plural = 'KYC Document Requirements'

    def __str__(self):
        return self.name


class KYCReview(UUIDPrimaryKeyModel, TimeStampedModel):
    """
    Records a review action performed by a staff member on a client's KYC profile.
    """
    client_profile = models.ForeignKey(
        'accounts.ClientProfile',
        on_delete=models.CASCADE,
        related_name='kyc_reviews',
    )
    reviewed_by = models.ForeignKey(
        'accounts.User',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='kyc_reviews_performed',
    )
    previous_status = models.CharField(max_length=30, blank=True, default='')
    new_status = models.CharField(max_length=30)
    notes = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'kyc_reviews'
        ordering = ['-reviewed_at']
        verbose_name = 'KYC Review'
        verbose_name_plural = 'KYC Reviews'

    def __str__(self):
        return f"{self.client_profile.user.email} â†’ {self.new_status}"

class CreditReport(UUIDPrimaryKeyModel, TimeStampedModel):
    """A credit report pulled from a bureau for a client."""
    user = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE, related_name='credit_reports',
    )
    id_number = models.CharField(max_length=20, db_index=True)
    bureau = models.CharField(max_length=50, db_index=True)
    score = models.IntegerField(null=True, blank=True)
    risk_band = models.CharField(max_length=30, blank=True, default='')
    total_monthly_obligations = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_outstanding_debt = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    worst_arrears_months = models.PositiveIntegerField(default=0)
    has_defaults = models.BooleanField(default=False)
    has_judgments = models.BooleanField(default=False)
    raw_response = models.JSONField(default=dict, blank=True)

    pulled_by = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='pulled_credit_reports',
    )
    consented_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = 'credit_reports'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'expires_at']),
            models.Index(fields=['id_number']),
        ]

    def __str__(self):
        return f"{self.bureau} report for {self.user_id} ({self.score})"

    @property
    def is_expired(self):
        from django.utils import timezone
        return self.expires_at < timezone.now()


class TradeLine(UUIDPrimaryKeyModel, TimeStampedModel):
    """A single credit account returned in a credit report."""
    credit_report = models.ForeignKey(
        CreditReport, on_delete=models.CASCADE, related_name='trade_lines',
    )
    creditor_name = models.CharField(max_length=200)
    account_type = models.CharField(max_length=50, blank=True, default='')
    account_number_masked = models.CharField(max_length=30, blank=True, default='')
    monthly_installment = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    outstanding_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    original_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    opened_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, default='current')
    arrears_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    months_in_arrears = models.PositiveIntegerField(default=0)
    is_secured = models.BooleanField(default=False)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'credit_trade_lines'
        ordering = ['-months_in_arrears', '-outstanding_balance']

    def __str__(self):
        return f"{self.creditor_name} - R{self.monthly_installment}/mo"