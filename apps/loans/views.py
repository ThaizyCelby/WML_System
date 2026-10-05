from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404

from .models import LoanApplication, LoanProduct, LoanApplicationEvent, Loan, LoanAgreement
from .serializers import (
    LoanProductSerializer, LoanApplicationSerializer, LoanApplicationCreateSerializer,
    LoanApplicationEventSerializer, LoanSerializer, LoanAgreementSerializer,
)
from .permissions import IsClientOwner, CanReviewLoan
from .services import LoanApplicationService
from .interest_engine import calculate_total_repayment
from .agreement_service import LoanAgreementService


class LoanProductViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = LoanProductSerializer
    permission_classes = [IsAuthenticated]
    queryset = LoanProduct.objects.filter(is_active=True)


class LoanApplicationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsClientOwner]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_queryset(self):
        # Schema generation (drf-spectacular) uses a fake view with AnonymousUser.
        if getattr(self, 'swagger_fake_view', False):
            return LoanApplication.objects.none()

        user = self.request.user
        if not user.is_authenticated:
            return LoanApplication.objects.none()

        if (user.is_superuser
                or user.has_role('Administrator')
                or user.has_role('Credit Officer')):
            return LoanApplication.objects.all()
        return LoanApplication.objects.filter(client=user)

    def get_serializer_class(self):
        if self.action == 'create':
            return LoanApplicationCreateSerializer
        return LoanApplicationSerializer

    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        application = LoanApplicationService.create_application(
            client=request.user,
            product_id=s.validated_data['product_id'],
            amount=s.validated_data['amount'],
            term=s.validated_data['term'],
        )
        return Response(LoanApplicationSerializer(application).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        application = self.get_object()
        try:
            LoanApplicationService.submit_application(
                application, request.user, request.META.get('REMOTE_ADDR'),
            )
        except ValueError as e:
            return Response({'detail': str(e)}, status=400)
        return Response({'status': 'submitted'})

    @action(detail=True, methods=['post'], permission_classes=[CanReviewLoan])
    def transition(self, request, pk=None):
        application = self.get_object()
        to_status = request.data.get('to_status')
        notes = request.data.get('notes', '')
        try:
            LoanApplicationService.transition(
                application, to_status, request.user, notes,
                request.META.get('REMOTE_ADDR'),
            )
        except ValueError as e:
            return Response({'detail': str(e)}, status=400)
        return Response({'status': application.status})

    @action(detail=True, methods=['post'])
    def accept_agreement(self, request, pk=None):
        """Client accepts their loan agreement."""
        application = self.get_object()
        if application.client != request.user:
            return Response({'detail': 'Not allowed.'}, status=403)
        if application.status != 'contract_pending':
            return Response(
                {'detail': 'Application is not awaiting agreement acceptance.'},
                status=400,
            )
        loan = getattr(application, 'loan', None)
        if not loan or not hasattr(loan, 'agreement'):
            return Response({'detail': 'No agreement to accept.'}, status=400)
        LoanAgreementService.accept_agreement(
            loan.agreement, request.user,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )
        try:
            LoanApplicationService.transition(
                application, 'contract_accepted', request.user,
                'Agreement accepted by client', request.META.get('REMOTE_ADDR'),
            )
        except ValueError as e:
            return Response({'detail': str(e)}, status=400)
        return Response({'status': application.status})

    @action(detail=True, methods=['get'])
    def events(self, request, pk=None):
        application = self.get_object()
        events = LoanApplicationEvent.objects.filter(application=application)
        return Response(LoanApplicationEventSerializer(events, many=True).data)

    @action(detail=True, methods=['post'])
    def calculate_repayment(self, request, pk=None):
        application = self.get_object()
        if not application.product:
            return Response({'detail': 'No product associated.'}, status=400)
        result = calculate_total_repayment(
            principal=application.requested_amount,
            annual_rate=application.product.interest_rate,
            term_months=application.requested_term,
            interest_type=application.product.interest_type,
        )
        return Response(result)


class LoanViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = LoanSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Loan.objects.none()

        user = self.request.user
        if not user.is_authenticated:
            return Loan.objects.none()

        if (user.is_superuser
                or user.has_role('Administrator')
                or user.has_role('Credit Officer')):
            return Loan.objects.all()
        return Loan.objects.filter(client=user)

    @action(detail=True, methods=['get'])
    def schedule(self, request, pk=None):
        loan = self.get_object()
        from apps.repayments.serializers import RepaymentScheduleSerializer
        rows = loan.repayment_schedule.order_by('period_number')
        return Response(RepaymentScheduleSerializer(rows, many=True).data)

    @action(detail=True, methods=['get'])
    def agreement(self, request, pk=None):
        """Return metadata for the loan's agreement."""
        loan = self.get_object()
        agreement = getattr(loan, 'agreement', None)
        if not agreement:
            return Response({'detail': 'No agreement generated.'}, status=404)
        return Response(LoanAgreementSerializer(agreement).data)

    @action(detail=True, methods=['get'])
    def download_agreement(self, request, pk=None):
        """Stream the agreement PDF (private)."""
        loan = self.get_object()
        agreement = getattr(loan, 'agreement', None)
        if not agreement:
            raise Http404
        try:
            file_obj = default_storage.open(agreement.pdf_storage_key, 'rb')
        except FileNotFoundError:
            raise Http404
        response = FileResponse(file_obj, content_type='application/pdf')
        response['Content-Disposition'] = (
            f'attachment; filename="loan-agreement-{loan.id}.pdf"'
        )
        return response