"""Analytics and report aggregation."""
from decimal import Decimal
from datetime import date, timedelta
from django.db.models import Count, Sum, Avg, Q

from apps.loans.models import Loan, LoanApplication
from apps.repayments.models import RepaymentSchedule, Repayment
from apps.payments.models import PaymentTransaction, ReconciliationRecord


def _fmt(v):
    if v is None:
        return 'R 0.00'
    return f'R {Decimal(v):,.2f}'


class ReportsService:

    # â”€â”€ Portfolio â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    @staticmethod
    def portfolio_summary():
        loans = Loan.objects.all()
        active = loans.filter(status='active')
        overdue = loans.filter(status='overdue')
        paid = loans.filter(status='paid')
        return {
            'total_loans': loans.count(),
            'active_loans': active.count(),
            'overdue_loans': overdue.count(),
            'paid_loans': paid.count(),
            'total_principal': _fmt(loans.aggregate(s=Sum('principal_amount'))['s']),
            'total_outstanding': _fmt(loans.aggregate(s=Sum('outstanding_balance'))['s']),
            'average_principal': _fmt(active.aggregate(a=Avg('principal_amount'))['a']),
            'average_interest_rate': str(active.aggregate(a=Avg('interest_rate'))['a'] or 0),
        }

    # â”€â”€ Applications â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    @staticmethod
    def application_stats(days=30):
        since = date.today() - timedelta(days=days)
        apps = LoanApplication.objects.filter(created_at__date__gte=since)
        total = apps.count()
        approved = apps.filter(status__in=['approved', 'contract_pending', 'contract_accepted',
                                           'disbursement_pending', 'active', 'paid']).count()
        rejected = apps.filter(status='rejected').count()
        return {
            'period_days': days,
            'total_applications': total,
            'approved': approved,
            'rejected': rejected,
            'approval_rate': round((approved / total) * 100, 2) if total else 0,
            'average_requested_amount': _fmt(apps.aggregate(a=Avg('requested_amount'))['a']),
        }

    # â”€â”€ Repayments â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    @staticmethod
    def repayment_stats(days=30):
        since = date.today() - timedelta(days=days)
        payments = Repayment.objects.filter(actual_date__gte=since, status='successful')
        total_collected = payments.aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

        upcoming = RepaymentSchedule.objects.filter(
            status__in=['pending', 'partial'],
            scheduled_date__gte=date.today(),
            scheduled_date__lte=date.today() + timedelta(days=30),
        )
        overdue = RepaymentSchedule.objects.filter(status='overdue')

        return {
            'period_days': days,
            'total_collected': _fmt(total_collected),
            'payment_count': payments.count(),
            'average_payment': _fmt(payments.aggregate(a=Avg('amount'))['a']),
            'upcoming_30d_count': upcoming.count(),
            'upcoming_30d_amount': _fmt(
                upcoming.aggregate(s=Sum('total_amount'))['s']),
            'overdue_count': overdue.count(),
            'overdue_amount': _fmt(
                overdue.aggregate(
                    s=Sum('total_amount') - Sum('amount_paid')
                )['s']),
        }

    # â”€â”€ Delinquency â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    @staticmethod
    def delinquency_report():
        buckets = {
            '1_30_days': 0,
            '31_60_days': 0,
            '61_90_days': 0,
            '90_plus_days': 0,
        }
        today = date.today()
        qs = RepaymentSchedule.objects.filter(
            status__in=['pending', 'partial', 'overdue'],
            scheduled_date__lt=today,
        )
        for row in qs.iterator():
            days = (today - row.scheduled_date).days
            if days <= 30:
                buckets['1_30_days'] += 1
            elif days <= 60:
                buckets['31_60_days'] += 1
            elif days <= 90:
                buckets['61_90_days'] += 1
            else:
                buckets['90_plus_days'] += 1
        return buckets

    # â”€â”€ Reconciliation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    @staticmethod
    def reconciliation_summary(days=30):
        since = date.today() - timedelta(days=days)
        records = ReconciliationRecord.objects.filter(created_at__date__gte=since)
        return {
            'period_days': days,
            'total_records': records.count(),
            'matched': records.filter(status='matched').count(),
            'missing': records.filter(status='missing').count(),
            'partial': records.filter(status='partial').count(),
            'unmatched': records.filter(status='unmatched').count(),
        }

    @staticmethod
    def portfolio_health_metrics() -> dict:
        """
        Aggregate the metrics needed for an AI-generated summary.
        Returns a compact dict — safe to send to any AI provider.
        """
        from apps.loans.models import Loan, LoanApplication
        from apps.repayments.models import RepaymentSchedule
        from apps.payments.models import ReconciliationRecord
        from apps.security.models import FraudAlert
        from django.db.models import Sum, Avg, Count
        from django.utils import timezone
        from datetime import timedelta

        now = timezone.now()
        last_30 = now - timedelta(days=30)
        last_7 = now - timedelta(days=7)

        loans = Loan.objects.all()
        apps = LoanApplication.objects.all()

        return {
            'as_of': now.isoformat(),
            'loans': {
                'total': loans.count(),
                'active': loans.filter(status='active').count(),
                'overdue': loans.filter(status='overdue').count(),
                'defaulted': loans.filter(status='defaulted').count(),
                'paid': loans.filter(status='paid').count(),
                'total_outstanding': float(
                    loans.aggregate(s=Sum('outstanding_balance'))['s'] or 0
                ),
                'average_principal': float(
                    loans.aggregate(a=Avg('principal_amount'))['a'] or 0
                ),
            },
            'risk': {
                'critical': loans.filter(default_risk_band='critical').count(),
                'high': loans.filter(default_risk_band='high').count(),
                'medium': loans.filter(default_risk_band='medium').count(),
            },
            'applications_last_30d': {
                'submitted': apps.filter(created_at__gte=last_30).count(),
                'approved': apps.filter(
                    status__in=['approved', 'contract_pending', 'contract_accepted',
                                'disbursement_pending', 'active', 'paid'],
                    created_at__gte=last_30,
                ).count(),
                'rejected': apps.filter(status='rejected', created_at__gte=last_30).count(),
            },
            'repayments_last_30d': {
                'due_count': RepaymentSchedule.objects.filter(
                    scheduled_date__gte=last_30.date(),
                ).count(),
                'paid_count': RepaymentSchedule.objects.filter(
                    status='paid', scheduled_date__gte=last_30.date(),
                ).count(),
                'overdue_count': RepaymentSchedule.objects.filter(
                    status='overdue',
                ).count(),
            },
            'reconciliation_last_7d': {
                'matched': ReconciliationRecord.objects.filter(
                    status='matched', created_at__gte=last_7,
                ).count(),
                'mismatches': ReconciliationRecord.objects.filter(
                    created_at__gte=last_7,
                ).exclude(status='matched').count(),
            },
            'security_last_7d': {
                'fraud_alerts_open': FraudAlert.objects.filter(status='open').count(),
                'fraud_alerts_critical': FraudAlert.objects.filter(
                    severity='critical', created_at__gte=last_7,
                ).count(),
            },
        }
