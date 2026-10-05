"""Business logic services for authentication and user management."""
import hashlib
import logging
import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone

from apps.audit.services import AuditService

logger = logging.getLogger('apps.accounts')
User = get_user_model()

PASSWORD_HISTORY_SIZE = 5
RESET_TOKEN_TTL = 3600  # 1 hour


class AuthService:
    """Service for authentication-related business logic."""

    @staticmethod
    def change_password(user: User, new_password: str) -> None:
        """Change user password with history checking."""
        # Check password history
        if AuthService._is_in_password_history(user, new_password):
            raise ValueError('Password has been used recently. Please choose a different password.')

        # Add current password to history before changing
        AuthService._add_to_password_history(user, user.password)

        # Set new password
        user.set_password(new_password)
        user.save(update_fields=['password', 'password_history', 'updated_at'])

    @staticmethod
    def _is_in_password_history(user: User, new_password: str) -> bool:
        """Check if the password matches any in the history."""
        if not user.password_history:
            return False

        history_hashes = user.password_history.split(',')
        new_hash = hashlib.sha256(new_password.encode()).hexdigest()
        return new_hash in history_hashes

    @staticmethod
    def _add_to_password_history(user: User, password_hash: str) -> None:
        """Add a password hash to the history."""
        hashes = []
        if user.password_history:
            hashes = user.password_history.split(',')

        # Add hash of the current password (we can't store the raw hash, just a marker)
        current_hash = hashlib.sha256(password_hash.encode()).hexdigest()
        hashes.insert(0, current_hash)

        # Keep only the last N hashes
        user.password_history = ','.join(hashes[:PASSWORD_HISTORY_SIZE])

    @staticmethod
    def check_and_record_login(user: User, password: str) -> bool:
        """Check password and handle failed attempt counting."""
        if user.is_locked:
            return False

        if user.check_password(password):
            user.record_login()
            return True

        # Increment failed attempts
        attempts = user.increment_failed_attempts()

        # Check if we should lock the account
        from django.conf import settings
        max_attempts = settings.LOGIN_RATE_LIMIT['max_attempts']
        lockout_duration = settings.LOGIN_RATE_LIMIT['lockout_duration']

        if attempts >= max_attempts:
            user.lock_account(lockout_duration)
            logger.warning(
                'Account locked due to too many failed attempts: %s',
                user.email,
            )

        return False


class PasswordResetService:
    """Service for password reset functionality."""

    @staticmethod
    def create_reset_token(email: str) -> None:
        """Create and store a password reset token."""
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if not user:
            # Still return success to prevent user enumeration
            return

        token = secrets.token_urlsafe(32)
        cache_key = f"password_reset:{token}"
        cache.set(cache_key, str(user.id), timeout=RESET_TOKEN_TTL)

        # Send email (async in production)
        from apps.notifications.services import NotificationService
        NotificationService.send_password_reset_email(user, token)

    @staticmethod
    def confirm_reset(token: str, new_password: str) -> bool:
        """Confirm password reset with token."""
        cache_key = f"password_reset:{token}"
        user_id = cache.get(cache_key)

        if not user_id:
            return False

        user = User.objects.filter(id=user_id, is_active=True).first()
        if not user:
            return False

        # Change password
        AuthService.change_password(user, new_password)

        # Delete the token (single-use)
        cache.delete(cache_key)

        # Invalidate all sessions
        from django.contrib.auth import update_session_auth_hash
        update_session_auth_hash(None, user)

        # Audit log
        AuditService.record(
            actor=user,
            action='password_reset',
            object_type='user',
            object_id=str(user.id),
            description='Password reset via token',
        )

        return True
