import uuid
from apps.audit.models import AuditLog

def record_audit(*, request, action, actor=None, obj=None, before=None, after=None):
    meta = getattr(request, "META", {})
    ip = meta.get("REMOTE_ADDR")
    return AuditLog.objects.create(
        actor=actor or getattr(request, "user", None) if getattr(request, "user", None) and request.user.is_authenticated else actor,
        action=action,
        object_type=obj.__class__.__name__ if obj else "",
        object_id=str(getattr(obj, "pk", "")) if obj else "",
        ip_address=ip,
        user_agent=meta.get("HTTP_USER_AGENT", "")[:4000],
        correlation_id=uuid.uuid4(),
        before_data=before,
        after_data=after,
    )
