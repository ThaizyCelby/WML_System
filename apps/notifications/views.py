from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Notification, NotificationPreference
from .serializers import NotificationSerializer, NotificationPreferenceSerializer


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Notification.objects.none()
        user = self.request.user
        if not user.is_authenticated:
            return Notification.objects.none()
        return Notification.objects.filter(user=user).order_by('-created_at')

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        count = Notification.objects.filter(
            user=request.user, status='sent', read_at__isnull=True,
        ).count()
        return Response({'unread': count})

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        from django.utils import timezone
        notification = self.get_object()
        notification.read_at = timezone.now()
        notification.status = 'read'
        notification.save(update_fields=['read_at', 'status', 'updated_at'])
        return Response(NotificationSerializer(notification).data)

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        from django.utils import timezone
        updated = Notification.objects.filter(
            user=request.user, read_at__isnull=True,
        ).update(read_at=timezone.now(), status='read')
        return Response({'updated': updated})


class NotificationPreferenceViewSet(viewsets.ViewSet):
    """Read/update the caller's notification preferences."""
    serializer_class = NotificationPreferenceSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id='notification_preferences_retrieve',
        responses={200: NotificationPreferenceSerializer},
    )
    def list(self, request):
        pref, _ = NotificationPreference.objects.get_or_create(user=request.user)
        return Response(NotificationPreferenceSerializer(pref).data)

    @extend_schema(
        operation_id='notification_preferences_update',
        request=NotificationPreferenceSerializer,
        responses={200: NotificationPreferenceSerializer},
    )
    def create(self, request):
        pref, _ = NotificationPreference.objects.get_or_create(user=request.user)
        serializer = NotificationPreferenceSerializer(
            pref, data=request.data, partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)