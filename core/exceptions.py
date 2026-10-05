"""Custom exceptions and error handling for Wethu Micro Lenders."""
import logging
from rest_framework.views import exception_handler

logger = logging.getLogger('apps')


def custom_exception_handler(exc, context):
    """Custom DRF exception handler that ensures safe error responses."""
    response = exception_handler(exc, context)

    if response is not None:
        # Preserve original validation errors if present
        if isinstance(response.data, dict):
            detail = response.data.get('detail', 'An error occurred.')
            errors = response.data
        else:
            detail = 'An error occurred.'
            errors = None

        response.data = {
            'status': 'error',
            'code': 'validation_error' if response.status_code == 400 else 'error',
            'detail': detail,
            'errors': errors,
        }

        request = context.get('request')
        user_email = 'anonymous'
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            user_email = request.user.email

        logger.warning(
            'API error: %s | endpoint: %s | user: %s | status: %s',
            response.data.get('code'),
            request.path if request else 'unknown',
            user_email,
            response.status_code,
        )
    return response
