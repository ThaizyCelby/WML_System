"""Audit log models."""
import uuid

from django.db import models

from core.models import TimeStampedModel, UUIDPrimaryKeyModel


class AuditLog(UUIDPrimaryKeyModel):
    """
    Immutable audit log entry.

    Audit logs should never be modified or deleted by regular users.
    Only superusers with special permission can purge old logs according to retention policy.
    """
    organisation = models.ForeignKey(
        'accounts.Organisation', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='audit_logs',
        db_index=True,
        help_text='Tenant this action occurred in. SET_NULL so deleting an '
                  'organisation never destroys audit history.',
    )

    actor_id = models.UUIDField(null=True, blank=True, db_index=True)
    actor_email = models.CharField(max_length=255, blank=True, default='')

    action = models.CharField(max_length=100, db_index=True)
    object_type = models.CharField(max_length=100, blank=True, default='')
    object_id = models.CharField(max_length=255, blank=True, default='')

    before_value = models.JSONField(null=True, blank=True)
    after_value = models.JSONField(null=True, blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default='')

    correlation_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    description = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'audit_logs'
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['action', 'created_at']),
            models.Index(fields=['object_type', 'object_id']),
            models.Index(fields=['actor_id', 'created_at']),
            models.Index(fields=['correlation_id']),
            models.Index(fields=['organisation', 'created_at']),
        ]

    def __str__(self):
        return f"{self.created_at} - {self.actor_email} - {self.action}"

    # Prevent modification
    def save(self, *args, **kwargs):
        # Use _state.adding to distinguish new records from updates.
        # self.pk is set immediately due to the UUID default, so we can't rely on it.
        if not self._state.adding:
            raise ValueError('Audit logs cannot be modified')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('Audit logs cannot be deleted')