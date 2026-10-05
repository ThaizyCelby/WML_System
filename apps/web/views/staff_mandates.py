"""Staff views for reviewing and activating debit-order mandates."""
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.audit.services import AuditService
from apps.payments.models import DebitInstruction

logger = logging.getLogger('apps.web')


# ──────────────────────────────────────────────────────────────────────
# Access control — self-contained so this module has no dependency on
# staff.py internals (avoids circular import risk).
# ──────────────────────────────────────────────────────────────────────
CREDIT_ROLES = ('Administrator', 'Credit Officer')
FINANCE_ROLES = ('Administrator', 'Finance Officer')


def _has_any(user, roles) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return any(user.has_role(r) for r in roles)


def _guard(request, roles):
    """Return None if the user is allowed; otherwise a redirect to the portal."""
    if _has_any(request.user, roles):
        return None
    messages.error(request, 'You do not have permission to access mandates.')
    return redirect('portal_dashboard')


# ──────────────────────────────────────────────────────────────────────
# Mandate review queue
# ──────────────────────────────────────────────────────────────────────
@login_required
def mandate_review_list(request):
    """
    Staff mandate review queue.

    Filters:
      ?status=<pending_review|active|rejected|all>
      Default: pending_review
      ?status=all shows every mandate.
    """
    g = _guard(request, CREDIT_ROLES + FINANCE_ROLES)
    if g:
        return g

    qs = (
        DebitInstruction.objects
        .select_related('loan', 'loan__client', 'created_by', 'reviewed_by')
        .order_by('-created_at')
    )

    status_filter = (request.GET.get('status') or 'pending_review').strip()

    if status_filter == 'all':
        pass
    elif status_filter:
        qs = qs.filter(status=status_filter)
    else:
        qs = qs.filter(status='pending_review')

    page = Paginator(qs, 25).get_page(request.GET.get('page'))

    # Small counters for the tabs
    counters = {
        'pending_review': DebitInstruction.objects.filter(status='pending_review').count(),
        'active': DebitInstruction.objects.filter(status='active').count(),
        'rejected': DebitInstruction.objects.filter(status='rejected').count(),
        'all': DebitInstruction.objects.count(),
    }

    return render(request, 'staff/mandates/list.html', {
        'page': page,
        'status_filter': status_filter,
        'counters': counters,
    })


# ──────────────────────────────────────────────────────────────────────
# Mandate detail / review
# ──────────────────────────────────────────────────────────────────────
@login_required
def mandate_review_detail(request, mandate_id):
    """Show a single mandate for staff review."""
    g = _guard(request, CREDIT_ROLES + FINANCE_ROLES)
    if g:
        return g

    mandate = get_object_or_404(
        DebitInstruction.objects.select_related(
            'loan', 'loan__client', 'created_by', 'reviewed_by',
        ),
        id=mandate_id,
    )

    return render(request, 'staff/mandates/detail.html', {
        'mandate': mandate,
    })


# ──────────────────────────────────────────────────────────────────────
# Approve / activate
# ──────────────────────────────────────────────────────────────────────
@require_POST
@login_required
def mandate_approve(request, mandate_id):
    """Approve and activate a mandate."""
    g = _guard(request, CREDIT_ROLES + FINANCE_ROLES)
    if g:
        return g

    mandate = get_object_or_404(DebitInstruction, id=mandate_id)

    if mandate.status != 'pending_review':
        messages.error(
            request,
            f'Only mandates in "pending review" can be approved. '
            f'This one is "{mandate.get_status_display()}".',
        )
        return redirect('staff_mandate_detail', mandate_id=mandate.id)

    notes = (request.POST.get('notes') or '')[:1000]

    mandate.status = 'active'
    mandate.is_active = True
    mandate.reviewed_by = request.user
    mandate.reviewed_at = timezone.now()
    mandate.review_notes = notes
    mandate.save(update_fields=[
        'status', 'is_active', 'reviewed_by', 'reviewed_at',
        'review_notes', 'updated_at',
    ])

    AuditService.record(
        actor=request.user,
        action='mandate_approved',
        object_type='debit_instruction',
        object_id=str(mandate.id),
        ip_address=request.META.get('REMOTE_ADDR'),
        after_value={'status': 'active', 'notes': notes},
    )

    messages.success(request, 'Mandate activated.')

    # Notify the client
    try:
        from apps.notifications.services import NotificationService
        NotificationService.dispatch(
            mandate.loan.client,
            'mandate_approved',
            context={
                'name': mandate.loan.client.full_name or mandate.loan.client.email,
                'loan_id': str(mandate.loan_id)[:8].upper(),
            },
            channels=['email', 'in_app'],
        )
    except Exception:
        logger.exception('Failed to notify client about mandate approval')

    return redirect('staff_mandate_detail', mandate_id=mandate.id)


