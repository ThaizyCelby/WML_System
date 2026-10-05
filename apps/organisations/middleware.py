"""Tenant middleware — attaches request.organisation."""
import logging

logger = logging.getLogger('apps.organisations')


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from .services import OrganisationService
        request.organisation = OrganisationService.resolve_for_request(request)
        return self.get_response(request)