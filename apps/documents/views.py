"""Views for document management."""
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.audit.services import AuditService

from .models import Document
from .serializers import DocumentSerializer, DocumentUploadSerializer
from .permissions import IsDocumentOwner
from .services import DocumentService


class DocumentViewSet(viewsets.ModelViewSet):
    """API endpoints for document upload and retrieval."""
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated, IsDocumentOwner]
    parser_classes = [MultiPartParser, FormParser]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Document.objects.none()
        user = self.request.user
        if not user.is_authenticated:
            return Document.objects.none()
        if (user.is_superuser
                or user.has_role('Administrator')
                or user.has_role('Credit Officer')):
            return Document.objects.all()
        return Document.objects.filter(client=user)

    def get_serializer_class(self):
        if self.action == 'create':
            return DocumentUploadSerializer
        return DocumentSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        file_obj = serializer.validated_data['file']
        document_type = serializer.validated_data['document_type']

        try:
            document = DocumentService.upload_document(
                client=request.user,
                file_obj=file_obj,
                document_type=document_type,
                uploaded_by=request.user,
                ip_address=request.META.get('REMOTE_ADDR'),
            )
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        output_serializer = DocumentSerializer(document)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """Return the actual file content (private)."""
        document = self.get_object()
        if document.client != request.user and not (
            request.user.has_role('Administrator')
            or request.user.has_role('Credit Officer')
        ):
            return Response({'detail': 'Not allowed.'}, status=403)

        if document.status != 'approved':
            return Response({'detail': 'Document not approved.'}, status=403)

        version = document.versions.order_by('-version_number').first()
        if not version:
            return Response({'detail': 'No file version found.'}, status=404)

        try:
            file_obj = default_storage.open(version.storage_key, 'rb')
        except FileNotFoundError:
            raise Http404("File not found")

        response = FileResponse(file_obj, content_type=document.mime_type)
        response['Content-Disposition'] = (
            f'attachment; filename="{document.original_filename}"'
        )

        document.access_count += 1
        document.last_accessed_at = timezone.now()
        document.save(update_fields=['access_count', 'last_accessed_at', 'updated_at'])

        AuditService.record(
            actor=request.user,
            action='document_downloaded',
            object_type='document',
            object_id=str(document.id),
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        return response


class DocumentReviewViewSet(viewsets.ReadOnlyModelViewSet):
    """Staff-facing review of submitted documents."""
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Document.objects.none()
        user = self.request.user
        if not user.is_authenticated:
            return Document.objects.none()
        if not (
            user.is_superuser
            or user.has_role('Administrator')
            or user.has_role('Credit Officer')
            or user.has_role('Compliance Officer')
        ):
            return Document.objects.none()

        qs = Document.objects.select_related('client', 'reviewed_by').order_by('-created_at')
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        else:
            qs = qs.filter(status='submitted')
        return qs

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        from apps.kyc.services import DocumentReviewService
        doc = self.get_object()
        try:
            DocumentReviewService.approve(
                doc, request.user,
                notes=request.data.get('notes', ''),
                ip_address=request.META.get('REMOTE_ADDR'),
            )
        except ValueError as e:
            return Response({'detail': str(e)}, status=400)
        return Response(DocumentSerializer(doc).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        from apps.kyc.services import DocumentReviewService
        doc = self.get_object()
        try:
            DocumentReviewService.reject(
                doc, request.user,
                notes=request.data.get('notes', ''),
                ip_address=request.META.get('REMOTE_ADDR'),
            )
        except ValueError as e:
            return Response({'detail': str(e)}, status=400)
        return Response(DocumentSerializer(doc).data)