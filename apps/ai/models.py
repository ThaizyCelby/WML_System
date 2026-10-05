"""AI models: provider config, analyses, insights, trends."""
from django.db import models

from core.models import TimeStampedModel, UUIDPrimaryKeyModel


class AIProviderConfiguration(UUIDPrimaryKeyModel, TimeStampedModel):
    provider = models.CharField(max_length=50, unique=True)
    api_key_encrypted = models.TextField(blank=True, default='')
    model_name = models.CharField(max_length=100)
    max_tokens = models.PositiveIntegerField(default=2000)
    temperature = models.DecimalField(max_digits=3, decimal_places=2, default=0.1)
    is_active = models.BooleanField(default=False)
    usage_count = models.PositiveIntegerField(default=0)
    usage_limit = models.PositiveIntegerField(default=1000)

    class Meta:
        db_table = 'ai_provider_configurations'

    def __str__(self):
        return self.provider


class AIAnalysis(UUIDPrimaryKeyModel, TimeStampedModel):
    provider = models.CharField(max_length=50)
    model_name = models.CharField(max_length=100)
    input_reference = models.CharField(max_length=255, blank=True)
    output_data = models.JSONField(default=dict, blank=True)
    confidence = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    explanation = models.TextField(blank=True)
    human_reviewed = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        db_table = 'ai_analyses'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.provider} - {self.created_at}"


class AIAffordabilityAssessment(UUIDPrimaryKeyModel, TimeStampedModel):
    """AI-generated affordability verdict for a loan application. Admin-side."""
    VERDICT_CHOICES = [
        ('likely_to_pay', 'Likely to Pay'),
        ('at_risk', 'At Risk'),
        ('unlikely_to_pay', 'Unlikely to Pay'),
        ('insufficient_data', 'Insufficient Data'),
    ]

    application = models.ForeignKey(
        'loans.LoanApplication', on_delete=models.CASCADE,
        related_name='ai_affordability_assessments',
    )
    client = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE,
        related_name='ai_affordability_assessments',
    )
    verdict = models.CharField(max_length=30, choices=VERDICT_CHOICES)
    confidence = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    reasons = models.JSONField(default=list, blank=True)
    risk_factors = models.JSONField(default=list, blank=True)
    positive_factors = models.JSONField(default=list, blank=True)
    recommended_max_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    recommended_term_months = models.PositiveIntegerField(null=True, blank=True)
    dti_ratio = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    disposable_income = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    ai_analysis = models.ForeignKey(
        AIAnalysis, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='ai_affordability_assessments',
    )
    reviewed_by = models.ForeignKey(
        'accounts.User', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='reviewed_ai_assessments',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    staff_override_verdict = models.CharField(max_length=30, blank=True, default='')
    staff_notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'ai_affordability_assessments'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['application', '-created_at']),
            models.Index(fields=['verdict']),
        ]

    def __str__(self):
        return f"{self.verdict} ({self.confidence}%)"


class ClientInsight(UUIDPrimaryKeyModel, TimeStampedModel):
    """A single AI-generated insight for a client dashboard."""
    SEVERITY_CHOICES = [
        ('info', 'Informational'),
        ('positive', 'Positive'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
    ]

    client = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE, related_name='ai_insights',
    )
    headline = models.CharField(max_length=200)
    body = models.TextField()
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='info')
    category = models.CharField(max_length=50, default='general')
    action_label = models.CharField(max_length=80, blank=True, default='')
    action_url = models.CharField(max_length=300, blank=True, default='')
    is_dismissed = models.BooleanField(default=False)
    dismissed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    ai_analysis = models.ForeignKey(
        AIAnalysis, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='client_insights',
    )

    class Meta:
        db_table = 'client_insights'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['client', 'is_dismissed', '-created_at']),
            models.Index(fields=['severity']),
        ]

    def __str__(self):
        return f"[{self.severity}] {self.headline}"


class ClientTrendSnapshot(UUIDPrimaryKeyModel, TimeStampedModel):
    """Daily snapshot of a client's financial behaviour."""
    client = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE, related_name='trend_snapshots',
    )
    snapshot_date = models.DateField(db_index=True)

    monthly_income = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    monthly_expenses = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    debt_obligations = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    disposable_income = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    active_loans_count = models.PositiveIntegerField(default=0)
    total_outstanding = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    payments_on_time = models.PositiveIntegerField(default=0)
    payments_late = models.PositiveIntegerField(default=0)
    payments_missed = models.PositiveIntegerField(default=0)
    avg_days_late = models.DecimalField(max_digits=6, decimal_places=2, default=0)

    affordability_score = models.PositiveIntegerField(default=0)
    trend_direction = models.CharField(
        max_length=20, default='stable',
        choices=[
            ('improving', 'Improving'),
            ('stable', 'Stable'),
            ('deteriorating', 'Deteriorating'),
        ],
    )
    ai_summary = models.TextField(blank=True, default='')
    ai_recommendation = models.CharField(max_length=30, blank=True, default='')
    raw_ai_output = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'client_trend_snapshots'
        ordering = ['-snapshot_date']
        unique_together = [('client', 'snapshot_date')]
        indexes = [
            models.Index(fields=['client', '-snapshot_date']),
            models.Index(fields=['trend_direction']),
        ]

    def __str__(self):
        return f"{self.client.email} @ {self.snapshot_date} ({self.affordability_score})"