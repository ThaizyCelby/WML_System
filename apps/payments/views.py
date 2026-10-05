"""Views for payments."""
import logging

from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import DebitInstruction, PaymentTransaction, ReconciliationRecord
from .serializers import (
    DebitInstructionSerializer,
    PaymentTransactionSerializer,
    ReconciliationRecordSerializer,
)
from .services import PaymentService
from .tasks import run_reconciliation, submit_due_debits, poll_pending_transactions

logger = logging.getLogger('apps.payments')


class PaymentTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PaymentTransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return PaymentTransaction.objects.none()

        user = self.request.user
        if not user.is_authenticated:
            return PaymentTransaction.objects.none()

        if (user.is_superuser
                or user.has_role('Finance Officer')
                or user.has_role('Administrator')):
            return PaymentTransaction.objects.all()
        return PaymentTransaction.objects.filter(loan__client=user)


class DebitInstructionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DebitInstructionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return DebitInstruction.objects.none()

        user = self.request.user
        if not user.is_authenticated:
            return DebitInstruction.objects.none()

        if user.is_superuser or user.has_role('Administrator'):
            return DebitInstruction.objects.all()
        return DebitInstruction.objects.filter(loan__client=user)


class ReconciliationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ReconciliationRecordSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ReconciliationRecord.objects.none()

        user = self.request.user
        if not user.is_authenticated:
            return ReconciliationRecord.objects.none()

        if (user.is_superuser
                or user.has_role('Finance Officer')
                or user.has_role('Administrator')):
            return ReconciliationRecord.objects.all()
        return ReconciliationRecord.objects.filter(loan__client=user)

    @extend_schema(
        operation_id='payments_reconciliation_run',
        request=None,
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=['post'], url_path='run')
    def run(self, request):
        """Trigger a full reconciliation run (admin only)."""
        if not (request.user.is_superuser
                or request.user.has_role('Finance Officer')):
            return Response({'detail': 'Not allowed.'}, status=403)
        task = run_reconciliation.delay()
        return Response({'task_id': task.id, 'status': 'queued'})


# -- Webhook endpoint (public, signature-verified) --------------------
@extend_schema(
    operation_id='payments_webhook',
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.OBJECT},
    description=(
        'Payment provider webhook. Public endpoint — authenticity is enforced '
        'via HMAC signature verification inside PaymentService.handle_webhook.'
    ),
)
@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def payment_webhook(request):
    provider_name = request.query_params.get('provider', 'mock')
    raw_body = request.body
    signature = (
        request.headers.get('X-Signature')
        or request.headers.get('X-NuPay-Signature')
        or ''
    )
    try:
        webhook = PaymentService.handle_webhook(
            provider_name, request.data, signature, raw_body,
        )
    except ValueError as e:
        return Response({'detail': str(e)}, status=400)
    except Exception as e:
        logger.exception("Webhook failed: %s", e)
        return Response(
            {'detail': 'Webhook processing failed'}, status=500,
        )
    return Response({
        'status': 'received',
        'webhook_id': str(webhook.id),
        'processed': webhook.processed,
    })