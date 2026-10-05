"""Dashboard endpoints — client vs staff, auto-detected by role."""
from datetime import date

from django.db.models import Sum
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


# Statuses that count as "under review" in the current loan state machine
# (see apps/loans/services.py → TRANSITIONS).
_APPLICATION_IN_REVIEW_STATUSES = [
    'submitted',
    'under_review',
    'awaiting_documents',
    'awaiting_affordability',
]


def _client_dashboard(user):
    from apps.loans.models import Loan
    from apps.notifications.models import Notification
    from apps.repayments.models import RepaymentSchedule

    loans = Loan.objects.filter(client=user)
    active_loans = loans.filter(status='active')
    upcoming = RepaymentSchedule.objects.filter(
        loan__client=user, status__in=['pending', 'partial', 'overdue'],
    ).order_by('scheduled_date')[:5]

    return {
        'role': 'client',
        'loans': {
            'active_count': active_loans.count(),
            'total_outstanding': str(
                loans.aggregate(s=Sum('outstanding_balance'))['s'] or 0
            ),
        },
        'upcoming_payments': [
            {
                'due_date': r.scheduled_date.isoformat(),
                'amount': str(r.total_amount - r.amount_paid),
                'status': r.status,
            }
            for r in upcoming
        ],
        'unread_notifications': Notification.objects.filter(
            user=user, read_at__isnull=True, status='sent',
        ).count(),
    }


def _staff_dashboard(user):
    from apps.loans.models import Loan, LoanApplication
    from apps.repayments.models import RepaymentSchedule

    applications = LoanApplication.objects.all()
    loans = Loan.objects.all()
    overdue = RepaymentSchedule.objects.filter(status='overdue')

    return {
        'role': 'staff',
        'applications': {
            'in_review': applications.filter(
                status__in=_APPLICATION_IN_REVIEW_STATUSES,
            ).count(),
            'approved_today': applications.filter(
                status='approved', reviewed_at__date=date.today(),
            ).count(),
        },
        'loans': {
            'active': loans.filter(status='active').count(),
            'overdue': loans.filter(status='overdue').count(),
        },
        'delinquency': {
            'overdue_installments': overdue.count(),
        },
    }


@extend_schema(
    operation_id='dashboard',
    responses={200: OpenApiTypes.OBJECT},
    description='Client or staff dashboard payload, depending on the caller’s role.',
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard(request):
    user = request.user
    if user.is_superuser or any(
        user.has_role(r) for r in (
            'Administrator', 'Credit Officer', 'Finance Officer',
            'Collections Officer', 'Auditor',
        )
    ):
        return Response(_staff_dashboard(user))
    return Response(_client_dashboard(user))