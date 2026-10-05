"""Risk scoring and automated response.

The FraudEngine combines deterministic rules into a weighted score, then
maps the score to a severity band and an automated response. AI is used
only as a secondary advisory layer — never as the decision-maker.

The AI provider is controlled by settings.AI_DEFAULT_PROVIDER, which
defaults to 'glm'.
"""
import logging
from dataclasses import dataclass
from typing import List, Optional

from django.conf import settings
from django.utils import timezone

from .fraud_rules import Signal
from .models import BlockedIP, FraudAlert, LoginAttempt, SecurityEvent, UserDevice

logger = logging.getLogger('apps.security')


# ----------------------------------------------------------------------
# Result container
# ----------------------------------------------------------------------
@dataclass
class RiskResult:
    score: int
    severity: str
    signals: List[dict]
    action_taken: str

    def to_dict(self):
        return {
            'score': self.score,
            'severity': self.severity,
            'signals': self.signals,
            'action_taken': self.action_taken,
        }


# ----------------------------------------------------------------------
# Scoring
# ----------------------------------------------------------------------
class RiskScorer:
    """Combine multiple signals into a single 0-100 score and a severity band."""

    @staticmethod
    def combine(signals: List[Signal]) -> RiskResult:
        if not signals:
            return RiskResult(
                score=0, severity='low', signals=[], action_taken='log_only',
            )

        # Weighted sum, capped at 100
        score = min(100, sum(s.weight for s in signals))

        thresholds = settings.SECURITY_CONFIG['RISK_SCORE_THRESHOLDS']
        if score >= thresholds['critical']:
            severity = 'critical'
        elif score >= thresholds['high']:
            severity = 'high'
        elif score >= thresholds['medium']:
            severity = 'medium'
        else:
            severity = 'low'

        action = settings.SECURITY_CONFIG['AUTO_RESPONSES'][severity]
        return RiskResult(
            score=score,
            severity=severity,
            signals=[
                {
                    'code': s.code,
                    'weight': s.weight,
                    'message': s.message,
                    'metadata': s.metadata,
                }
                for s in signals
            ],
            action_taken=action,
        )


# ----------------------------------------------------------------------
# Automated response
# ----------------------------------------------------------------------
class AutoResponseEngine:
    """Apply automated responses based on severity."""

    @staticmethod
    def apply(risk: RiskResult, user=None, ip_address: Optional[str] = None):
        action = risk.action_taken
        applied = action

        if action == 'log_only':
            # Audit trail only — the SecurityEvent has already been written.
            pass

        elif action == 'increase_monitoring':
            # Recorded via SecurityEvent; no additional action.
            pass

        elif action == 'require_additional_auth':
            # Mark session as "step-up required" via cache.
            try:
                from django.core.cache import cache
                if user:
                    cache.set(
                        f"stepup_required:{user.id}", True, timeout=1800,
                    )
            except Exception as e:
                logger.warning("Could not set step-up flag: %s", e)

        elif action == 'temporary_block':
            # Block the source IP and lock the user account (if known).
            if ip_address:
                duration = settings.SECURITY_CONFIG['IP_BLOCK_DURATION']
                BlockedIP.objects.update_or_create(
                    ip_address=ip_address,
                    defaults={
                        'blocked_until': timezone.now() + timezone.timedelta(seconds=duration),
                        'reason': f"Auto-block: risk score {risk.score}",
                        'is_active': True,
                    },
                )
            if user:
                try:
                    user.lock_account(duration_seconds=1800)
                except Exception as e:
                    logger.warning("Could not lock user account: %s", e)

        return applied


