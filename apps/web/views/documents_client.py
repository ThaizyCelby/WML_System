"""Client document upload views."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.audit.services import AuditService
from apps.documents.models import Document
from apps.documents.services import DocumentService


DOCUMENT_TYPES = [
    ('identity_document', 'Identity document (ID or passport)'),
    ('proof_of_address', 'Proof of address'),
    ('payslip', 'Latest payslip'),
    ('bank_statement', 'Bank statement (3 months)'),
    ('employment_confirmation', 'Employment confirmation'),
    ('other', 'Other supporting document'),
]


@login_required
def upload(request):
    # Pre-fill for replacement
    replace_id = request.GET.get('replace')
    preset_type = request.GET.get('type', '')
    replacing = None
    if replace_id:
        from apps.documents.models import Document
        replacing = Document.objects.filter(
            id=replace_id, client=request.user,
        ).first()

    if request.method == 'POST':
        file_obj = request.FILES.get('file')
        document_type = request.POST.get('document_type')

        if not file_obj or not document_type:
            messages.error(request, 'Please select a document type and a file.')
            return redirect('client_document_upload')

        try:
            doc = DocumentService.upload_document(
                client=request.user,
                file_obj=file_obj,
                document_type=document_type,
                uploaded_by=request.user,
                ip_address=request.META.get('REMOTE_ADDR'),
            )
            messages.success(
                request,
                f'{"Replaced" if replacing else "Uploaded"} {doc.original_filename}. '
                'We will verify it shortly.'
            )
            return redirect('client_document_list')
        except Exception as e:
            messages.error(request, f'Upload failed: {e}')
            return redirect('client_document_upload')

    return render(request, 'client/documents/upload.html', {
        'document_types': DOCUMENT_TYPES,
        'replacing': replacing,
        'preset_type': preset_type,
    })


@login_required
def reextract(request, document_id):
    """Manually trigger OCR/ID extraction on an identity document."""
    from apps.documents.models import Document
    from apps.kyc.ocr_service import extract_identity_from_document

    doc = get_object_or_404(Document, id=document_id, client=request.user)
    result = extract_identity_from_document(doc)

    if result and result.get('id_number'):
        messages.success(
            request,
            f"Extracted ID: {result['id_number']} "
            f"(source: {result.get('source')}, confidence: {result.get('confidence')})."
        )
    else:
        messages.warning(
            request,
            "Could not extract an ID number from this document. "
            "Please ensure the image is clear and well-lit."
        )
    return redirect('client_document_list')


@login_required
def download(request, document_id):
    doc = get_object_or_404(Document, id=document_id, client=request.user)
    if doc.status != 'approved':
        raise Http404
    latest = doc.versions.order_by('-version_number').first()
    if not latest:
        raise Http404

    try:
        file_obj = default_storage.open(latest.storage_key, 'rb')
    except FileNotFoundError:
        raise Http404

    AuditService.record(
        actor=request.user,
        action='document_downloaded',
        object_type='document',
        object_id=str(doc.id),
        ip_address=request.META.get('REMOTE_ADDR'),
    )
    response = FileResponse(file_obj, content_type=doc.mime_type)
    response['Content-Disposition'] = f'attachment; filename="{doc.original_filename}"'
    return response

@login_required
def request_replacement(request, document_id):
    """Client requests permission to replace an approved document."""
    from apps.documents.models import Document, DocumentReplacementRequest

    doc = get_object_or_404(Document, id=document_id, client=request.user)

    if doc.status != 'approved':
        messages.error(request, 'Only approved documents require a replacement request.')
        return redirect('client_document_list')

    if request.method == 'POST':
        reason = (request.POST.get('reason') or '').strip()
        req = DocumentReplacementRequest.objects.create(
            document=doc, requested_by=request.user, reason=reason,
        )
        messages.success(
            request,
            'Replacement request submitted. A staff member will review it shortly.',
        )
        return redirect('client_document_list')

    return render(request, 'client/documents/request_replacement.html', {'document': doc})


@login_required
def request_replacement_cancel(request, request_id):
    """Client cancels their own pending replacement request."""
    from apps.documents.models import DocumentReplacementRequest
    req = get_object_or_404(
        DocumentReplacementRequest,
        id=request_id, requested_by=request.user, status='pending',
    )
    if request.method == 'POST':
        req.status = 'rejected'
        req.review_notes = 'Cancelled by client'
        req.save(update_fields=['status', 'review_notes', 'updated_at'])
        messages.info(request, 'Replacement request cancelled.')
    return redirect('client_document_list')