# ──────────────────────────────────────────────────────────────────────
# Reject
# ──────────────────────────────────────────────────────────────────────
@require_POST
@login_required
def mandate_reject(request, mandate_id):
    """Reject a pending mandate."""
    g = _guard(request, CREDIT_ROLES + FINANCE_ROLES)
    if g:
        return g

    mandate = get_object_or_404(DebitInstruction, id=mandate_id)

    if mandate.status not in ('pending_review', 'pending_client'):
        messages.error(
            request,
            f'Only pending mandates can be rejected. '
            f'This one is "{mandate.get_status_display()}".',
        )
        return redirect('staff_mandate_detail', mandate_id=mandate.id)

    reason = (request.POST.get('reason') or request.POST.get('notes') or '').strip()[:1000]
    if not reason:
        messages.error(request, 'Please provide a rejection reason.')
        return redirect('staff_mandate_detail', mandate_id=mandate.id)

    mandate.status = 'rejected'
    mandate.is_active = False
    mandate.reviewed_by = request.user
    mandate.reviewed_at = timezone.now()
    mandate.rejection_reason = reason
    mandate.save(update_fields=[
        'status', 'is_active', 'reviewed_by', 'reviewed_at',
        'rejection_reason', 'updated_at',
    ])

    AuditService.record(
        actor=request.user,
        action='mandate_rejected',
        object_type='debit_instruction',
        object_id=str(mandate.id),
        ip_address=request.META.get('REMOTE_ADDR'),
        after_value={'status': 'rejected', 'reason': reason},
    )

    messages.success(request, 'Mandate rejected.')

    # Notify the client
    try:
        from apps.notifications.services import NotificationService
        NotificationService.dispatch(
            mandate.loan.client,
            'mandate_rejected',
            context={
                'name': mandate.loan.client.full_name or mandate.loan.client.email,
                'loan_id': str(mandate.loan_id)[:8].upper(),
                'reason': reason,
            },
            channels=['email', 'in_app'],
        )
    except Exception:
        logger.exception('Failed to notify client about mandate rejection')

    return redirect('staff_mandate_detail', mandate_id=mandate.id)


# ──────────────────────────────────────────────────────────────────────
# Download mandate PDF
# ──────────────────────────────────────────────────────────────────────
@login_required
def mandate_download(request, mandate_id):
    """Stream the signed mandate PDF to the browser (staff-side)."""
    g = _guard(request, CREDIT_ROLES + FINANCE_ROLES + ('Compliance Officer', 'Auditor'))
    if g:
        return g

    mandate = get_object_or_404(DebitInstruction, id=mandate_id)

    if not mandate.mandate_pdf_storage_key:
        raise Http404

    try:
        file_obj = default_storage.open(mandate.mandate_pdf_storage_key, 'rb')
    except FileNotFoundError:
        raise Http404

    AuditService.record(
        actor=request.user,
        action='staff_mandate_download',
        object_type='debit_instruction',
        object_id=str(mandate.id),
        ip_address=request.META.get('REMOTE_ADDR'),
    )

    response = FileResponse(file_obj, content_type='application/pdf')
    filename = (
        f"mandate-{mandate.mandate_reference_number or str(mandate.id)[:8]}.pdf"
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response