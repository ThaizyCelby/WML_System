"""Views for KYC workflows, credit bureau, and document replacement."""
from rest_framework import viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import ClientProfile
from apps.documents.models import DocumentReplacementRequest

from .credit_bureau_service import CreditBureauService
from .credit_bureau.base import CreditBureauError, CreditBureauConsentRequired
from .models import KYCReview
from .permissions import CanReviewKYC, CanVerifyKYC
from .serializers import (
    ClientProfileKYCSerializer,
    CreditReportSerializer,
    DocumentReplacementRequestSerializer,
    KYCReviewSerializer,
)
from .services import DocumentReplacementService, KYCService


class KYCViewSet(viewsets.ReadOnlyModelViewSet):
    """Staff-facing KYC management."""
    serializer_class = ClientProfileKYCSerializer
    permission_classes = [IsAuthenticated, CanReviewKYC]
    queryset = ClientProfile.objects.select_related('user').all()
    filterset_fields = ['kyc_status', 'employment_type']
    search_fields = ['user__email', 'user__first_name', 'user__last_name', 'id_number']
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        profile = self.get_object()
        if profile.user != request.user and not request.user.has_role('Administrator'):
            return Response({'detail': 'Not allowed.'}, status=403)
        try:
            KYCService.submit_kyc(profile, request.user, request.META.get('REMOTE_ADDR'))
        except ValueError as e:
            return Response({'detail': str(e)}, status=400)
        return Response({'status': 'success'})

    @action(detail=True, methods=['post'], permission_classes=[CanReviewKYC])
    def start_review(self, request, pk=None):
        profile = self.get_object()
        KYCService.start_review(profile, request.user, request.META.get('REMOTE_ADDR'))
        return Response({'status': 'success'})

    # ── Verification actions require Compliance Officer ────────────
    @action(detail=True, methods=['post'], permission_classes=[CanVerifyKYC])
    def approve(self, request, pk=None):
        profile = self.get_object()
        KYCService.approve(
            profile, request.user, request.META.get('REMOTE_ADDR'),
            request.data.get('notes', ''),
        )
        return Response({'status': 'success'})

    @action(detail=True, methods=['post'], permission_classes=[CanVerifyKYC])
    def reject(self, request, pk=None):
        profile = self.get_object()
        KYCService.reject(
            profile, request.user, request.META.get('REMOTE_ADDR'),
            request.data.get('notes', ''),
        )
        return Response({'status': 'success'})

    @action(detail=True, methods=['post'], permission_classes=[CanVerifyKYC])
    def request_additional_info(self, request, pk=None):
        profile = self.get_object()
        KYCService.request_additional_info(
            profile, request.user, request.META.get('REMOTE_ADDR'),
            request.data.get('notes', ''),
        )
        return Response({'status': 'success'})

    @action(detail=True, methods=['post'], permission_classes=[CanVerifyKYC])
    def suspend(self, request, pk=None):
        profile = self.get_object()
        KYCService.suspend(
            profile, request.user, request.META.get('REMOTE_ADDR'),
            request.data.get('notes', ''),
        )
        return Response({'status': 'success'})

    @action(detail=True, methods=['get'], permission_classes=[CanReviewKYC])
    def reviews(self, request, pk=None):
        profile = self.get_object()
        reviews = KYCReview.objects.filter(client_profile=profile)
        return Response(KYCReviewSerializer(reviews, many=True).data)


class DocumentReplacementRequestViewSet(viewsets.ReadOnlyModelViewSet):
    """Staff-facing list/triage of client document replacement requests."""
    serializer_class = DocumentReplacementRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not (
            user.is_superuser
            or user.has_role('Administrator')
            or user.has_role('Credit Officer')
            or user.has_role('Compliance Officer')
        ):
            return DocumentReplacementRequest.objects.none()

        qs = DocumentReplacementRequest.objects.select_related(
            'document', 'requested_by', 'reviewed_by',
        )
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs.order_by('-created_at')

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        req = self.get_object()
        try:
            DocumentReplacementService.approve_request(
                req, request.user,
                notes=request.data.get('notes', ''),
                ip_address=request.META.get('REMOTE_ADDR'),
            )
        except ValueError as e:
            return Response({'detail': str(e)}, status=400)
        return Response(DocumentReplacementRequestSerializer(req).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        req = self.get_object()
        try:
            DocumentReplacementService.reject_request(
                req, request.user,
                notes=request.data.get('notes', ''),
                ip_address=request.META.get('REMOTE_ADDR'),
            )
        except ValueError as e:
            return Response({'detail': str(e)}, status=400)
        return Response(DocumentReplacementRequestSerializer(req).data)


# ----------------------------------------------------------------------
# Client-facing: profile completeness + credit bureau
# ----------------------------------------------------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def profile_completeness(request):
    """
    Return whether the logged-in user's profile is complete enough to
    apply, along with a list of missing items.
    """
    from apps.accounts.completeness import get_profile_gaps, is_profile_complete
    return Response({
        'complete': is_profile_complete(request.user),
        'gaps': get_profile_gaps(request.user),
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def pull_credit_report(request):
    """
    Pull (or reuse a fresh) credit report for the logged-in client.

    Refuses with 400 if the client has not given consent (NCA + POPIA).
    Refuses with 503 if the bureau is unreachable or unconfigured.
    """
    try:
        report = CreditBureauService.pull_report(
            request.user,
            actor=request.user,
            ip_address=request.META.get('REMOTE_ADDR'),
        )
    except CreditBureauConsentRequired as e:
        return Response({'detail': str(e)}, status=400)
    except CreditBureauError as e:
        return Response({'detail': str(e)}, status=503)
    return Response(CreditReportSerializer(report).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def latest_credit_report(request):
    """
    Return the logged-in client's latest non-expired credit report.

    Never returns another user's report — scoped to request.user.
    """
    report = CreditBureauService.has_valid_report(request.user)
    if not report:
        return Response({'detail': 'No valid credit report on file.'}, status=404)
    return Response(CreditReportSerializer(report).data)