"""Security models."""
from django.db import models

from core.models import TimeStampedModel, UUIDPrimaryKeyModel


# ─────────────────────────────────────────────────────────────────────
# EXISTING MODELS (Phase 1)
# ─────────────────────────────────────────────────────────────────────
class SecurityEvent(UUIDPrimaryKeyModel):
    """
    Security event for tracking suspicious activity.
    """
    organisation = models.ForeignKey(
        'accounts.Organisation', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='security_events',
        db_index=True,
    )

    user_id = models.UUIDField(null=True, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    user_agent = models.TextField(blank=True, default='')
    event_type = models.CharField(max_length=100, db_index=True)
    risk_score = models.IntegerField(default=0, db_index=True, help_text='0-100 scale')
    severity = models.CharField(
        max_length=20,
        default='low',
        choices=[
            ('low', 'Low'),
            ('medium', 'Medium'),
            ('high', 'High'),
            ('critical', 'Critical'),
        ],
    )
    description = models.TextField(blank=True, default='')
    ai_explanation = models.TextField(blank=True, default='')
    action_taken = models.CharField(
        max_length=50,
        blank=True,
        default='',
        choices=[
            ('log_only', 'Log Only'),
            ('increase_monitoring', 'Increase Monitoring'),
            ('require_additional_auth', 'Require Additional Auth'),
            ('temporary_block', 'Temporary Block'),
            ('account_suspended', 'Account Suspended'),
            ('ip_blocked', 'IP Blocked'),
            ('session_invalidated', 'Session Invalidated'),
        ],
    )
    resolution = models.CharField(
        max_length=30,
        default='detected',
        choices=[
            ('detected', 'Detected'),
            ('triaged', 'Triaged'),
            ('investigating', 'Investigating'),
            ('contained', 'Contained'),
            ('resolved', 'Resolved'),
            ('false_positive', 'False Positive'),
        ],
    )
    reviewed_by = models.ForeignKey(
        'accounts.User',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='reviewed_security_events',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'security_events'
        verbose_name = 'Security Event'
        verbose_name_plural = 'Security Events'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['event_type', 'created_at']),
            models.Index(fields=['risk_score', 'created_at']),
            models.Index(fields=['severity', 'resolution']),
            models.Index(fields=['organisation', 'severity']),
        ]

    def __str__(self):
        return f"{self.event_type} - score={self.risk_score} - {self.severity}"

    @property
    def risk_level(self):
        if self.risk_score >= 80:
            return 'critical'
        elif self.risk_score >= 60:
            return 'high'
        elif self.risk_score >= 30:
            return 'medium'
        return 'low'


class BlockedIP(UUIDPrimaryKeyModel, TimeStampedModel):
    """Temporarily blocked IP addresses."""
    ip_address = models.GenericIPAddressField(unique=True, db_index=True)
    reason = models.TextField(blank=True, default='')
    blocked_until = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='blocked_ips',
    )
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = 'blocked_ips'
        verbose_name = 'Blocked IP'
        verbose_name_plural = 'Blocked IPs'

    def __str__(self):
        return f"{self.ip_address} (until {self.blocked_until})"

    @property
    def is_expired(self):
        from django.utils import timezone
        return self.blocked_until and self.blocked_until < timezone.now()


class RiskAssessment(UUIDPrimaryKeyModel, TimeStampedModel):
    """Risk assessment for users."""
    user = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE, related_name='risk_assessments',
    )
    risk_score = models.IntegerField(default=0)
    risk_level = models.CharField(max_length=20, default='low')
    factors = models.JSONField(default=dict, blank=True)
    ai_analysis = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = 'risk_assessments'
        verbose_name = 'Risk Assessment'
        verbose_name_plural = 'Risk Assessments'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} - score={self.risk_score}"


# ─────────────────────────────────────────────────────────────────────
# PHASE 7B MODELS
# ─────────────────────────────────────────────────────────────────────
class FraudAlert(UUIDPrimaryKeyModel, TimeStampedModel):
    """A suspected fraud case requiring human review."""
    organisation = models.ForeignKey(
        'accounts.Organisation', null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='fraud_alerts',
        db_index=True,
    )

    user_id = models.UUIDField(null=True, blank=True, db_index=True)
    source_event = models.ForeignKey(
        SecurityEvent, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='fraud_alerts',
    )
    alert_type = models.CharField(max_length=80, db_index=True)
    risk_score = models.IntegerField(default=0, db_index=True)
    severity = models.CharField(
        max_length=20, default='medium',
        choices=[
            ('low', 'Low'), ('medium', 'Medium'),
            ('high', 'High'), ('critical', 'Critical'),
        ],
    )
    summary = models.CharField(max_length=255)
    details = models.JSONField(default=dict, blank=True)
    signals = models.JSONField(default=list, blank=True)
    ai_analysis = models.JSONField(null=True, blank=True)
    status = models.CharField(
        max_length=20, default='open',
        choices=[
            ('open', 'Open'),
            ('investigating', 'Investigating'),
            ('resolved', 'Resolved'),
            ('false_positive', 'False Positive'),
            ('escalated', 'Escalated'),
        ],
        db_index=True,
    )
    assigned_to = models.ForeignKey(
        'accounts.User', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='assigned_fraud_alerts',
    )
    reviewed_by = models.ForeignKey(
        'accounts.User', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='reviewed_fraud_alerts',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True, default='')
    action_taken = models.CharField(max_length=50, blank=True, default='')

    class Meta:
        db_table = 'fraud_alerts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'severity']),
            models.Index(fields=['user_id', 'created_at']),
            models.Index(fields=['organisation', 'status']),
        ]

    def __str__(self):
        return f"[{self.severity}] {self.alert_type} - {self.status}"


class UserDevice(UUIDPrimaryKeyModel, TimeStampedModel):
    """Track known devices per user to spot anomalies."""
    user = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE, related_name='devices',
    )
    fingerprint = models.CharField(max_length=64, db_index=True)
    user_agent = models.TextField(blank=True, default='')
    first_ip = models.GenericIPAddressField(null=True, blank=True)
    last_ip = models.GenericIPAddressField(null=True, blank=True)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    is_trusted = models.BooleanField(default=False)
    seen_count = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = 'user_devices'
        unique_together = [('user', 'fingerprint')]
        ordering = ['-last_seen']

    def __str__(self):
        return f"{self.user.email} :: {self.fingerprint[:12]}"


class LoginAttempt(UUIDPrimaryKeyModel):
    """Lightweight log of every login attempt (success or failure)."""
    user = models.ForeignKey(
        'accounts.User', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='login_attempts',
    )
    email = models.CharField(max_length=255, blank=True, default='', db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    user_agent = models.TextField(blank=True, default='')
    success = models.BooleanField(default=False)
    failure_reason = models.CharField(max_length=100, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'login_attempts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['ip_address', 'created_at']),
            models.Index(fields=['email', 'created_at']),
        ]

    def __str__(self):
        status = 'OK' if self.success else 'FAIL'
        return f"{self.email} @ {self.ip_address} [{status}]"