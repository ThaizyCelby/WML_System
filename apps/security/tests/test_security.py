"""Tests for security event tracking."""
import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestSecurityEvents:

    def test_security_event_created(self):
        """Test creating a security event."""
        from apps.security.services import SecurityEventService
        from apps.security.models import SecurityEvent

        event = SecurityEventService.record(
            event_type='failed_login',
            ip_address='192.168.1.100',
            risk_score=40,
            severity='medium',
            description='Test security event',
        )

        assert event is not None
        assert SecurityEvent.objects.count() == 1
        assert event.risk_score == 40
        assert event.risk_level == 'medium'

    def test_high_risk_event_triggers_action(self):
        """Test that high-risk events trigger automated responses."""
        from apps.security.services import SecurityEventService

        event = SecurityEventService.record(
            event_type='brute_force_attempt',
            ip_address='192.168.1.200',
            risk_score=85,
            severity='critical',
            description='Critical security event',
        )

        assert event.action_taken == 'ip_blocked'

    def test_risk_level_calculation(self, db):
        """Test risk level calculation."""
        from apps.security.models import SecurityEvent

        event = SecurityEvent(risk_score=0)
        assert event.risk_level == 'low'

        event = SecurityEvent(risk_score=35)
        assert event.risk_level == 'medium'

        event = SecurityEvent(risk_score=65)
        assert event.risk_level == 'high'

        event = SecurityEvent(risk_score=90)
        assert event.risk_level == 'critical'
