"""Celery tasks for payment operations."""
import logging
from datetime import date, timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger('apps.payments')


def _is_within_collection_window(loan, today: date) -> bool:
    """
    Return True if `today` is inside the loan's collection tracking window.
    If no window is configured, allow any day.
    """
    start, end = loan.effective_collection_window
    return start <= today.day <= end


@shared_task(name='apps.payments.tasks.process_disbursement')
def process_disbursement(application_id):
    """Release funds, activate the loan record, and transition the app."""
    from apps.loans.models import LoanApplication
    from apps.loans.services import LoanApplicationService
    from apps.payments.providers.factory import get_payment_provider

    application = LoanApplication.objects.filter(id=application_id).first()
    if not application:
        return 'not_found'

    loan = getattr(application, 'loan', None)
    if not loan:
        return 'no_loan'

    mandate = loan.debit_instructions.filter(status='active', is_active=True).first()
    if not mandate:
        return 'no_mandate'

    provider = get_payment_provider()
    try:
        provider.initiate_disbursement({
            'loan_id': str(loan.id),
            'amount': str(loan.principal_amount),
            'account_number': mandate.account_number_encrypted,
            'bank_name': mandate.bank_name,
            'branch_code': mandate.branch_code,
            'reference': f'WML-{loan.id.hex[:8].upper()}',
        })
    except Exception as e:
        logger.exception("Disbursement failed: %s", e)
        return f'error: {e}'

    loan.status = 'active'
    loan.start_date = timezone.now().date()
    loan.save(update_fields=['status', 'start_date', 'updated_at'])

    try:
        LoanApplicationService.transition(
            application, 'active', None,
            notes=f"Disbursed via {provider.__class__.__name__}",
        )
    except ValueError as e:
        logger.error("Transition to active failed after disbursement: %s", e)

    return f'disbursed {loan.id}'


@shared_task(name='apps.payments.tasks.submit_due_debits')
def submit_due_debits(days_ahead: int = 1):
    """
    First-attempt debit submission. Runs nightly.
    Only attempts collection when today falls inside each loan's collection window.
    """
    from apps.loans.models import Loan
    from apps.payments.services import PaymentService
    from apps.repayments.models import RepaymentSchedule

    today = date.today()
    submitted = 0
    skipped_window = 0

    for loan in Loan.objects.filter(status='active').iterator():
        if not _is_within_collection_window(loan, today):
            skipped_window += 1
            continue

        instruction = loan.debit_instructions.filter(
            status='active', is_active=True,
        ).first()
        if not instruction:
            continue

        cutoff = today + timedelta(days=days_ahead)
        due_rows = RepaymentSchedule.objects.filter(
            loan=loan,
            status__in=['pending', 'partial'],
            scheduled_date__lte=cutoff,
        ).order_by('period_number')

        for row in due_rows:
            # Skip if any attempt already exists for this instalment
            if loan.payment_transactions.filter(
                repayment_schedule_id=row.id,
                status__in=['pending', 'processing', 'successful', 'failed'],
            ).exists():
                continue

            try:
                PaymentService.submit_payment(
                    loan=loan,
                    amount=row.total_amount - row.amount_paid,
                    schedule_id=row.id,
                    method='debit_order',
                )
                submitted += 1
            except Exception as e:
                logger.exception('Scheduled debit submission failed: %s', e)

    logger.info(
        'submit_due_debits: submitted=%d skipped_window=%d',
        submitted, skipped_window,
    )
    return {'submitted': submitted, 'skipped_window': skipped_window}


@shared_task(name='apps.payments.tasks.retry_failed_debits')
def retry_failed_debits():
    """
    Process scheduled undisputable retries. Runs nightly.
    Only retries where:
      - status = 'failed'
      - next_retry_at <= now
      - loan is inside its collection window
      - loan is active or overdue
    """
    from apps.payments.models import PaymentTransaction
    from apps.payments.services import PaymentService

    today = date.today()
    now = timezone.now()

    pending = PaymentTransaction.objects.filter(
        status='failed',
        next_retry_at__isnull=False,
        next_retry_at__lte=now,
    ).select_related('loan')

    attempted = 0
    skipped_window = 0
    failed = 0

    for txn in pending:
        loan = txn.loan
        if loan.status not in ('active', 'overdue'):
            txn.next_retry_at = None
            txn.save(update_fields=['next_retry_at', 'updated_at'])
            continue

        if not _is_within_collection_window(loan, today):
            skipped_window += 1
            continue

        try:
            result = PaymentService._submit_retry(txn)
            if result is not None:
                attempted += 1
        except Exception as e:
            failed += 1
            logger.exception('Retry failed for txn %s: %s', txn.id, e)

    logger.info(
        'retry_failed_debits: attempted=%d skipped_window=%d failed=%d',
        attempted, skipped_window, failed,
    )
    return {'attempted': attempted, 'skipped_window': skipped_window, 'failed': failed}


@shared_task(name='apps.payments.tasks.poll_pending_transactions')
def poll_pending_transactions():
    """Poll the provider for status of pending/processing transactions."""
    from apps.payments.models import PaymentTransaction
    from apps.payments.providers.factory import get_payment_provider
    from apps.payments.services import PaymentService

    provider = get_payment_provider()
    updated = 0

    for txn in PaymentTransaction.objects.filter(
        status__in=['pending', 'processing'],
    )[:100].iterator():
        if not txn.provider_transaction_id:
            continue
        try:
            result = provider.get_payment_status(txn.provider_transaction_id)
            new_status = result.get('status')
            if new_status and new_status != txn.status:
                previous_status = txn.status
                txn.status = new_status
                if new_status == 'failed':
                    txn.decline_code = result.get('decline_code', '')
                    txn.decline_reason = result.get('decline_reason', '')
                txn.save(update_fields=[
                    'status', 'decline_code', 'decline_reason', 'updated_at',
                ])
                updated += 1

                # Notify on the transition into 'failed' only.
                if new_status == 'failed' and previous_status != 'failed':
                    PaymentService._notify_client_payment_failed(
                        txn,
                        is_retry=(txn.attempt_number or 1) > 1,
                    )
        except Exception as e:
            logger.warning('Poll failed for %s: %s', txn.id, e)

    return {'updated': updated}


@shared_task(name='apps.payments.tasks.run_reconciliation')
def run_reconciliation():
    """Reconcile all active loans."""
    from apps.payments.services import PaymentService
    return PaymentService.reconcile_all_active_loans()