from apps.security.models import SecurityEvent

def create_security_event(*, request, event_type, severity="LOW", risk_score=0, reason="", action_taken="LOG", user=None, metadata=None):
    return SecurityEvent.objects.create(
        user=user if user is not None else (request.user if request.user.is_authenticated else None),
        ip_address=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:4000],
        event_type=event_type,
        severity=severity,
        risk_score=max(0, min(100, risk_score)),
        reason=reason,
        action_taken=action_taken,
        metadata=metadata or {},
    )
