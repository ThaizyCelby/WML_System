"""Template context shared across all pages."""
from django.conf import settings


def branding(request):
    return {
        'SITE_NAME': getattr(settings, 'SITE_NAME', 'Wethu Micro Lenders'),
        'SITE_SHORT_NAME': getattr(settings, 'SITE_SHORT_NAME', 'Wethu'),
        'SITE_DESCRIPTION': getattr(settings, 'SITE_DESCRIPTION', ''),
        'SITE_SUPPORT_EMAIL': getattr(settings, 'SITE_SUPPORT_EMAIL', ''),
        'SITE_SUPPORT_PHONE': getattr(settings, 'SITE_SUPPORT_PHONE', ''),
        'SITE_COMPANY_REG': getattr(settings, 'SITE_COMPANY_REG', ''),
    }

def notifications_context(request):
    """Inject unread notification count into every template (cached)."""
    if not request.user.is_authenticated:
        return {'unread_count': 0}

    from django.core.cache import cache
    cache_key = f"unread_count:{request.user.id}"
    count = cache.get(cache_key)
    if count is None:
        try:
            from apps.notifications.models import Notification
            count = Notification.objects.filter(
                user=request.user, status='sent', read_at__isnull=True,
            ).count()
        except Exception:
            count = 0
        cache.set(cache_key, count, timeout=30)
    return {'unread_count': count}
