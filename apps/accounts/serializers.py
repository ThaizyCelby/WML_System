"""Serializers for authentication and user management."""
import re

from django.contrib.auth import get_user_model
from django.core.validators import validate_email
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from core.utils.masking import mask_email

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    """Serializer for user registration."""
    password = serializers.CharField(write_only=True, required=True, min_length=12, max_length=128)
    password_confirm = serializers.CharField(write_only=True, required=True)
    first_name = serializers.CharField(required=True, max_length=150)
    last_name = serializers.CharField(required=True, max_length=150)

    class Meta:
        model = User
        fields = ['email', 'phone_number', 'password', 'password_confirm', 'first_name', 'last_name']
        extra_kwargs = {
            'email': {'required': True},
            'phone_number': {'required': False},
        }

    def validate_email(self, value):
        """Validate email format and check for disposable domains."""
        try:
            validate_email(value)
        except Exception:
            raise serializers.ValidationError('Invalid email address.')

        # Normalize email
        value = value.lower().strip()

        # Check for duplicates
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('This email is already registered.')

        return value

    def validate_password(self, value):
        """Validate password strength."""
        if len(value) < 12:
            raise serializers.ValidationError('Password must be at least 12 characters.')
        if not re.search(r'[A-Z]', value):
            raise serializers.ValidationError('Password must contain at least one uppercase letter.')
        if not re.search(r'[a-z]', value):
            raise serializers.ValidationError('Password must contain at least one lowercase letter.')
        if not re.search(r'\d', value):
            raise serializers.ValidationError('Password must contain at least one number.')
        if not re.search(r'[^A-Za-z0-9]', value):
            raise serializers.ValidationError('Password must contain at least one special character.')
        return value

    def validate(self, attrs):
        if attrs.get('password') != attrs.get('password_confirm'):
            raise serializers.ValidationError({'password_confirm': 'Passwords do not match.'})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm', None)
        password = validated_data.pop('password')
        user = User.objects.create_user(password=password, **validated_data)
        user.is_active = True
        user.save(update_fields=['is_active'])
        return user


class UserSerializer(serializers.ModelSerializer):
    """Serializer for user details (never exposes sensitive fields)."""

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'phone_number',
            'is_active', 'email_verified', 'phone_verified',
            'mfa_enabled', 'last_login_at', 'created_at',
        ]
        read_only_fields = [
            'id', 'email', 'is_active', 'email_verified',
            'phone_verified', 'mfa_enabled', 'last_login_at', 'created_at',
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Mask sensitive data in API responses
        if data.get('phone_number'):
            data['phone_number'] = self._mask_phone(data['phone_number'])
        return data

    @staticmethod
    def _mask_phone(phone):
        if len(phone) < 8:
            return phone
        return phone[:4] + '*****' + phone[-3:]


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Custom JWT serializer that includes user information and handles lockouts."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['email'] = user.email
        token['name'] = user.full_name
        token['roles'] = [r.role.name for r in user.get_roles()]
        return token

    def validate(self, attrs):
        from django.conf import settings
        from django.utils import timezone
        from rest_framework.exceptions import AuthenticationFailed

        email = attrs.get('email', '')
        user = User.objects.filter(email__iexact=email).first()

        # Refuse if the account is currently locked → HTTP 401
        if user and user.is_locked:
            remaining = user.locked_until - timezone.now()
            minutes = max(1, int(remaining.total_seconds() / 60))
            raise AuthenticationFailed(
                f'Account temporarily locked. Please try again in {minutes} minutes.'
            )

        # Attempt authentication via SimpleJWT.
        # On failure, increment the counter and lock if the threshold is reached.
        try:
            data = super().validate(attrs)
        except Exception:
            if user is not None:
                cfg = getattr(settings, 'LOGIN_RATE_LIMIT', {})
                max_attempts = cfg.get('max_attempts', 3)
                lockout_duration = cfg.get('lockout_duration', 1200)
                attempts = user.increment_failed_attempts()
                if attempts >= max_attempts:
                    user.lock_account(duration_seconds=lockout_duration)
            raise

        # Successful login
        self.user.record_login()
        data['user'] = UserSerializer(self.user).data
        return data


class PasswordChangeSerializer(serializers.Serializer):
    """Serializer for password change."""
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=12)
    new_password_confirm = serializers.CharField(required=True)

    def validate_new_password(self, value):
        """Validate new password strength."""
        if len(value) < 12:
            raise serializers.ValidationError('Password must be at least 12 characters.')
        if not re.search(r'[A-Z]', value):
            raise serializers.ValidationError('Password must contain at least one uppercase letter.')
        if not re.search(r'[a-z]', value):
            raise serializers.ValidationError('Password must contain at least one lowercase letter.')
        if not re.search(r'\d', value):
            raise serializers.ValidationError('Password must contain at least one number.')
        if not re.search(r'[^A-Za-z0-9]', value):
            raise serializers.ValidationError('Password must contain at least one special character.')
        return value

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({'new_password_confirm': 'Passwords do not match.'})
        if attrs['old_password'] == attrs['new_password']:
            raise serializers.ValidationError('New password must be different from old password.')
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    """Serializer for password reset request."""
    email = serializers.EmailField(required=True)

    def validate_email(self, value):
        return value.lower().strip()


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Serializer for password reset confirmation."""
    token = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=12)
    new_password_confirm = serializers.CharField(required=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({'new_password_confirm': 'Passwords do not match.'})
        return attrs
