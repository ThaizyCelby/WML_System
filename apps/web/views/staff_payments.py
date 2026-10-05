"""Staff views: retry queue + collection tracking window."""
from datetime import datetime, date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.loans.models import Loan
from apps.payments.models import PaymentTransaction
from apps.payments.services import PaymentService


def _staff_allowed(user):
    return (
        user.is_superuser
        or user.has_role('Administrator')
        or user.has_role('Credit Officer')
        or user.has_role('Finance Officer')
        or user.has_role('Collections Officer')
    )


@login_required
def retry_queue(request):
    """List failed debits awaiting retry, plus those already scheduled."""
    if not _staff_allowed(request.user):
        return redirect('portal_dashboard')

    # Pending retries (scheduled, not yet attempted)
    scheduled = PaymentTransaction.objects.filter(
        status='failed',
        next_retry_at__isnull=False,
    ).select_related('loan', 'loan__client', 'retry_scheduled_by').order_by('next_retry_at')

    # Failed, no retry scheduled yet
    awaiting = PaymentTransaction.objects.filter(
        status='failed',
        next_retry_at__isnull=True,
    ).select_related('loan', 'loan__client').order_by('-created_at')[:100]

    return render(request, 'staff/payments/retry_queue.html', {
        'scheduled': scheduled,
        'awaiting': awaiting,
        'today': date.today(),
    })


@require_POST
@login_required
def retry_schedule(request, txn_id):
    """Schedule a retry for a failed debit."""
    if not _staff_allowed(request.user):
        return redirect('portal_dashboard')

    txn = get_object_or_404(PaymentTransaction, id=txn_id)

    retry_date_str = (request.POST.get('retry_at') or '').strip()
    undisputable = request.POST.get('undisputable') == 'on'
    reason = (request.POST.get('reason') or '').strip()

    if not retry_date_str:
        messages.error(request, 'Please choose a retry date.')
        return redirect('staff_retry_queue')

    try:
        # Accept date or datetime-local
        if 'T' in retry_date_str:
            retry_at = timezone.make_aware(datetime.fromisoformat(retry_date_str))
        else:
            d = date.fromisoformat(retry_date_str)
            retry_at = timezone.make_aware(datetime.combine(d, datetime.min.time().replace(hour=9)))
    except ValueError:
        messages.error(request, 'Invalid retry date.')
        return redirect('staff_retry_queue')

    if retry_at <= timezone.now():
        messages.error(request, 'Retry date must be in the future.')
        return redirect('staff_retry_queue')

    try:
        PaymentService.schedule_retry(
            txn,
            request.user,
            retry_at=retry_at,
            undisputable=undisputable,
            reason=reason,
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        messages.success(request, f'Retry scheduled for {retry_at.strftime("%Y-%m-%d %H:%M")}.')
    except ValueError as e:
        messages.error(request, str(e))

    return redirect('staff_retry_queue')


@require_POST
@login_required
def retry_cancel(request, txn_id):
    """Cancel a scheduled retry."""
    if not _staff_allowed(request.user):
        return redirect('portal_dashboard')

    txn = get_object_or_404(PaymentTransaction, id=txn_id)
    try:
        PaymentService.cancel_retry(
            txn,
            request.user,
            reason=request.POST.get('reason', ''),
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        messages.success(request, 'Retry cancelled.')
    except ValueError as e:
        messages.error(request, str(e))

    return redirect('staff_retry_queue')


@require_POST
@login_required
def loan_set_collection_window(request, loan_id):
    """Set (or update) the collection tracking window for a loan."""
    if not _staff_allowed(request.user):
        return redirect('portal_dashboard')

    loan = get_object_or_404(Loan, id=loan_id)

    try:
        start = int(request.POST.get('collection_window_start') or 0)
        end = int(request.POST.get('collection_window_end') or 0)
        max_retries = int(request.POST.get('max_retry_attempts') or 3)
    except (ValueError, TypeError):
        messages.error(request, 'Please enter valid day numbers.')
        return redirect('staff_application_detail', application_id=loan.application_id)

    if not (1 <= start <= 31 and 1 <= end <= 31):
        messages.error(request, 'Days must be between 1 and 31.')
        return redirect('staff_application_detail', application_id=loan.application_id)

    if end < start:
        start, end = end, start

    if not (0 <= max_retries <= 10):
        messages.error(request, 'Max retry attempts must be between 0 and 10.')
        return redirect('staff_application_detail', application_id=loan.application_id)

    loan.collection_window_start = start
    loan.collection_window_end = end
    loan.max_retry_attempts = max_retries
    loan.save(update_fields=[
        'collection_window_start', 'collection_window_end',
        'max_retry_attempts', 'updated_at',
    ])

    messages.success(
        request,
        f'Collection window set: day {start}–{end} of each month (max {max_retries} retries).'
    )
    return redirect('staff_application_detail', application_id=loan.application_id)