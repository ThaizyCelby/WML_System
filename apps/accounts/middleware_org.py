"""
Sets request.organisation from the authenticated user's organisation.
Also stores it in a thread-local so services can access it without
threading the user through every call.

No-op for anonymous users and superusers without an organisation.
"""
import logging

from .organisation_service import clear_current_org, set_current_org

logger = logging.getLogger('apps.accounts')


class OrganisationMiddleware:

    # URLs that must never require an organisation context.
    # Prefix match. Extend as needed.
    EXEMPT_PREFIXES = (
        '/login/',
        '/logout/',
        '/register/',
        '/password-reset/',
        '/mfa/',
        '/static/',
        '/media/',
        '/health/',
        '/readiness/',
        '/liveness/',
        '/metrics',
        '/admin/',
        '/django-admin/',
        '/api/v1/accounts/login',
        '/api/v1/accounts/register',
        '/api/v1/accounts/refresh',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        org = None
        user = getattr(request, 'user', None)

        if user and getattr(user, 'is_authenticated', False):
            org = getattr(user, 'organisation', None)

            # Refuse access for suspended organisations. Superusers without
            # an org are exempt (they operate across tenants).
            is_global_superuser = (
                getattr(user, 'is_superuser', False) and org is None
            )
            if org and org.is_suspended and not is_global_superuser:
                from django.http import HttpResponse
                if not self._is_exempt(request.path):
                    logger.warning(
                        'Request blocked: organisation %s is suspended',
                        org.slug,
                    )
                    return HttpResponse(
                        'This organisation account is suspended.',
                        status=403,
                    )

        request.organisation = org
        set_current_org(org)
        try:
            return self.get_response(request)
        finally:
            clear_current_org()

    @classmethod
    def _is_exempt(cls, path: str) -> bool:
        return any(path.startswith(p) for p in cls.EXEMPT_PREFIXES)
