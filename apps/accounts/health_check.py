"""Health check endpoints for Wethu Micro Lenders."""
from django.db import connection
from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone


def health_check(request):
    return JsonResponse({
        'status': 'healthy',
        'service': 'wethu-api',
        'timestamp': timezone.now().isoformat(),
    })


def readiness_check(request):
    """Readiness check - verify database and cache connectivity."""
    checks = {
        'database': _check_database(),
        'cache': _check_cache(),
    }

    is_ready = all(checks.values())

    return JsonResponse(
        {
            'status': 'ready' if is_ready else 'not_ready',
            'checks': checks,
            'timestamp': timezone.now().isoformat(),
        },
        status=200 if is_ready else 503,
    )


def liveness_check(request):
    """Liveness check - simplest possible."""
    return JsonResponse({'status': 'alive'})


def _check_database() -> bool:
    """Check database connectivity."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        return True
    except Exception:
        return False


def _check_cache() -> bool:
    """Check Redis cache connectivity."""
    try:
        cache.set('_health_check', 'ok', timeout=5)
        return cache.get('_health_check') == 'ok'
    except Exception:
        return False
