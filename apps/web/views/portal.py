"""Client portal views: dashboard, loans, payments, documents, notifications."""
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST


@login_required
def dashboard(request):
    """
    Client dashboard.

    Optimised: single pass over loans, single notification count, profile
    completeness computed once.
    """
    from django.core.cache import cache
    from django.db.models import Sum
    from apps.accounts.completeness import get_profile_gaps
    from apps.kyc.services import get_missing_documents
    from apps.loans.models import Loan
    from apps.notifications.models import Notification
    from apps.repayments.models import RepaymentSchedule

    user = request.user

    # ── Loans — single query with all the aggregates we need ────────
    loans_qs = (
        Loan.objects
        .filter(client=user)
        .select_related('product')
        .order_by('-created_at')
    )
    # Force evaluation once — reuse the list everywhere else
    loans = list(loans_qs)
    active_loans_count = sum(1 for l in loans if l.status != 'paid')
    total_outstanding = sum((l.outstanding_balance or 0) for l in loans)

    # ── Upcoming payments — single query, 5 rows ────────────────────
    upcoming_payments = list(
        RepaymentSchedule.objects
        .filter(
            loan__client=user,
            status__in=['pending', 'partial', 'overdue'],
        )
        .select_related('loan')
        .order_by('scheduled_date')[:5]
    )

    # ── Notification count — cached for 30 seconds ──────────────────
    cache_key = f"unread_count:{user.id}"
    unread_count = cache.get(cache_key)
    if unread_count is None:
        unread_count = Notification.objects.filter(
            user=user, status='sent', read_at__isnull=True,
        ).count()
        cache.set(cache_key, unread_count, timeout=30)

    # ── Profile completeness — computed once, reused ────────────────
    profile_gaps = get_profile_gaps(user)
    profile_complete = not profile_gaps

    # ── Documents — cached for 60 seconds (invalidated on upload) ───
    docs_key = f"missing_docs:{user.id}"
    missing_documents = cache.get(docs_key)
    if missing_documents is None:
        missing_documents = get_missing_documents(user)
        cache.set(docs_key, missing_documents, timeout=60)

    return render(request, 'client/dashboard.html', {
        'loans': loans,
        'active_loans_count': active_loans_count,
        'upcoming_payments': upcoming_payments,
        'total_outstanding': total_outstanding,
        'unread_count': unread_count,
        'missing_documents': missing_documents,
        'profile_complete': profile_complete,
        'profile_gaps': profile_gaps,
    })


@login_required
def loan_list(request):
    from apps.loans.models import Loan, LoanApplication

    loans = (
        Loan.objects
        .filter(client=request.user)
        .select_related('product')
        .order_by('-created_at')
    )
    applications = (
        LoanApplication.objects
        .filter(client=request.user)
        .exclude(status__in=['active', 'paid', 'cancelled'])
        .select_related('product')
        .order_by('-created_at')
    )
    return render(request, 'client/loans/list.html', {
        'loans': loans,
        'applications': applications,
    })


@login_required
def loan_detail(request, loan_id):
    from apps.loans.models import Loan, LoanApplication

    # The URL kwarg is named "loan_id" but historically the view has been used
    # for both Loan and LoanApplication IDs. Try Loan first, fall back to the
    # application's draft state so the client can still see their in-flight
    # application even before a Loan row exists.
    loan = Loan.objects.filter(id=loan_id, client=request.user).select_related(
        'product', 'application'
    ).first()

    if loan is not None:
        schedule = loan.repayment_schedule.order_by('period_number')
        agreement = getattr(loan, 'agreement', None)
        mandate = loan.debit_instructions.first()
        return render(request, 'client/loans/detail.html', {
            'loan': loan,
            'application': loan.application,
            'schedule': schedule,
            'agreement': agreement,
            'mandate': mandate,
        })

    # No Loan yet — try as an application id (draft / submitted applications
    # are visible from the client's loan list page).
    application = LoanApplication.objects.filter(
        id=loan_id, client=request.user,
    ).select_related('product').first()

    if application is None:
        raise Http404

    return render(request, 'client/loans/application_detail.html', {
        'application': application,
    })


@login_required
def loan_schedule(request, loan_id):
    from apps.loans.models import Loan

    loan = get_object_or_404(Loan, id=loan_id, client=request.user)
    return render(request, 'client/loans/_schedule.html', {
        'loan': loan,
        'schedule': loan.repayment_schedule.order_by('period_number'),
    })


@login_required
def payments_list(request):
    from apps.repayments.models import Repayment

    payments = (
        Repayment.objects
        .filter(loan__client=request.user)
        .select_related('loan')
        .order_by('-actual_date')
    )
    return render(request, 'client/payments/list.html', {'payments': payments})


@login_required
def documents_list(request):
    from apps.documents.models import Document

    docs = (
        Document.objects
        .filter(client=request.user)
        .prefetch_related('replacement_requests')
        .order_by('-created_at')
    )
    return render(request, 'client/documents/list.html', {'documents': docs})


@login_required
def notifications_list(request):
    from apps.notifications.models import Notification

    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')
    unread_count = notifications.filter(status='sent', read_at__isnull=True).count()
    return render(request, 'client/notifications/list.html', {
        'notifications': notifications,
        'unread_count': unread_count,
    })


@require_POST
@login_required
def notification_mark_read(request, notification_id):
    from apps.notifications.models import Notification

    n = get_object_or_404(Notification, id=notification_id, user=request.user)
    n.read_at = timezone.now()
    n.status = 'read'
    n.save(update_fields=['read_at', 'status', 'updated_at'])
    return HttpResponse(status=204)