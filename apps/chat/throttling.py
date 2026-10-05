"""Chat-specific throttles."""
from django.core.exceptions import ImproperlyConfigured
from rest_framework.throttling import SimpleRateThrottle


class ChatbotThrottle(SimpleRateThrottle):
    scope = 'chatbot'

    def get_rate(self):
        """Return the configured rate, or None to disable throttling if unset."""
        try:
            return self.THROTTLE_RATES[self.scope]
        except (KeyError, ImproperlyConfigured, AttributeError):
            return None

    def get_cache_key(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return self.get_ident(request)
        return f"throttle_chatbot_{request.user.id}"
