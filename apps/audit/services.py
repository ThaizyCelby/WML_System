"""Audit logging service."""
import logging
import uuid
from typing import Any, Optional

from django.conf import settings

logger = logging.getLogger('apps.audit')

from .models import AuditLog


class AuditService:
    """Centralized audit logging service."""

    @staticmethod
    def record(
            action: str,
            object_type: str = '',
            object_id: str = '',
            actor=None,
            ip_address: Optional[str] = None,
            user_agent: str = '',
            before_value: Optional[dict] = None,
            after_value: Optional[dict] = None,
            correlation_id: str = '',
            description: str = '',
    ) -> Optional[AuditLog]:
        """
        Create an audit log entry.

        This method is designed to be fast and safe.
        Audit logging failures should not break the main operation.
        """
        try:
            actor_id = None
            actor_email = ''

            if actor is not None:
                actor_id = getattr(actor, 'id', None)
                actor_email = getattr(actor, 'email', '') or str(actor)

            if not correlation_id:
                correlation_id = uuid.uuid4().hex[:16]

            audit_entry = AuditLog.objects.create(
                actor_id=actor_id,
                actor_email=actor_email,
                action=action,
                object_type=object_type,
                object_id=object_id,
                before_value=before_value,
                after_value=after_value,
                ip_address=ip_address,
                user_agent=user_agent,
                correlation_id=correlation_id,
                description=description,
            )

            logger.info(
                'AUDIT | action=%s | actor=%s | object=%s:%s | ip=%s | correlation_id=%s',
                action, actor_email, object_type, object_id, ip_address, correlation_id,
            )

            return audit_entry
        except Exception as e:
            # Audit logging should never break the main operation
            logger.error('Failed to write audit log: %s', e)
            return None

    @staticmethod
    def get_audit_trail(
            object_type: str,
            object_id: str,
            limit: int = 100,
    ) -> list[AuditLog]:
        """Get audit trail for a specific object."""
        return AuditLog.objects.filter(
            object_type=object_type,
            object_id=object_id,
        ).order_by('-created_at')[:limit]

    @staticmethod
    def get_user_audit_trail(user_id: str, limit: int = 100) -> list[AuditLog]:
        """Get audit trail for a specific user."""
        return AuditLog.objects.filter(
            actor_id=user_id,
        ).order_by('-created_at')[:limit]

    @staticmethod
    def purge_old_logs(retention_days: int = 365) -> int:
        """
        Purge audit logs older than the retention period.
        Only callable by system administrators with appropriate permissions.
        """
        from django.utils import timezone

        cutoff = timezone.now() - timezone.timedelta(days=retention_days)
        deleted_count, _ = AuditLog.objects.filter(created_at__lt=cutoff).delete()
        return deleted_count
