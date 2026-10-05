"""Authentication views for Wethu Micro Lenders."""
import logging

from django.contrib.auth import get_user_model
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.audit.services import AuditService
from apps.security.services import SecurityEventService
from apps.security.throttling import LoginRateThrottle, RegistrationRateThrottle

from .models import User
from .serializers import (
    CustomTokenObtainPairSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserSerializer,
)
from .services import AuthService, PasswordResetService

logger = logging.getLogger('apps.accounts')
User = get_user_model()


class RegisterView(APIView):
    """User registration endpoint."""
    permission_classes = [AllowAny]
    throttle_classes = [RegistrationRateThrottle]

    @extend_schema(
        operation_id='auth_register',
        request=RegisterSerializer,
        responses={201: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        AuditService.record(
            actor=user,
            action='user_registered',
            object_type='user',
            object_id=str(user.id),
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )

        SecurityEventService.record(
            user=user,
            event_type='registration',
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            risk_score=0,
            severity='low',
            description='New user registration',
        )

        return Response(
            {
                'status': 'success',
                'message': 'Registration successful. Please verify your email.',
                'user': UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    """Custom login view with rate limiting."""
    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = [LoginRateThrottle]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            # NOTE: at this point the request is not yet authenticated (the JWT
            # has just been minted). self.request.user will be AnonymousUser.
            # Fixing this requires the serializer to return the user in
            # response.data; leave for the auth-hardening pass.
            AuditService.record(
                actor=self.request.user if hasattr(self.request, 'user') else None,
                action='login',
                object_type='user',
                object_id=str(self.request.user.id) if hasattr(self.request, 'user') else None,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
            )
        else:
            email = request.data.get('email', 'unknown')
            SecurityEventService.record(
                event_type='failed_login',
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                risk_score=40,
                severity='medium',
                description=f'Failed login attempt for {email}',
            )

        return response


class RefreshTokenView(TokenRefreshView):
    """Custom refresh token view."""
    pass


class LogoutView(APIView):
    """Logout endpoint that blacklists the refresh token."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id='auth_logout',
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
        except Exception:
            pass

        AuditService.record(
            actor=request.user,
            action='logout',
            object_type='user',
            object_id=str(request.user.id),
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )

        return Response({'status': 'success', 'message': 'Logged out successfully.'})


class PasswordChangeView(APIView):
    """Password change endpoint."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id='auth_password_change',
        request=PasswordChangeSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user

        if not user.check_password(serializer.validated_data['old_password']):
            return Response(
                {'status': 'error', 'detail': 'Current password is incorrect.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        AuthService.change_password(user, serializer.validated_data['new_password'])

        AuditService.record(
            actor=user,
            action='password_changed',
            object_type='user',
            object_id=str(user.id),
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )

        return Response({'status': 'success', 'message': 'Password changed successfully.'})


class PasswordResetRequestView(APIView):
    """Request password reset."""
    permission_classes = [AllowAny]
    throttle_classes = [RegistrationRateThrottle]

    @extend_schema(
        operation_id='auth_password_reset_request',
        request=PasswordResetRequestSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        PasswordResetService.create_reset_token(email)

        # Always return success (don't leak if email exists)
        return Response(
            {
                'status': 'success',
                'message': 'If the email exists, a password reset link has been sent.',
            }
        )


class PasswordResetConfirmView(APIView):
    """Confirm password reset with token."""
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id='auth_password_reset_confirm',
        request=PasswordResetConfirmSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        success = PasswordResetService.confirm_reset(
            serializer.validated_data['token'],
            serializer.validated_data['new_password'],
        )

        if not success:
            return Response(
                {'status': 'error', 'detail': 'Invalid or expired reset token.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({'status': 'success', 'message': 'Password reset successfully.'})


class UserProfileViewSet(viewsets.ModelViewSet):
    """User profile management."""
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        # Users can only access their own profile
        return User.objects.filter(id=self.request.user.id)

    def get_object(self):
        return self.request.user

    def perform_update(self, serializer):
        user = serializer.save()
        AuditService.record(
            actor=self.request.user,
            action='profile_updated',
            object_type='user',
            object_id=str(user.id),
            ip_address=self.request.META.get('REMOTE_ADDR'),
            user_agent=self.request.META.get('HTTP_USER_AGENT', ''),
        )