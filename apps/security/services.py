"""Security event services."""
import logging

from django.conf import settings
from django.utils import timezone

from apps.audit.services import AuditService

logger = logging.getLogger('apps.security')

from .models import BlockedIP, SecurityEvent


class SecurityEventService:
    """Service for recording and managing security events."""

    @staticmethod
    def record(
        event_type: str,
        ip_address: str = None,
        user_agent: str = '',
        risk_score: int = 0,
        severity: str = 'low',
        description: str = '',
        user=None,
        ai_explanation: str = '',
        action_taken: str = '',
    ) -> SecurityEvent:
        """Record a security event."""
        user_id = None
        if user:
            user_id = str(user.id)

        event = SecurityEvent.objects.create(
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            event_type=event_type,
            risk_score=risk_score,
            severity=severity,
            description=description,
            ai_explanation=ai_explanation,
            action_taken=action_taken,
        )

        logger.warning(
            'SECURITY EVENT | type=%s | score=%s | severity=%s | ip=%s | desc=%s',
            event_type, risk_score, severity, ip_address, description[:200],
        )

        # Trigger automated response if needed
        if risk_score >= settings.SECURITY_CONFIG['RISK_SCORE_THRESHOLDS']['critical']:
            SecurityEventService._trigger_critical_response(event)
        elif risk_score >= settings.SECURITY_CONFIG['RISK_SCORE_THRESHOLDS']['high']:
            SecurityEventService._trigger_high_response(event)

        return event

    @staticmethod
    def _trigger_critical_response(event: SecurityEvent):
        """Automated response for critical risk events."""
        # Temporary block IP
        if event.ip_address:
            BlockedIP.objects.update_or_create(
                ip_address=event.ip_address,
                defaults={
                    'blocked_until': timezone.now() + timezone.timedelta(
                        seconds=settings.SECURITY_CONFIG['IP_BLOCK_DURATION']
                    ),
                    'reason': f'Auto-block from critical security event: {event.event_type}',
                    'is_active': True,
                },
            )
            event.action_taken = 'ip_blocked'
            event.save(update_fields=['action_taken'])

        # Send admin notification
        from apps.notifications.services import NotificationService
        NotificationService.send_security_alert(event)

        # Audit log
        AuditService.record(
            action='security_critical_event',
            object_type='security_event',
            object_id=str(event.id),
            description=f'Critical security event: {event.event_type}',
            correlation_id=str(event.id),
        )

    @staticmethod
    def _trigger_high_response(event: SecurityEvent):
        """Automated response for high-risk events."""
        event.action_taken = 'require_additional_auth'
        event.save(update_fields=['action_taken'])

        AuditService.record(
            action='security_high_risk_event',
            object_type='security_event',
            object_id=str(event.id),
            description=f'High-risk security event: {event.event_type}',
            correlation_id=str(event.id),
        )

    @staticmethod
    def get_user_security_events(user_id: str, limit: int = 50) -> list[SecurityEvent]:
        """Get security events for a specific user."""
        return SecurityEvent.objects.filter(user_id=user_id).order_by('-created_at')[:limit]

    @staticmethod
    def get_recent_security_events(limit: int = 100, min_score: int = 30) -> list[SecurityEvent]:
        """Get recent security events above a risk threshold."""
        return SecurityEvent.objects.filter(
            risk_score__gte=min_score,
        ).order_by('-created_at')[:limit]
