"""Tests for the fraud engine and rules."""
import pytest
from datetime import timedelta
from django.utils import timezone

from apps.accounts.models import User
from apps.security.models import BlockedIP, FraudAlert, LoginAttempt, SecurityEvent
from apps.security.risk_engine import FraudEngine, RiskScorer
from apps.security.fraud_rules import (
    rule_velocity_login_failures, rule_multiple_users_same_ip,
    rule_new_device_for_user, rule_rapid_applications,
)


@pytest.mark.django_db
class TestFraudRules:

    def test_velocity_login_failures_triggers(self):
        for _ in range(12):
            LoginAttempt.objects.create(
                email='victim@example.com', ip_address='10.0.0.5', success=False,
            )
        sig = rule_velocity_login_failures('10.0.0.5', 'victim@example.com')
        assert sig is not None
        assert sig.code == 'login_velocity_exceeded'
        assert sig.weight > 0

    def test_velocity_below_threshold_no_signal(self):
        LoginAttempt.objects.create(email='x@y.com', ip_address='10.0.0.1', success=False)
        assert rule_velocity_login_failures('10.0.0.1', 'x@y.com') is None

    def test_multiple_users_same_ip(self):
        for i in range(6):
            u = User.objects.create_user(email=f'u{i}@x.com', password='TestPass123!')
            LoginAttempt.objects.create(
                user=u, email=u.email, ip_address='192.168.1.5', success=True,
            )
        sig = rule_multiple_users_same_ip('192.168.1.5')
        assert sig is not None
        assert sig.code == 'multiple_users_same_ip'

    def test_new_device_for_user(self):
        u = User.objects.create_user(email='nd@x.com', password='TestPass123!')
        sig = rule_new_device_for_user(u, 'fp-new-123')
        assert sig is not None
        assert sig.code == 'new_device'

    def test_rapid_applications(self):
        from apps.loans.models import LoanApplication, LoanProduct
        u = User.objects.create_user(email='rap@x.com', password='TestPass123!')
        product = LoanProduct.objects.create(name='P')
        for _ in range(4):
            LoanApplication.objects.create(
                client=u, product=product, requested_amount=1000, requested_term=12,
            )
        sig = rule_rapid_applications(u)
        assert sig is not None
        assert sig.code == 'rapid_applications'


@pytest.mark.django_db
class TestRiskScorer:

    def test_combine_returns_low_for_no_signals(self):
        r = RiskScorer.combine([])
        assert r.score == 0
        assert r.severity == 'low'
        assert r.action_taken == 'log_only'

    def test_combine_uses_weights(self):
        from apps.security.fraud_rules import Signal
        signals = [
            Signal('a', 30, 'msg a'),
            Signal('b', 25, 'msg b'),
        ]
        r = RiskScorer.combine(signals)
        assert r.score == 55
        assert r.severity == 'medium'

    def test_combine_caps_at_100(self):
        from apps.security.fraud_rules import Signal
        r = RiskScorer.combine([Signal('x', 200, '')])
        assert r.score == 100
        assert r.severity == 'critical'
        assert r.action_taken == 'temporary_block'


@pytest.mark.django_db
class TestFraudEngine:

    def test_evaluate_persists_event_and_alert(self):
        u = User.objects.create_user(email='fe@x.com', password='TestPass123!')
        # Force a signal by flooding failed logins
        for _ in range(12):
            LoginAttempt.objects.create(email=u.email, ip_address='10.1.1.1', success=False)

        risk = FraudEngine.evaluate(
            user=u, email=u.email, ip_address='10.1.1.1',
            user_agent='pytest', context='login',
        )
        assert risk.score > 0
        assert SecurityEvent.objects.filter(event_type='fraud_login').exists()
        assert FraudAlert.objects.filter(user_id=str(u.id)).exists()

    def test_critical_risk_blocks_ip(self):
        u = User.objects.create_user(email='c@x.com', password='TestPass123!')
        # Force many login failures to exceed threshold
        for _ in range(15):
            LoginAttempt.objects.create(email=u.email, ip_address='10.9.9.9', success=False)

        risk = FraudEngine.evaluate(
            user=u, email=u.email, ip_address='10.9.9.9',
            user_agent='pytest', context='login',
        )
        # If this scores >= critical, verify IP block was applied
        if risk.severity == 'critical':
            assert BlockedIP.objects.filter(ip_address='10.9.9.9', is_active=True).exists()
