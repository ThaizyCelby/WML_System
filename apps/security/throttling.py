"""Custom throttling classes for security-sensitive endpoints."""
from rest_framework.throttling import SimpleRateThrottle, ScopedRateThrottle as DRFScopedRateThrottle


class LoginRateThrottle(SimpleRateThrottle):
    """Throttle for login attempts - 3 per 15 minutes."""
    scope = 'login'

    def get_cache_key(self, request, view):
        ip = request.META.get('REMOTE_ADDR', '0.0.0.0')
        return f"throttle_login_{ip}"


class RegistrationRateThrottle(SimpleRateThrottle):
    """Throttle for registration - 5 per hour."""
    scope = 'registration'

    def get_cache_key(self, request, view):
        ip = request.META.get('REMOTE_ADDR', '0.0.0.0')
        return f"throttle_registration_{ip}"


class FileUploadRateThrottle(SimpleRateThrottle):
    """Throttle for file uploads."""
    scope = 'file_upload'

    def get_cache_key(self, request, view):
        user_id = request.user.id if request.user.is_authenticated else 'anonymous'
        return f"throttle_upload_{user_id}"


class SecuritySensitiveRateThrottle(SimpleRateThrottle):
    """Throttle for security-sensitive operations."""
    scope = 'security_sensitive'

    def get_cache_key(self, request, view):
        user_id = request.user.id if request.user.is_authenticated else 'anonymous'
        return f"throttle_security_{user_id}"


class ScopedRateThrottle(DRFScopedRateThrottle):
    """Scoped rate throttle with custom cache key generation."""

    def get_cache_key(self, request, view):
        if not hasattr(view, 'throttle_scope'):
            return None

        ident = self.get_ident(request)
        scope = getattr(view, 'throttle_scope')
        return f"throttle_scoped_{scope}_{ident}"
