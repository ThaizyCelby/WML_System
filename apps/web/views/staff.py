"""Staff portal views: dashboard, review queues, portfolio, fraud, audit."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.db.models import Count, Sum, Q, Value
from django.db.models.functions import TruncDate, Coalesce
from django.http import FileResponse, Http404
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import User, ClientProfile, BankAccount
from apps.audit.models import AuditLog
from apps.documents.models import Document, DocumentReplacementRequest
from apps.kyc.models import KYCReview
from apps.kyc.services import DocumentReviewService, KYCService
from apps.loans.models import Loan, LoanApplication, LoanApplicationEvent, LoanProduct
from apps.loans.services import LoanApplicationService
from apps.payments.models import DebitInstruction, ReconciliationRecord, PaymentTransaction
from apps.repayments.models import RepaymentSchedule, Repayment
from apps.security.models import FraudAlert, SecurityEvent


# ──────────────────────────────────────────────────────────────────────
# Access control
# ──────────────────────────────────────────────────────────────────────
STAFF_ROLES = (
    'Administrator', 'Credit Officer', 'Finance Officer',
    'Collections Officer', 'Compliance Officer', 'Auditor',
)
CREDIT_ROLES = ('Administrator', 'Credit Officer')
FINANCE_ROLES = ('Administrator', 'Finance Officer')
COLLECTIONS_ROLES = ('Administrator', 'Collections Officer', 'Credit Officer')
COMPLIANCE_ROLES = ('Administrator', 'Compliance Officer', 'Auditor')


def _is_staff(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return any(user.has_role(r) for r in STAFF_ROLES)


def _has_any(user, roles):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return any(user.has_role(r) for r in roles)


def _guard(request, roles=None):
    user = request.user
    allowed = _is_staff(user) if roles is None else _has_any(user, roles)
    if not allowed:
        messages.error(request, 'You do not have permission to access the staff portal.')
        return redirect('portal_dashboard')
    return None


# ──────────────────────────────────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────────────────────────────────
@login_required
def dashboard(request):
    g = _guard(request)
    if g:
        return g

    today = date.today()

    apps_qs = LoanApplication.objects.all()
    in_review = apps_qs.filter(status__in=[
        'submitted', 'document_review', 'kyc_review',
        'affordability_review', 'credit_review',
    ]).count()
    apps_approved = apps_qs.filter(status__in=[
        'approved', 'contract_pending', 'contract_accepted',
        'disbursement_pending', 'active', 'paid',
    ]).count()
    apps_rejected = apps_qs.filter(status='rejected').count()

    loans_qs = Loan.objects.all()
    total_loans = loans_qs.count()
    active_loans = loans_qs.filter(status='active').count()
    overdue_loans = loans_qs.filter(status='overdue').count()
    outstanding = loans_qs.aggregate(
        s=Coalesce(Sum('outstanding_balance'), Value(Decimal('0')))
    )['s']

    docs_pending = Document.objects.filter(status='submitted').count()
    mandates_pending = DebitInstruction.objects.filter(status='pending_review').count()
    fraud_open = FraudAlert.objects.filter(status='open').count()
    security_critical = SecurityEvent.objects.filter(
        severity='critical',
        created_at__gte=timezone.now() - timedelta(days=7),
    ).count()
    recon_issues = ReconciliationRecord.objects.filter(
        created_at__gte=timezone.now() - timedelta(days=30),
    ).exclude(status='matched').count()

    recent_apps = (
        LoanApplication.objects
        .select_related('client', 'product')
        .order_by('-created_at')[:8]
    )

    since = today - timedelta(days=14)
    app_series = (
        LoanApplication.objects
        .filter(created_at__date__gte=since)
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(count=Count('id'))
        .order_by('day')
    )
    app_labels = [row['day'].strftime('%d %b') for row in app_series]
    app_values = [row['count'] for row in app_series]

    return render(request, 'staff/dashboard.html', {
        'in_review': in_review,
        'apps_approved': apps_approved,
        'apps_rejected': apps_rejected,
        'total_loans': total_loans,
        'active_loans': active_loans,
        'overdue_loans': overdue_loans,
        'outstanding': outstanding,
        'docs_pending': docs_pending,
        'mandates_pending': mandates_pending,
        'fraud_open': fraud_open,
        'security_critical': security_critical,
        'recon_issues': recon_issues,
        'recent_apps': recent_apps,
        'app_labels': app_labels,
        'app_values': app_values,
    })


# ──────────────────────────────────────────────────────────────────────
# Applications
# ──────────────────────────────────────────────────────────────────────
@login_required
def applications_list(request):
    g = _guard(request, CREDIT_ROLES)
    if g:
        return g

    qs = (
        LoanApplication.objects
        .select_related('client', 'product')
        .order_by('-created_at')
    )

    status_filter = request.GET.get('status', '')
    if status_filter:
        qs = qs.filter(status=status_filter)

    product_id = request.GET.get('product')
    if product_id:
        qs = qs.filter(product_id=product_id)

    search = request.GET.get('q', '').strip()
    if search:
        qs = qs.filter(
            Q(client__email__icontains=search) |
            Q(client__first_name__icontains=search) |
            Q(client__last_name__icontains=search)
        )

    page = Paginator(qs, 25).get_page(request.GET.get('page'))
    products = LoanProduct.objects.all().order_by('name')

    return render(request, 'staff/applications_list.html', {
        'page': page,
        'status_filter': status_filter,
        'product_filter': product_id,
        'search': search,
        'products': products,
        'statuses': LoanApplication._meta.get_field('status').choices,
    })


@login_required
def application_detail(request, application_id):
    g = _guard(request, CREDIT_ROLES)
    if g:
        return g

    application = get_object_or_404(
        LoanApplication.objects.select_related('client', 'product'),
        id=application_id,
    )

    try:
        profile = application.client.client_profile
    except ClientProfile.DoesNotExist:
        profile = None

    documents = (
        Document.objects
        .filter(client=application.client)
        .prefetch_related('versions', 'replacement_requests')
        .order_by('-created_at')
    )

    from apps.banking.models import BankStatement, BankTransaction
    statements = (
        BankStatement.objects
        .filter(client=application.client)
        .order_by('-created_at')
    )
    latest_statement = statements.first()
    transaction_summary = None
    if latest_statement:
        credits = BankTransaction.objects.filter(
            statement=latest_statement, transaction_type='credit',
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0')
        debits = BankTransaction.objects.filter(
            statement=latest_statement, transaction_type='debit',
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0')
        transaction_summary = {
            'credits': credits,
            'debits': debits,
            'net': credits - debits,
            'count': latest_statement.transactions.count(),
        }

    from apps.kyc.credit_bureau_service import CreditBureauService
    credit_report = CreditBureauService.has_valid_report(application.client)

    affordability = None
    if profile and application.product:
        try:
            from apps.loans.interest_engine import calculate_total_repayment
            from apps.affordability.engine import AffordabilityEngine

            calc = calculate_total_repayment(
                application.requested_amount,
                application.product.interest_rate,
                application.requested_term,
                application.product.interest_type,
            )
            installment = (
                calc['total_repayment'] / Decimal(application.requested_term)
            ).quantize(Decimal('0.01'))

            existing_debt = (
                credit_report.total_monthly_obligations
                if credit_report else profile.existing_debt_obligations
            )

            affordability = AffordabilityEngine.calculate(
                gross_income=profile.monthly_income,
                monthly_expenses=profile.monthly_expenses,
                existing_debt=existing_debt,
                proposed_repayment=installment,
            )
        except Exception:
            affordability = None

    events = (
        LoanApplicationEvent.objects
        .filter(application=application)
        .select_related('actor')
        .order_by('timestamp')
    )

    # Deterministic policy evaluation (pure function, no side effects)
    from apps.loans.policy_engine import evaluate as evaluate_policy
    try:
        policy_result = evaluate_policy(application, profile)
        application.policy_result = policy_result.to_dict()
        application.policy_evaluated_at = timezone.now()
        application.save(update_fields=['policy_result', 'policy_evaluated_at', 'updated_at'])
    except Exception:
        policy_result = None

    # Client's bank accounts (structured, post-backfill)
    bank_accounts = (
        BankAccount.objects
        .filter(client=application.client)
        .order_by('-is_primary', '-last_seen_at', '-created_at')
    )

    return render(request, 'staff/application_detail.html', {
        'application': application,
        'profile': profile,
        'documents': documents,
        'statements': statements,
        'latest_statement': latest_statement,
        'transaction_summary': transaction_summary,
        'affordability': affordability,
        'credit_report': credit_report,
        'events': events,
        'policy_result': policy_result,
        'bank_accounts': bank_accounts,
    })


@require_POST
@login_required
def application_transition(request, application_id):
    g = _guard(request, CREDIT_ROLES)
    if g:
        return g

    application = get_object_or_404(LoanApplication, id=application_id)
    to_status = (request.POST.get('to_status') or '').strip()
    notes = (request.POST.get('notes') or '').strip()[:500]

    try:
        LoanApplicationService.transition(
            application, to_status, request.user, notes,
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        messages.success(request, f'Application moved to {to_status}.')
    except ValueError as e:
        messages.error(request, str(e))

    return redirect('staff_application_detail', application_id=application.id)


@require_POST
@login_required
def application_mark_documents_reviewed(request, application_id):
    g = _guard(request, CREDIT_ROLES)
    if g:
        return g
    application = get_object_or_404(LoanApplication, id=application_id)
    reviewed = request.POST.get('reviewed', 'true') == 'true'
    LoanApplicationService.mark_documents_reviewed(
        application, request.user, reviewed=reviewed,
        ip_address=request.META.get('REMOTE_ADDR'),
    )
    messages.success(request, 'Documents marked as reviewed.')
    return redirect('staff_application_detail', application_id=application.id)


@require_POST
@login_required
def application_mark_transactions_reviewed(request, application_id):
    g = _guard(request, CREDIT_ROLES)
    if g:
        return g
    application = get_object_or_404(LoanApplication, id=application_id)
    reviewed = request.POST.get('reviewed', 'true') == 'true'
    LoanApplicationService.mark_transactions_reviewed(
        application, request.user, reviewed=reviewed,
        ip_address=request.META.get('REMOTE_ADDR'),
    )
    messages.success(request, 'Transactions marked as reviewed.')
    return redirect('staff_application_detail', application_id=application.id)


@require_POST
@login_required
def application_verify_contract(request, application_id):
    g = _guard(request, CREDIT_ROLES)
    if g:
        return g
    application = get_object_or_404(LoanApplication, id=application_id)
    try:
        LoanApplicationService.verify_contract(
            application, request.user,
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        messages.success(request, 'Contract verified.')
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('staff_application_detail', application_id=application.id)


# ──────────────────────────────────────────────────────────────────────
# KYC review queue
# ──────────────────────────────────────────────────────────────────────
@login_required
def kyc_list(request):
    g = _guard(request, COMPLIANCE_ROLES)
    if g:
        return g

    qs = ClientProfile.objects.select_related('user').order_by('-updated_at')
    status_filter = request.GET.get('status', '')
    if status_filter:
        qs = qs.filter(kyc_status=status_filter)
    else:
        qs = qs.exclude(kyc_status='verified')

    page = Paginator(qs, 25).get_page(request.GET.get('page'))

    return render(request, 'staff/kyc_list.html', {
        'page': page,
        'status_filter': status_filter,
        'statuses': ClientProfile._meta.get_field('kyc_status').choices,
    })


@require_POST
@login_required
def kyc_action(request, profile_id):
    g = _guard(request, COMPLIANCE_ROLES)
    if g:
        return g

    profile = get_object_or_404(ClientProfile, id=profile_id)
    action = request.POST.get('action')
    notes = (request.POST.get('notes') or '')[:500]

    try:
        if action == 'approve':
            KYCService.approve(profile, request.user, request.META.get('REMOTE_ADDR'), notes)
        elif action == 'reject':
            KYCService.reject(profile, request.user, request.META.get('REMOTE_ADDR'), notes)
        elif action == 'request_info':
            KYCService.request_additional_info(profile, request.user, request.META.get('REMOTE_ADDR'), notes)
        elif action == 'suspend':
            KYCService.suspend(profile, request.user, request.META.get('REMOTE_ADDR'), notes)
        elif action == 'start_review':
            KYCService.start_review(profile, request.user, request.META.get('REMOTE_ADDR'))
        else:
            raise ValueError(f'Unknown KYC action: {action}')
        messages.success(request, f'KYC {action} completed.')
    except ValueError as e:
        messages.error(request, str(e))

    return redirect('staff_kyc_list')


# ──────────────────────────────────────────────────────────────────────
# Document review queue
# ──────────────────────────────────────────────────────────────────────
@login_required
def documents_list(request):
    g = _guard(request, CREDIT_ROLES + ('Compliance Officer',))
    if g:
        return g

    from django.db.models import Q
    from apps.accounts.models import User
    from apps.accounts.completeness import get_profile_gaps

    status_filter = request.GET.get('status', 'submitted')
    search = (request.GET.get('q') or '').strip()
    only_missing = request.GET.get('only_missing') == '1'

    docs_qs = (
        Document.objects
        .select_related('client', 'reviewed_by')
        .order_by('client__email', '-created_at')
    )
    if status_filter:
        docs_qs = docs_qs.filter(status=status_filter)

    client_ids = list(docs_qs.values_list('client_id', flat=True).distinct())

    if search:
        q = (
            Q(email__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(phone_number__icontains=search)
        )
        try:
            from core.crypto import blind_index
            exact_index = blind_index(search)
            if exact_index:
                profile_matches = list(
                    ClientProfile.objects
                    .filter(id_number_index=exact_index)
                    .values_list('user_id', flat=True)
                )
                if profile_matches:
                    q = q | Q(id__in=profile_matches)
        except Exception:
            pass

        client_ids = list(
            User.objects.filter(q, id__in=client_ids)
            .values_list('id', flat=True)
        )

    clients = (
        User.objects
        .filter(id__in=client_ids)
        .select_related('client_profile')
        .order_by('email')
    )

    grouped = []
    for client in clients:
        profile = getattr(client, 'client_profile', None)
        client_docs = list(docs_qs.filter(client=client))

        try:
            raw_missing = get_profile_gaps(client)
        except Exception:
            raw_missing = []

        missing = []
        for m in raw_missing or []:
            if isinstance(m, dict):
                missing.append({
                    'label': m.get('label') or m.get('name') or str(m),
                    'code': m.get('code', ''),
                    'href': m.get('href', '/staff/applications/?q=' + client.email),
                })
            else:
                missing.append({
                    'label': str(m),
                    'code': '',
                    'href': '/staff/applications/?q=' + client.email,
                })

        if only_missing and not missing:
            continue

        grouped.append({
            'client': client,
            'profile': profile,
            'documents': client_docs,
            'missing': missing,
            'document_count': len(client_docs),
        })

    total_clients = len(grouped)
    total_documents = docs_qs.count()

    page = Paginator(grouped, 20).get_page(request.GET.get('page'))

    pending_replacements = (
        DocumentReplacementRequest.objects
        .filter(status='pending')
        .select_related('document', 'requested_by')
        .order_by('-created_at')[:10]
    )

    return render(request, 'staff/documents_list.html', {
        'page': page,
        'status_filter': status_filter,
        'search': search,
        'only_missing': only_missing,
        'total_clients': total_clients,
        'total_documents': total_documents,
        'pending_replacements': pending_replacements,
        'statuses': Document._meta.get_field('status').choices,
    })


@require_POST
@login_required
def document_review(request, document_id):
    g = _guard(request, CREDIT_ROLES + ('Compliance Officer',))
    if g:
        return g

    doc = get_object_or_404(Document, id=document_id)
    action = request.POST.get('action')
    notes = (request.POST.get('notes') or '')[:500]

    try:
        if action == 'approve':
            DocumentReviewService.approve(
                doc, request.user,
                notes=notes, ip_address=request.META.get('REMOTE_ADDR'),
            )
            messages.success(request, f'Approved {doc.original_filename}.')
        elif action == 'reject':
            DocumentReviewService.reject(
                doc, request.user,
                notes=notes, ip_address=request.META.get('REMOTE_ADDR'),
            )
            messages.success(request, f'Rejected {doc.original_filename}.')
        else:
            raise ValueError(f'Unknown document action: {action}')
    except ValueError as e:
        messages.error(request, str(e))

    from urllib.parse import urlencode
    params = {}
    if request.POST.get('_status'):
        params['status'] = request.POST['_status']
    if request.POST.get('_q'):
        params['q'] = request.POST['_q']
    if request.POST.get('_only_missing') == '1':
        params['only_missing'] = '1'

    url = reverse('staff_documents_list')
    if params:
        url = f"{url}?{urlencode(params)}"
    return redirect(url)


@require_POST
@login_required
def replacement_review(request, request_id):
    g = _guard(request, CREDIT_ROLES + ('Compliance Officer',))
    if g:
        return g

    req = get_object_or_404(DocumentReplacementRequest, id=request_id)
    action = request.POST.get('action')
    notes = (request.POST.get('notes') or '')[:500]

    from apps.kyc.services import DocumentReplacementService
    try:
        if action == 'approve':
            DocumentReplacementService.approve_request(
                req, request.user, notes=notes, ip_address=request.META.get('REMOTE_ADDR'),
            )
            messages.success(request, 'Replacement request approved.')
        elif action == 'reject':
            DocumentReplacementService.reject_request(
                req, request.user, notes=notes, ip_address=request.META.get('REMOTE_ADDR'),
            )
            messages.success(request, 'Replacement request rejected.')
        else:
            raise ValueError(f'Unknown action: {action}')
    except ValueError as e:
        messages.error(request, str(e))

    return redirect('staff_documents_list')


@login_required
def document_download(request, document_id):
    g = _guard(request, CREDIT_ROLES + ('Compliance Officer', 'Auditor'))
    if g:
        return g

    doc = get_object_or_404(Document, id=document_id)
    version = doc.versions.order_by('-version_number').first()
    if not version:
        raise Http404
    try:
        file_obj = default_storage.open(version.storage_key, 'rb')
    except FileNotFoundError:
        raise Http404

    from apps.audit.services import AuditService
    AuditService.record(
        actor=request.user, action='staff_document_download',
        object_type='document', object_id=str(doc.id),
        ip_address=request.META.get('REMOTE_ADDR'),
    )
    response = FileResponse(file_obj, content_type=doc.mime_type)
    response['Content-Disposition'] = f'attachment; filename="{doc.original_filename}"'
    return response


# ──────────────────────────────────────────────────────────────────────
# Loan portfolio
# ──────────────────────────────────────────────────────────────────────
@login_required
def loans_list(request):
    g = _guard(request, CREDIT_ROLES + FINANCE_ROLES + COLLECTIONS_ROLES)
    if g:
        return g

    qs = Loan.objects.select_related('client', 'product').order_by('-created_at')
    status_filter = request.GET.get('status', '')
    if status_filter:
        qs = qs.filter(status=status_filter)

    search = request.GET.get('q', '').strip()
    if search:
        qs = qs.filter(
            Q(client__email__icontains=search) |
            Q(client__first_name__icontains=search) |
            Q(client__last_name__icontains=search)
        )

    totals = qs.aggregate(
        principal=Coalesce(Sum('principal_amount'), Value(Decimal('0'))),
        outstanding=Coalesce(Sum('outstanding_balance'), Value(Decimal('0'))),
    )

    page = Paginator(qs, 25).get_page(request.GET.get('page'))

    return render(request, 'staff/loans_list.html', {
        'page': page,
        'status_filter': status_filter,
        'search': search,
        'totals': totals,
        'statuses': Loan._meta.get_field('status').choices,
    })


@login_required
def loan_detail(request, loan_id):
    g = _guard(request, CREDIT_ROLES + FINANCE_ROLES + COLLECTIONS_ROLES)
    if g:
        return g

    loan = get_object_or_404(
        Loan.objects.select_related('client', 'product', 'application'),
        id=loan_id,
    )
    schedule = loan.repayment_schedule.order_by('period_number')
    payments = loan.repayments.order_by('-actual_date')[:50]
    mandate = loan.debit_instructions.order_by('-created_at').first()
    transactions = loan.payment_transactions.order_by('-created_at')[:50]
    failed_count = loan.payment_transactions.filter(status='failed').count()

    return render(request, 'staff/loan_detail.html', {
        'loan': loan,
        'schedule': schedule,
        'payments': payments,
        'mandate': mandate,
        'transactions': transactions,
        'failed_count': failed_count,
    })


@require_POST
@login_required
def loan_set_collection_day(request, loan_id):
    g = _guard(request, CREDIT_ROLES + FINANCE_ROLES)
    if g:
        return g
    loan = get_object_or_404(Loan, id=loan_id)
    try:
        day = int(request.POST.get('collection_day', 0))
        if not (1 <= day <= 31):
            raise ValueError('Collection day must be 1–31.')
        loan.collection_day = day
        loan.save(update_fields=['collection_day', 'updated_at'])
        messages.success(request, f'Collection day set to {day}.')
    except (ValueError, TypeError) as e:
        messages.error(request, str(e))
    return redirect('staff_application_detail', application_id=loan.application_id)


# ──────────────────────────────────────────────────────────────────────
# Collections
# ──────────────────────────────────────────────────────────────────────
@login_required
def collections(request):
    g = _guard(request, COLLECTIONS_ROLES)
    if g:
        return g

    today = date.today()

    overdue_qs = (
        RepaymentSchedule.objects
        .filter(status__in=['pending', 'partial', 'overdue'], scheduled_date__lt=today)
        .select_related('loan', 'loan__client')
        .order_by('scheduled_date')
    )

    buckets = {'1_30': 0, '31_60': 0, '61_90': 0, '90_plus': 0}
    total_overdue = Decimal('0')
    rows = []
    for row in overdue_qs:
        days = (today - row.scheduled_date).days
        if days <= 30:
            buckets['1_30'] += 1
        elif days <= 60:
            buckets['31_60'] += 1
        elif days <= 90:
            buckets['61_90'] += 1
        else:
            buckets['90_plus'] += 1
        total_overdue += (row.total_amount - row.amount_paid)
        row.days_overdue = days
        rows.append(row)

    page = Paginator(rows, 25).get_page(request.GET.get('page'))

    return render(request, 'staff/collections.html', {
        'page': page,
        'buckets': buckets,
        'total_overdue': total_overdue,
    })


# ──────────────────────────────────────────────────────────────────────
# Reconciliation
# ──────────────────────────────────────────────────────────────────────
@login_required
def reconciliation(request):
    g = _guard(request, FINANCE_ROLES + ('Administrator',))
    if g:
        return g

    qs = (
        ReconciliationRecord.objects
        .select_related('loan', 'loan__client')
        .order_by('-created_at')
    )

    status_filter = request.GET.get('status', '')
    if status_filter:
        qs = qs.filter(status=status_filter)

    date_from = request.GET.get('from', '')
    date_to = request.GET.get('to', '')
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    summary = {
        'matched': qs.filter(status='matched').count(),
        'missing': qs.filter(status='missing').count(),
        'partial': qs.filter(status='partial').count(),
        'unmatched': qs.filter(status='unmatched').count(),
    }

    page = Paginator(qs, 25).get_page(request.GET.get('page'))

    return render(request, 'staff/reconciliation.html', {
        'page': page,
        'status_filter': status_filter,
        'date_from': date_from,
        'date_to': date_to,
        'summary': summary,
    })


# ──────────────────────────────────────────────────────────────────────
# Fraud alerts
# ──────────────────────────────────────────────────────────────────────
@login_required
def fraud_list(request):
    g = _guard(request, COMPLIANCE_ROLES + ('Credit Officer',))
    if g:
        return g

    qs = FraudAlert.objects.select_related('assigned_to', 'reviewed_by').order_by('-created_at')
    status_filter = request.GET.get('status', 'open')
    if status_filter:
        qs = qs.filter(status=status_filter)

    severity = request.GET.get('severity', '')
    if severity:
        qs = qs.filter(severity=severity)

    page = Paginator(qs, 25).get_page(request.GET.get('page'))

    return render(request, 'staff/fraud_list.html', {
        'page': page,
        'status_filter': status_filter,
        'severity_filter': severity,
    })


@login_required
def fraud_detail(request, alert_id):
    g = _guard(request, COMPLIANCE_ROLES + ('Credit Officer',))
    if g:
        return g

    alert = get_object_or_404(FraudAlert, id=alert_id)
    related_events = []
    if alert.user_id:
        related_events = (
            SecurityEvent.objects
            .filter(user_id=alert.user_id)
            .order_by('-created_at')[:30]
        )

    return render(request, 'staff/fraud_detail.html', {
        'alert': alert,
        'related_events': related_events,
    })


@require_POST
@login_required
def fraud_action(request, alert_id):
    g = _guard(request, COMPLIANCE_ROLES + ('Credit Officer',))
    if g:
        return g

    alert = get_object_or_404(FraudAlert, id=alert_id)
    action = request.POST.get('action')
    notes = (request.POST.get('notes') or '')[:1000]

    from apps.audit.services import AuditService

    if action == 'assign':
        alert.assigned_to = request.user
        alert.status = 'investigating'
        alert.save(update_fields=['assigned_to', 'status', 'updated_at'])
        messages.success(request, 'Fraud alert assigned to you.')
    elif action in ('resolve', 'false_positive', 'escalate'):
        alert.status = {
            'resolve': 'resolved',
            'false_positive': 'false_positive',
            'escalate': 'escalated',
        }[action]
        alert.reviewed_by = request.user
        alert.reviewed_at = timezone.now()
        alert.resolution_notes = notes
        alert.save(update_fields=[
            'status', 'reviewed_by', 'reviewed_at', 'resolution_notes', 'updated_at',
        ])
        messages.success(request, f'Alert marked as {alert.status}.')
    else:
        messages.error(request, f'Unknown action: {action}')

    AuditService.record(
        actor=request.user, action=f'fraud_alert_{action}',
        object_type='fraud_alert', object_id=str(alert.id),
        ip_address=request.META.get('REMOTE_ADDR'),
    )
    return redirect('staff_fraud_detail', alert_id=alert.id)


# ──────────────────────────────────────────────────────────────────────
# Audit log viewer
# ──────────────────────────────────────────────────────────────────────
@login_required
def audit_list(request):
    g = _guard(request, ('Administrator', 'Auditor', 'Compliance Officer'))
    if g:
        return g

    qs = AuditLog.objects.all().order_by('-created_at')

    action_filter = request.GET.get('action', '')
    if action_filter:
        qs = qs.filter(action__icontains=action_filter)

    actor_filter = request.GET.get('actor', '')
    if actor_filter:
        qs = qs.filter(actor_email__icontains=actor_filter)

    date_from = request.GET.get('from', '')
    date_to = request.GET.get('to', '')
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    page = Paginator(qs, 50).get_page(request.GET.get('page'))

    return render(request, 'staff/audit_list.html', {
        'page': page,
        'action_filter': action_filter,
        'actor_filter': actor_filter,
        'date_from': date_from,
        'date_to': date_to,
    })


# ──────────────────────────────────────────────────────────────────────
# Staff AI Insights
# ──────────────────────────────────────────────────────────────────────
def _qualification_hint(payday, debt, credit_report):
    if not payday and not debt:
        return {
            'code': 'insufficient_data',
            'label': 'Insufficient data',
            'detail': 'No AI analysis available yet.',
            'tone': 'slate',
        }

    if credit_report and credit_report.worst_arrears_months >= 3:
        return {
            'code': 'decline',
            'label': 'Likely decline',
            'detail': f"Credit report shows {credit_report.worst_arrears_months} months in arrears.",
            'tone': 'rose',
        }

    if credit_report and credit_report.has_defaults:
        return {
            'code': 'decline',
            'label': 'Likely decline',
            'detail': 'Credit report shows defaults.',
            'tone': 'rose',
        }

    if debt and isinstance(debt.output_data, dict):
        creditors = debt.output_data.get('creditors') or []
        if len(creditors) >= 5:
            return {
                'code': 'review',
                'label': 'Manual review',
                'detail': f"{len(creditors)} recurring creditors detected.",
                'tone': 'amber',
            }

    if payday and isinstance(payday.output_data, dict):
        try:
            conf = float(payday.output_data.get('confidence') or 0)
        except (TypeError, ValueError):
            conf = 0
        if conf < 0.5:
            return {
                'code': 'review',
                'label': 'Manual review',
                'detail': f"Low payday confidence ({conf:.0%}).",
                'tone': 'amber',
            }

    return {
        'code': 'proceed',
        'label': 'Proceed with review',
        'detail': 'No red flags in AI analysis. Verify documents and affordability.',
        'tone': 'emerald',
    }


@login_required
def ai_insights(request):
    g = _guard(request, CREDIT_ROLES + ('Administrator', 'Compliance Officer'))
    if g:
        return g

    from apps.ai.models import AIAnalysis
    from apps.banking.models import BankStatement
    from apps.kyc.credit_bureau_service import CreditBureauService

    statements = (
        BankStatement.objects
        .filter(processing_status='completed')
        .select_related('client')
        .order_by('-created_at')
    )

    client_id = request.GET.get('client')
    if client_id:
        statements = statements.filter(client_id=client_id)

    seen = set()
    rows = []
    for stmt in statements:
        if stmt.client_id in seen:
            continue
        seen.add(stmt.client_id)

        analyses = list(
            AIAnalysis.objects
            .filter(input_reference=str(stmt.id))
            .order_by('-created_at')
        )

        payday = next((a for a in analyses if 'detected_salary' in (a.output_data or {})), None)
        debt = next((a for a in analyses if 'creditors' in (a.output_data or {})), None)
        general = next((a for a in analyses if a not in (payday, debt)), None)

        application = (
            LoanApplication.objects
            .filter(client=stmt.client, status__in=[
                'submitted', 'document_review', 'kyc_review',
                'affordability_review', 'credit_review',
            ])
            .order_by('-created_at')
            .first()
        )

        credit_report = CreditBureauService.has_valid_report(stmt.client)

        recommendation = _qualification_hint(
            payday=payday, debt=debt, credit_report=credit_report,
        )

        rows.append({
            'client': stmt.client,
            'statement': stmt,
            'payday': payday,
            'debt': debt,
            'general': general,
            'application': application,
            'credit_report': credit_report,
            'recommendation': recommendation,
        })

    return render(request, 'staff/ai_insights.html', {
        'rows': rows,
        'client_filter': client_id,
    })


# ──────────────────────────────────────────────────────────────────────
# Staff AI Assistant
# ──────────────────────────────────────────────────────────────────────
CHAT_ROLES = CREDIT_ROLES + (
    'Administrator', 'Compliance Officer', 'Finance Officer', 'Collections Officer',
)


@login_required
def staff_chat(request):
    g = _guard(request, CHAT_ROLES)
    if g:
        return g

    from apps.chat.models import ChatConversation
    from apps.chat.services import ChatService

    conv = (
        ChatConversation.objects
        .filter(user=request.user, is_active=True, channel='staff')
        .order_by('-last_message_at')
        .first()
    )
    if not conv:
        conv = ChatService.get_or_create_conversation(
            user=request.user, channel='staff',
        )

    return render(request, 'staff/chat.html', {'conversation': conv})


@login_required
def staff_chat_messages(request, conversation_id):
    g = _guard(request, CHAT_ROLES)
    if g:
        return g

    from apps.chat.models import ChatConversation

    conv = get_object_or_404(
        ChatConversation, id=conversation_id, user=request.user,
    )
    messages_qs = conv.messages.order_by('created_at')
    return render(request, 'staff/_chat_messages.html', {
        'conversation': conv,
        'messages': messages_qs,
    })


@require_POST
@login_required
def staff_chat_send(request, conversation_id):
    g = _guard(request, CHAT_ROLES)
    if g:
        return g

    from apps.chat.models import ChatConversation
    from apps.chat.services import ChatService

    conv = get_object_or_404(
        ChatConversation, id=conversation_id, user=request.user,
    )
    text = (request.POST.get('message') or '').strip()
    if text:
        try:
            ChatService.ask(request.user, text, conv)
        except Exception:
            pass

    messages_qs = conv.messages.order_by('created_at')
    return render(request, 'staff/_chat_messages.html', {
        'conversation': conv,
        'messages': messages_qs,
    })