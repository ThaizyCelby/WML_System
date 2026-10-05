"""Role-safe context builders for the AI chatbot.

IMPORTANT: These functions only return data that the requesting user is
permitted to see. They are the single source of truth for what the AI is
allowed to reference.
"""
from decimal import Decimal


def _fmt(v):
    try:
        return f"R {Decimal(v):,.2f}"
    except Exception:
        return str(v)


def build_client_context(user) -> dict:
    """Build context for a client user using only their own records."""
    from apps.loans.models import Loan
    from apps.repayments.models import RepaymentSchedule

    ctx = {
        'role': 'client',
        'user': {
            'name': getattr(user, 'full_name', '') or user.email,
            'email': user.email,
        },
        'loans': [],
        'upcoming_payments': [],
    }

    loans = (
        Loan.objects
        .filter(client=user)
        .select_related('product')
        .order_by('-created_at')[:5]
    )
    for loan in loans:
        ctx['loans'].append({
            'id': str(loan.id),
            'product': loan.product.name if loan.product else 'Loan',
            'principal': _fmt(loan.principal_amount),
            'interest_rate': f"{loan.interest_rate}%",
            'outstanding': _fmt(loan.outstanding_balance),
            'status': loan.status,
            'term_periods': loan.term_periods,
            'repayment_frequency': loan.repayment_frequency,
        })

    # Upcoming 5 unpaid schedule rows across all their loans
    upcoming = (
        RepaymentSchedule.objects
        .filter(loan__client=user, status__in=['pending', 'partial', 'overdue'])
        .order_by('scheduled_date')
        .select_related('loan')[:5]
    )
    for row in upcoming:
        ctx['upcoming_payments'].append({
            'due_date': row.scheduled_date.isoformat(),
            'amount': _fmt(row.total_amount - row.amount_paid),
            'status': row.status,
        })

    return ctx


def build_staff_context(user) -> dict:
    """
    Aggregate, anonymized portfolio summary for staff.

    Never returns individual client PII. Only aggregate counts/sums that a
    staff member with the appropriate role would already see in dashboards.
    """
    from apps.loans.models import Loan, LoanApplication
    from apps.repayments.models import RepaymentSchedule
    from apps.payments.models import ReconciliationRecord
    from apps.security.models import FraudAlert
    from django.db.models import Sum, Count, Avg, Q
    from datetime import date, timedelta

    is_admin = user.is_superuser or user.has_role('Administrator')
    if not (
        is_admin
        or user.has_role('Credit Officer')
        or user.has_role('Finance Officer')
        or user.has_role('Collections Officer')
        or user.has_role('Compliance Officer')
    ):
        return {'role': 'staff', 'access': 'limited', 'note': 'No portfolio access.'}

    today = date.today()
    month_start = today.replace(day=1)

    loans = Loan.objects.all()
    apps = LoanApplication.objects.all()
    overdue = RepaymentSchedule.objects.filter(status='overdue')

    return {
        'role': 'staff',
        'user': {'name': getattr(user, 'full_name', '') or user.email},
        'as_of': today.isoformat(),
        'portfolio': {
            'total_loans': loans.count(),
            'active_loans': loans.filter(status='active').count(),
            'paid_loans': loans.filter(status='paid').count(),
            'overdue_loans': loans.filter(status='overdue').count(),
            'defaulted_loans': loans.filter(status='defaulted').count(),
            'total_principal_disbursed': str(
                loans.aggregate(s=Sum('principal_amount'))['s'] or 0
            ),
            'total_outstanding': str(
                loans.aggregate(s=Sum('outstanding_balance'))['s'] or 0
            ),
            'average_principal': str(
                loans.aggregate(a=Avg('principal_amount'))['a'] or 0
            ),
        },
        'applications': {
            'total': apps.count(),
            'submitted': apps.filter(status='submitted').count(),
            'in_review': apps.filter(status__in=[
                'document_review', 'kyc_review',
                'affordability_review', 'credit_review',
            ]).count(),
            'approved': apps.filter(status__in=[
                'approved', 'contract_pending', 'contract_accepted',
                'disbursement_pending', 'active', 'paid',
            ]).count(),
            'rejected': apps.filter(status='rejected').count(),
            'approval_rate_pct': round(
                (apps.filter(status__in=['approved', 'contract_pending',
                                          'contract_accepted', 'disbursement_pending',
                                          'active', 'paid']).count()
                 / max(apps.count(), 1)) * 100, 2
            ),
            'this_month': apps.filter(created_at__date__gte=month_start).count(),
        },
        'delinquency': {
            'overdue_installments': overdue.count(),
            'overdue_amount': str(
                overdue.aggregate(s=Sum('total_amount'))['s'] or 0
            ),
            'oldest_overdue_days': (
                (today - overdue.order_by('scheduled_date').first().scheduled_date).days
                if overdue.exists() else 0
            ),
        },
        'security': {
            'open_fraud_alerts': FraudAlert.objects.filter(status='open').count(),
            'critical_alerts_7d': FraudAlert.objects.filter(
                severity='critical',
                created_at__date__gte=today - timedelta(days=7),
            ).count(),
        },
        'reconciliation': {
            'unmatched_30d': ReconciliationRecord.objects.filter(
                created_at__date__gte=today - timedelta(days=30),
            ).exclude(status='matched').count(),
        },
    }

    ctx = {
        'role': 'staff',
        'user': {'name': getattr(user, 'full_name', '') or user.email},
        'portfolio': {},
        'applications': {},
        'delinquency': {},
    }

    loans = Loan.objects.all()
    ctx['portfolio'] = {
        'total_loans': loans.count(),
        'active_loans': loans.filter(status='active').count(),
        'paid_loans': loans.filter(status='paid').count(),
        'overdue_loans': loans.filter(status='overdue').count(),
        'total_principal_disbursed': _fmt(
            loans.aggregate(s=Sum('principal_amount'))['s'] or 0
        ),
        'total_outstanding': _fmt(
            loans.aggregate(s=Sum('outstanding_balance'))['s'] or 0
        ),
    }

    applications = LoanApplication.objects.all()
    ctx['applications'] = {
        'total': applications.count(),
        'submitted': applications.filter(status='submitted').count(),
        'in_review': applications.filter(status__in=[
            'document_review', 'kyc_review', 'affordability_review', 'credit_review',
        ]).count(),
        'approved': applications.filter(status='approved').count(),
        'active': applications.filter(status='active').count(),
        'rejected': applications.filter(status='rejected').count(),
    }

    overdue_rows = RepaymentSchedule.objects.filter(status='overdue')
    ctx['delinquency'] = {
        'overdue_installments': overdue_rows.count(),
        'overdue_amount': _fmt(
            overdue_rows.aggregate(
                s=Sum('total_amount') - Sum('amount_paid')
            )['s'] or 0
        ),
    }

    return ctx


def build_context(user) -> dict:
    """Dispatch based on user role."""
    if not user.is_authenticated:
        return {'role': 'anonymous'}
    # Staff = any user with a staff-facing role
    staff_roles = ('Administrator', 'Credit Officer', 'Finance Officer', 'Collections Officer', 'Auditor')
    if user.is_superuser or any(user.has_role(r) for r in staff_roles):
        # Client can also be staff, but if they have both we default to staff
        return build_staff_context(user)
    return build_client_context(user)
