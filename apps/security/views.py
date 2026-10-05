"""Security views."""
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.audit.services import AuditService

from .models import (
    BlockedIP,
    FraudAlert,
    LoginAttempt,
    SecurityEvent,
    UserDevice,
)
from .serializers import (
    BlockedIPSerializer,
    FraudAlertSerializer,
    LoginAttemptSerializer,
    SecurityEventSerializer,
    UserDeviceSerializer,
)


class SecurityEventViewSet(viewsets.ReadOnlyModelViewSet):
    """Viewset for security events."""
    serializer_class = SecurityEventSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['event_type', 'severity', 'risk_score', 'resolution', 'created_at']
    search_fields = ['ip_address', 'description', 'event_type']
    ordering_fields = ['created_at', 'risk_score']
    ordering = ['-created_at']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return SecurityEvent.objects.none()
        user = self.request.user
        if not user.is_authenticated:
            return SecurityEvent.objects.none()
        if (user.is_superuser
                or user.has_role('Auditor')
                or user.has_role('Administrator')):
            return SecurityEvent.objects.all()
        return SecurityEvent.objects.filter(user_id=str(user.id))

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """Resolve a security event."""
        event = self.get_object()
        event.resolution = request.data.get('resolution', 'resolved')
        event.reviewed_by = request.user
        event.reviewed_at = timezone.now()
        event.save(update_fields=[
            'resolution', 'reviewed_by', 'reviewed_at', 'updated_at',
        ])

        AuditService.record(
            actor=request.user,
            action='security_event_resolved',
            object_type='security_event',
            object_id=str(event.id),
            description=f'Event resolved as {event.resolution}',
        )

        return Response({'status': 'success'})


class BlockedIPViewSet(viewsets.ModelViewSet):
    """Viewset for managing blocked IPs."""
    serializer_class = BlockedIPSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['is_active', 'created_at']
    search_fields = ['ip_address', 'reason']
    ordering_fields = ['created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return BlockedIP.objects.none()
        user = self.request.user
        if not user.is_authenticated:
            return BlockedIP.objects.none()
        if user.is_superuser or user.has_role('Administrator'):
            return BlockedIP.objects.all()
        return BlockedIP.objects.none()

    def perform_create(self, serializer):
        ip_entry = serializer.save(created_by=self.request.user)
        AuditService.record(
            actor=self.request.user,
            action='ip_blocked',
            object_type='blocked_ip',
            object_id=str(ip_entry.id),
            description=f'IP {ip_entry.ip_address} blocked manually',
        )


class FraudAlertViewSet(viewsets.ModelViewSet):
    """Staff-facing triage of fraud alerts."""
    serializer_class = FraudAlertSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'patch', 'post', 'head', 'options']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return FraudAlert.objects.none()
        user = self.request.user
        if not user.is_authenticated:
            return FraudAlert.objects.none()
        allowed = (
            user.is_superuser
            or user.has_role('Administrator')
            or user.has_role('Compliance Officer')
            or user.has_role('Credit Officer')
        )
        if not allowed:
            return FraudAlert.objects.none()

        qs = FraudAlert.objects.all()
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        severity = self.request.query_params.get('severity')
        if severity:
            qs = qs.filter(severity=severity)
        return qs.order_by('-created_at')

    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        alert = self.get_object()
        alert.assigned_to = request.user
        alert.status = 'investigating'
        alert.save(update_fields=['assigned_to', 'status', 'updated_at'])
        AuditService.record(
            actor=request.user,
            action='fraud_alert_assigned',
            object_type='fraud_alert',
            object_id=str(alert.id),
            description='Fraud alert assigned for investigation',
        )
        return Response(FraudAlertSerializer(alert).data)

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        alert = self.get_object()
        alert.status = request.data.get('status', 'resolved')
        alert.reviewed_by = request.user
        alert.reviewed_at = timezone.now()
        alert.resolution_notes = request.data.get('notes', '')
        alert.action_taken = request.data.get('action_taken', '')
        alert.save(update_fields=[
            'status', 'reviewed_by', 'reviewed_at',
            'resolution_notes', 'action_taken', 'updated_at',
        ])
        AuditService.record(
            actor=request.user,
            action='fraud_alert_resolved',
            object_type='fraud_alert',
            object_id=str(alert.id),
            after_value={'status': alert.status, 'notes': alert.resolution_notes},
        )
        return Response(FraudAlertSerializer(alert).data)

    @action(detail=True, methods=['post'])
    def escalate(self, request, pk=None):
        alert = self.get_object()
        alert.status = 'escalated'
        alert.reviewed_by = request.user
        alert.reviewed_at = timezone.now()
        alert.resolution_notes = request.data.get('notes', '')
        alert.save(update_fields=[
            'status', 'reviewed_by', 'reviewed_at',
            'resolution_notes', 'updated_at',
        ])
        AuditService.record(
            actor=request.user,
            action='fraud_alert_escalated',
            object_type='fraud_alert',
            object_id=str(alert.id),
            description='Fraud alert escalated',
        )
        return Response(FraudAlertSerializer(alert).data)


class UserDeviceViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = UserDeviceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return UserDevice.objects.none()
        user = self.request.user
        if not user.is_authenticated:
            return UserDevice.objects.none()
        if user.is_superuser or user.has_role('Administrator'):
            return UserDevice.objects.all()
        return UserDevice.objects.filter(user=user)


class LoginAttemptViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = LoginAttemptSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return LoginAttempt.objects.none()
        user = self.request.user
        if not user.is_authenticated:
            return LoginAttempt.objects.none()
        if user.is_superuser or user.has_role('Administrator'):
            return LoginAttempt.objects.all()
        return LoginAttempt.objects.filter(user=user)