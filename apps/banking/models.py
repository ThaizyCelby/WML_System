"""Banking models for bank statements and transactions."""
from decimal import Decimal
from django.db import models
from core.models import TimeStampedModel, UUIDPrimaryKeyModel


class BankStatement(UUIDPrimaryKeyModel, TimeStampedModel):
    """Metadata for an uploaded bank statement."""
    organisation = models.ForeignKey(
        'accounts.Organisation', null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='bank_statements',
        db_index=True,
    )

    client = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='bank_statements')
    document = models.ForeignKey('documents.Document', null=True, blank=True, on_delete=models.SET_NULL)
    bank_name = models.CharField(max_length=100, blank=True, default='')
    account_number_masked = models.CharField(max_length=30, blank=True, default='')
    statement_period_start = models.DateField(null=True, blank=True)
    statement_period_end = models.DateField(null=True, blank=True)
    extracted_text = models.TextField(blank=True, default='')
    extraction_confidence = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    processing_status = models.CharField(
        max_length=20,
        default='pending',
        choices=[
            ('pending', 'Pending'),
            ('processing', 'Processing'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
        ],
    )

    class Meta:
        db_table = 'bank_statements'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['client', 'processing_status']),
            models.Index(fields=['organisation', 'processing_status']),
        ]

    def __str__(self):
        return f"{self.client.email} - {self.statement_period_start or 'unknown'}"


class BankTransaction(UUIDPrimaryKeyModel, TimeStampedModel):
    """Normalized bank transaction."""
    statement = models.ForeignKey(BankStatement, on_delete=models.CASCADE, related_name='transactions')
    transaction_date = models.DateField()
    description = models.TextField()
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    transaction_type = models.CharField(
        max_length=20,
        choices=[('credit', 'Credit'), ('debit', 'Debit')],
        default='debit',
    )
    category = models.CharField(max_length=50, blank=True, default='uncategorized')
    confidence_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    is_salary = models.BooleanField(default=False)
    is_debit_order = models.BooleanField(default=False)
    merchant_name = models.CharField(max_length=200, blank=True, default='')
    raw_data = models.JSONField(default=dict, blank=True)
    reviewer_corrected = models.BooleanField(default=False)

    class Meta:
        db_table = 'bank_transactions'
        ordering = ['-transaction_date']
        indexes = [
            models.Index(fields=['statement', 'transaction_date']),
            models.Index(fields=['category']),
            models.Index(fields=['is_salary']),
        ]

    def __str__(self):
        return f"{self.transaction_date} - {self.amount} - {self.description[:50]}"