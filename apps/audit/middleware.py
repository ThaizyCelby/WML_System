"""Audit logging middleware."""
import uuid
import logging

from core.utils.logging import correlation_id_var

logger = logging.getLogger('apps.audit')


class AuditLogMiddleware:
    """
    Middleware that adds correlation IDs to all requests and logs API calls.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Generate correlation ID
        correlation_id = request.META.get('HTTP_X_CORRELATION_ID') or uuid.uuid4().hex[:16]
        request.correlation_id = correlation_id

        # Set the global context variable for logging
        correlation_id_var.set(correlation_id)

        response = self.get_response(request)

        # Add correlation ID to response headers
        response['X-Correlation-ID'] = correlation_id

        return response
