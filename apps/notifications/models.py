"""Notification models."""
from django.db import models

from core.models import TimeStampedModel, UUIDPrimaryKeyModel


class NotificationTemplate(UUIDPrimaryKeyModel, TimeStampedModel):
    """Reusable template for a notification event."""
    code = models.CharField(max_length=80, db_index=True)
    channel = models.CharField(
        max_length=20,
        choices=[('email', 'Email'), ('sms', 'SMS'), ('in_app', 'In-App'), ('push', 'Push')],
    )
    subject = models.CharField(max_length=200, blank=True, default='')
    body = models.TextField(help_text='Can use {placeholders}')
    is_active = models.BooleanField(default=True)
    description = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        db_table = 'notification_templates'
        unique_together = [('code', 'channel')]

    def render(self, context: dict) -> dict:
        try:
            subject = self.subject.format(**context)
        except (KeyError, IndexError):
            subject = self.subject
        try:
            body = self.body.format(**context)
        except (KeyError, IndexError):
            body = self.body
        return {'subject': subject, 'body': body}


class Notification(UUIDPrimaryKeyModel, TimeStampedModel):
    """A single notification sent (or queued) to a user."""
    user = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE, related_name='notifications',
    )
    code = models.CharField(max_length=80, db_index=True)
    channel = models.CharField(max_length=20, default='in_app')
    title = models.CharField(max_length=200)
    message = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20, default='pending',
        choices=[('pending', 'Pending'), ('sent', 'Sent'), ('failed', 'Failed'), ('read', 'Read')],
        db_index=True,
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', 'created_at']),
        ]


class NotificationPreference(UUIDPrimaryKeyModel, TimeStampedModel):
    """User's preferred channels per notification code prefix."""
    user = models.OneToOneField(
        'accounts.User', on_delete=models.CASCADE, related_name='notification_preferences',
    )
    email_enabled = models.BooleanField(default=True)
    sms_enabled = models.BooleanField(default=False)
    in_app_enabled = models.BooleanField(default=True)
    push_enabled = models.BooleanField(default=False)
    marketing_opt_in = models.BooleanField(default=False)

    class Meta:
        db_table = 'notification_preferences'
