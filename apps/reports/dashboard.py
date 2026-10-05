"""Dashboard aggregations for client / staff / admin."""
from datetime import date
from django.db.models import Sum
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.loans.models import Loan, LoanApplication
from apps.repayments.models import RepaymentSchedule
from apps.notifications.models import Notification


def _client_dashboard(user):
    loans = Loan.objects.filter(client=user)
    active = loans.exclude(status='paid')
    upcoming = RepaymentSchedule.objects.filter(
        loan__client=user, status__in=['pending', 'partial', 'overdue'],
    ).order_by('scheduled_date')[:5]

    return {
        'role': 'client',
        'loans': {
            'active_count': active.count(),
            'total_outstanding': str(
                loans.aggregate(s=Sum('outstanding_balance'))['s'] or 0
            ),
        },
        'upcoming_payments': [
            {
                'due_date': r.scheduled_date.isoformat(),
                'amount': str(r.total_amount - r.amount_paid),
                'status': r.status,
            } for r in upcoming
        ],
        'unread_notifications': Notification.objects.filter(
            user=user, read_at__isnull=True, status='sent',
        ).count(),
    }


def _staff_dashboard(user):
    apps = LoanApplication.objects.all()
    loans = Loan.objects.all()
    overdue = RepaymentSchedule.objects.filter(status='overdue')
    return {
        'role': 'staff',
        'applications': {
            'in_review': apps.filter(status__in=[
                'submitted', 'document_review', 'kyc_review',
                'affordability_review', 'credit_review',
            ]).count(),
            'approved_today': apps.filter(
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
