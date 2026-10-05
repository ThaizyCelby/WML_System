"""Audit log views."""
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only viewset for audit logs."""
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['action', 'object_type', 'actor_email', 'created_at']
    search_fields = ['actor_email', 'action', 'object_type', 'object_id', 'description']
    ordering_fields = ['created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return AuditLog.objects.none()
        user = self.request.user
        if not user.is_authenticated:
            return AuditLog.objects.none()
        # Only superusers and auditors can view audit logs
        if user.is_superuser or user.has_role('Auditor'):
            return AuditLog.objects.all()
        # Other users can only see their own audit trail
        return AuditLog.objects.filter(actor_id=str(user.id))