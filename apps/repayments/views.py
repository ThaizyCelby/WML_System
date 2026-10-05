from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import RepaymentSchedule, Repayment
from .serializers import RepaymentScheduleSerializer, RepaymentSerializer


class RepaymentScheduleViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = RepaymentScheduleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return RepaymentSchedule.objects.none()
        user = self.request.user
        if not user.is_authenticated:
            return RepaymentSchedule.objects.none()
        if (user.is_superuser
                or user.has_role('Administrator')
                or user.has_role('Credit Officer')):
            return RepaymentSchedule.objects.all()
        return RepaymentSchedule.objects.filter(loan__client=user)


class RepaymentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = RepaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Repayment.objects.none()
        user = self.request.user
        if not user.is_authenticated:
            return Repayment.objects.none()
        if (user.is_superuser
                or user.has_role('Administrator')
                or user.has_role('Credit Officer')):
            return Repayment.objects.all()
        return Repayment.objects.filter(loan__client=user)