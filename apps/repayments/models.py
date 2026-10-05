"""Repayment and schedule models."""
from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator

from core.models import TimeStampedModel, UUIDPrimaryKeyModel


class RepaymentSchedule(UUIDPrimaryKeyModel, TimeStampedModel):
    organisation = models.ForeignKey(
        'accounts.Organisation', null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='repayment_schedules',
        db_index=True,
    )

    loan = models.ForeignKey('loans.Loan', on_delete=models.CASCADE, related_name='repayment_schedule')
    period_number = models.PositiveIntegerField()
    scheduled_date = models.DateField(db_index=True)
    principal_portion = models.DecimalField(max_digits=15, decimal_places=2)
    interest_portion = models.DecimalField(max_digits=15, decimal_places=2)
    fees_portion = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)
    balance_after = models.DecimalField(max_digits=15, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(
        max_length=20, default='pending',
        choices=[
            ('pending','Pending'), ('partial','Partial'),
            ('paid','Paid'), ('overdue','Overdue'), ('waived','Waived'),
        ],
        db_index=True,
    )

    class Meta:
        db_table = 'repayment_schedules'
        unique_together = [('loan', 'period_number')]
        ordering = ['loan', 'period_number']
        indexes = [
            models.Index(fields=['loan', 'status']),
            models.Index(fields=['scheduled_date', 'status']),
            models.Index(fields=['organisation', 'status']),
        ]

    def __str__(self):
        return f"{self.loan_id} period {self.period_number}"

    @property
    def outstanding(self):
        return max(self.total_amount - self.amount_paid, Decimal('0.00'))


class Repayment(UUIDPrimaryKeyModel, TimeStampedModel):
    organisation = models.ForeignKey(
        'accounts.Organisation', null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='repayments',
        db_index=True,
    )

    loan = models.ForeignKey('loans.Loan', on_delete=models.CASCADE, related_name='repayments')
    schedule = models.ForeignKey(
        RepaymentSchedule, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='repayments',
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    actual_date = models.DateField()
    method = models.CharField(max_length=20, default='debit_order', choices=[
        ('debit_order','Debit Order'), ('eft','EFT'), ('card','Card'),
        ('cash','Cash'), ('adjustment','Adjustment'),
    ])
    reference = models.CharField(max_length=100, blank=True, default='')
    status = models.CharField(max_length=20, default='successful', choices=[
        ('pending','Pending'), ('successful','Successful'),
        ('failed','Failed'), ('reversed','Reversed'),
    ])
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'repayments'
        ordering = ['-actual_date']
        indexes = [
            models.Index(fields=['loan', 'status']),
            models.Index(fields=['organisation', 'status']),
        ]

    def __str__(self):
        return f"{self.loan_id} {self.amount} on {self.actual_date}"