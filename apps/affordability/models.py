"""Models for affordability assessments."""
from django.db import models
from core.models import TimeStampedModel, UUIDPrimaryKeyModel


class AffordabilityAssessment(UUIDPrimaryKeyModel, TimeStampedModel):
    """Stored result of an affordability calculation."""
    client = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='affordability_assessments')
    gross_income = models.DecimalField(max_digits=15, decimal_places=2)
    monthly_expenses = models.DecimalField(max_digits=15, decimal_places=2)
    existing_debt_obligations = models.DecimalField(max_digits=15, decimal_places=2)
    proposed_repayment = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.CharField(max_length=30)
    explanation = models.TextField(blank=True)
    result_data = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'affordability_assessments'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.client.email} - {self.status}"
