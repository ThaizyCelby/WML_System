"""Enforce MFA verification after password login."""
from django.shortcuts import redirect


class MFAEnforcementMiddleware:
    """
    If a user is authenticated and has MFA enabled but hasn't verified this
    session, redirect to the challenge page.
    """

    EXEMPT_PREFIXES = (
        '/login/',
        '/logout/',
        '/mfa/',
        '/password-reset/',
        '/password-change/',
        '/static/',
        '/media/',
        '/health/',
        '/readiness/',
        '/liveness/',
        '/metrics',
        '/api/',          # API uses JWT; MFA enforced separately
        '/admin/',        # Django admin has its own protections
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._should_redirect(request):
            return redirect('mfa_challenge')
        return self.get_response(request)

    def _should_redirect(self, request) -> bool:
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False

        from .mfa_service import MFAService
        if not MFAService.user_requires_mfa(user):
            return False

        if request.session.get('mfa_verified'):
            return False

        path = request.path
        for prefix in self.EXEMPT_PREFIXES:
            if path.startswith(prefix):
                return False
        return True