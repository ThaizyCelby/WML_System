"""Security middleware: rate limiting, security headers, event recording."""
import logging
import time

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone

from .models import BlockedIP
from .services import SecurityEventService

logger = logging.getLogger('apps.security')


class RateLimitMiddleware:
    """
    Middleware for IP-based rate limiting and blocked-IP enforcement.

    Order matters:
      1. Blocked-IP check runs first (hard deny).
      2. Rate-limit check runs second (soft throttle).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip rate limiting for health endpoints
        if request.path.startswith(('/health', '/readiness', '/liveness', '/metrics')):
            return self.get_response(request)

        ip_address = self._get_client_ip(request)

        # 1. Blocked-IP enforcement (checks the database)
        if self._is_ip_blocked(ip_address):
            logger.warning("Request blocked: IP on denylist %s", ip_address)
            return JsonResponse(
                {'status': 'error', 'detail': 'Access temporarily blocked.'},
                status=429,
            )

        # 2. Rate-limit check (uses Redis cache)
        if not self._check_rate_limit(ip_address):
            SecurityEventService.record(
                event_type='rate_limit_exceeded',
                ip_address=ip_address,
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                risk_score=30,
                severity='medium',
                description=f'Rate limit exceeded from {ip_address}',
            )
            return JsonResponse(
                {'status': 'error', 'detail': 'Too many requests. Please try again later.'},
                status=429,
            )

        return self.get_response(request)

    @staticmethod
    def _get_client_ip(request):
        """Extract the real client IP, accounting for proxies."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '0.0.0.0')

    @staticmethod
    def _is_ip_blocked(ip_address):
        """
        Check if an IP address is currently blocked.

        SECURITY: Uses the database (BlockedIP table), not the cache, so
        blocks set by the fraud engine or by staff are enforced
        immediately and survive a Redis restart.
        """
        return BlockedIP.objects.filter(
            ip_address=ip_address,
            is_active=True,
            blocked_until__gt=timezone.now(),
        ).exists()

    @staticmethod
    def _check_rate_limit(ip_address):
        """Check rate limit for an IP address."""
        window = 60           # 1 minute window
        max_requests = 120    # 120 requests per minute
        cache_key = f"rate_limit:{ip_address}:{int(time.time() / window)}"

        try:
            count = cache.get(cache_key, 0)
            if count >= max_requests:
                return False
            cache.set(cache_key, count + 1, timeout=window)
            return True
        except Exception:
            # If Redis is down, allow the request but log it.
            logger.error('Rate limiting cache unavailable')
            return True


class SecurityEventMiddleware:
    """
    Lightweight middleware that can be extended to auto-record security
    events on suspicious responses. Currently a pass-through.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)


class SecurityHeadersMiddleware:
    """Set HTTP security headers on every response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        response['X-Content-Type-Options'] = 'nosniff'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'

        if not settings.DEBUG:
            response['Content-Security-Policy'] = self._build_csp()

        return response

    @staticmethod
    def _build_csp():
        """Build the Content-Security-Policy header."""
        csp = settings.CSP_DEFAULT_SRC
        return (
            f"default-src {' '.join(csp)}; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
        )