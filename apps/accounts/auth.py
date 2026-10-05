"""Custom authentication backend."""
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

from .models import User


class EmailBackend(ModelBackend):
    """Authentication backend that supports login by email or phone number."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None

        try:
            # Try to find user by email or phone number
            user = User.objects.get(
                Q(email__iexact=username) | Q(phone_number=username)
            )
        except User.DoesNotExist:
            # Run password hasher to prevent timing attacks
            User().set_password(password)
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

    def user_can_authenticate(self, user):
        """Check if the user is active and not locked."""
        if not user.is_active:
            return False
        if user.is_locked:
            return False
        return True