# ----------------------------------------------------------------------
# Orchestrator
# ----------------------------------------------------------------------
class FraudEngine:
    """Orchestrate rules -> score -> response -> persist."""

    @staticmethod
    def evaluate(
        *,
        user=None,
        email: str = '',
        ip_address: str = '',
        user_agent: str = '',
        device_fingerprint: str = '',
        context: str = 'login',
        run_ai: bool = False,
    ) -> RiskResult:
        from .fraud_rules import (
            rule_velocity_login_failures,
            rule_multiple_users_same_ip,
            rule_new_device_for_user,
            rule_impossible_travel,
            rule_rapid_applications,
            rule_duplicate_identity,
            rule_rapid_document_uploads,
        )

        signals: List[Signal] = []

        # Only run rules relevant to the context (still keep them cheap)
        try:
            if context in ('login', 'auth'):
                s = rule_velocity_login_failures(ip_address, email)
                if s:
                    signals.append(s)
                s = rule_multiple_users_same_ip(ip_address)
                if s:
                    signals.append(s)
                if user:
                    s = rule_new_device_for_user(user, device_fingerprint)
                    if s:
                        signals.append(s)
                    s = rule_impossible_travel(user, ip_address)
                    if s:
                        signals.append(s)

            if context in ('loan_apply', 'kyc', 'document_upload') and user:
                s = rule_rapid_applications(user)
                if s:
                    signals.append(s)
                s = rule_rapid_document_uploads(user)
                if s:
                    signals.append(s)
                s = rule_duplicate_identity(user)
                if s:
                    signals.append(s)
        except Exception as e:
            logger.exception("Fraud rule evaluation error: %s", e)

        risk = RiskScorer.combine(signals)

        # ------------------------------------------------------------------
        # Persist the SecurityEvent
        # ------------------------------------------------------------------
        event = SecurityEvent.objects.create(
            user_id=str(user.id) if user else None,
            ip_address=ip_address or None,
            user_agent=user_agent or '',
            event_type=f'fraud_{context}',
            risk_score=risk.score,
            severity=risk.severity,
            description=(
                '; '.join(s['message'] for s in risk.signals) or 'No signals'
            ),
            action_taken=risk.action_taken,
        )

        # ------------------------------------------------------------------
        # Optional AI advisory
        #
        # The AI is only consulted for medium+ risk. Its output is stored
        # as advisory — it never changes the risk score or the action.
        # ------------------------------------------------------------------
        ai_analysis = None
        if (
            run_ai
            and risk.score
            >= settings.SECURITY_CONFIG['RISK_SCORE_THRESHOLDS']['medium']
        ):
            try:
                from apps.ai.services import AIService
                provider = getattr(settings, 'AI_DEFAULT_PROVIDER', 'glm')
                ai_record = AIService.run_analysis(
                    provider,
                    [{
                        'event': context,
                        'score': risk.score,
                        'signals': risk.signals,
                    }],
                    'general',
                    input_ref=str(event.id),
                )
                if ai_record:
                    ai_analysis = ai_record.output_data
            except Exception as e:
                logger.warning("AI advisory failed: %s", e)

        # ------------------------------------------------------------------
        # Create a FraudAlert for medium+ severity
        # ------------------------------------------------------------------
        if risk.severity in ('medium', 'high', 'critical'):
            FraudAlert.objects.create(
                user_id=str(user.id) if user else None,
                source_event=event,
                alert_type=f'fraud_{context}',
                risk_score=risk.score,
                severity=risk.severity,
                summary=(
                    '; '.join(s['message'] for s in risk.signals)
                )[:255] or 'Suspicious activity',
                details=risk.to_dict(),
                signals=risk.signals,
                ai_analysis=ai_analysis,
            )

        # ------------------------------------------------------------------
        # Apply automated response
        # ------------------------------------------------------------------
        AutoResponseEngine.apply(risk, user=user, ip_address=ip_address)

        # ------------------------------------------------------------------
        # Track/update device fingerprint if provided
        # ------------------------------------------------------------------
        if user and device_fingerprint:
            UserDevice.objects.update_or_create(
                user=user,
                fingerprint=device_fingerprint,
                defaults={
                    'user_agent': user_agent or '',
                    'last_ip': ip_address or None,
                },
            )

        return risk


# ----------------------------------------------------------------------
# Login attempt logging (used by rules engine)
# ----------------------------------------------------------------------
def record_login_attempt(
    user,
    email: str,
    ip_address: str,
    user_agent: str,
    success: bool,
    reason: str = '',
):
    """Log every login attempt — used by the rules engine."""
    LoginAttempt.objects.create(
        user=user,
        email=email or '',
        ip_address=ip_address or None,
        user_agent=user_agent or '',
        success=success,
        failure_reason=reason or '',
    )