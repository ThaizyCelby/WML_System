from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import BankStatement, BankTransaction
from .serializers import (
    BankStatementSerializer,
    BankTransactionSerializer,
    BankStatementUploadSerializer,
)
from .services import BankStatementService


class BankStatementViewSet(viewsets.ModelViewSet):
    """Endpoints for uploading and viewing bank statements."""
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return BankStatement.objects.none()
        user = self.request.user
        if not user.is_authenticated:
            return BankStatement.objects.none()
        if (user.is_superuser
                or user.has_role('Administrator')
                or user.has_role('Credit Officer')):
            return BankStatement.objects.all()
        return BankStatement.objects.filter(client=user)

    def get_serializer_class(self):
        if self.action == 'create':
            return BankStatementUploadSerializer
        return BankStatementSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document_id = serializer.validated_data['document_id']
        bank_name = serializer.validated_data.get('bank_name', '')
        account_masked = serializer.validated_data.get('account_number_masked', '')

        from apps.documents.models import Document
        document = Document.objects.get(id=document_id, client=request.user)

        statement = BankStatement.objects.create(
            client=request.user,
            document=document,
            bank_name=bank_name,
            account_number_masked=account_masked,
            processing_status='pending',
        )

        # Process synchronously for now; in production use Celery
        BankStatementService.process_statement(statement)

        output = BankStatementSerializer(statement)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def analyze(self, request, pk=None):
        """Trigger AI analysis on a bank statement."""
        statement = self.get_object()
        if statement.processing_status != 'completed':
            return Response({'detail': 'Statement not fully processed yet.'}, status=400)

        payday, debt = BankStatementService.analyze_with_ai(statement)
        return Response({
            'payday_analysis': payday.output_data if payday else None,
            'payday_provider': payday.provider if payday else None,
            'debt_analysis': debt.output_data if debt else None,
            'debt_provider': debt.provider if debt else None,
        })

    @action(detail=True, methods=['get'])
    def transactions(self, request, pk=None):
        """List all transactions for a statement."""
        statement = self.get_object()
        tx_qs = BankTransaction.objects.filter(statement=statement)
        serializer = BankTransactionSerializer(tx_qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def spending(self, request, pk=None):
        """Return deterministic spending summary for a statement."""
        statement = self.get_object()
        if statement.processing_status != 'completed':
            return Response({'detail': 'Statement not yet processed.'}, status=400)
        summary = BankStatementService.summarize_spending(statement)
        return Response(summary)