"""Celery tasks for notifications."""
import logging
from datetime import date, timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger('apps.notifications')


@shared_task(name='apps.notifications.tasks.send_payment_reminders')
def send_payment_reminders(days_ahead: int = 3):
    """Notify clients about repayments due soon."""
    from apps.loans.models import Loan
    from apps.repayments.models import RepaymentSchedule
    from .services import NotificationService

    target = date.today() + timedelta(days=days_ahead)
    sent = 0
    for loan in Loan.objects.filter(status='active').select_related('client'):
        rows = RepaymentSchedule.objects.filter(
            loan=loan, status__in=['pending', 'partial'], scheduled_date=target,
        )
        for row in rows:
            amount = row.total_amount - row.amount_paid
            NotificationService.dispatch(
                loan.client, 'payment_due',
                context={
                    'amount': f'R {amount:,.2f}',
                    'due_date': row.scheduled_date.strftime('%Y-%m-%d'),
                    'loan_id': str(loan.id),
                },
            )
            sent += 1
    logger.info("Sent %d payment reminders", sent)
    return {'sent': sent}


@shared_task(name='apps.notifications.tasks.send_overdue_notifications')
def send_overdue_notifications():
    """Notify clients of overdue repayments."""
    from apps.repayments.models import RepaymentSchedule
    from .services import NotificationService

    overdue = RepaymentSchedule.objects.filter(
        status__in=['pending', 'partial'],
        scheduled_date__lt=date.today(),
    ).select_related('loan__client')

    count = 0
    for row in overdue:
        amount = row.total_amount - row.amount_paid
        NotificationService.dispatch(
            row.loan.client, 'payment_overdue',
            context={
                'amount': f'R {amount:,.2f}',
                'due_date': row.scheduled_date.strftime('%Y-%m-%d'),
                'loan_id': str(row.loan_id),
            },
        )
        row.status = 'overdue'
        row.save(update_fields=['status', 'updated_at'])
        count += 1
    return {'notified': count}
