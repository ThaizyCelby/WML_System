"""Payment orchestration: idempotency, webhooks, reconciliation, retries."""
import calendar
import hashlib
import logging
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.audit.services import AuditService

from .models import (
    DebitInstruction, PaymentTransaction, PaymentWebhook, ReconciliationRecord,
)
from .providers.factory import get_payment_provider

logger = logging.getLogger('apps.payments')


def _make_idem_key(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:64]


def _next_retry_date(loan, from_date: date | None = None) -> date | None:
    """
    Compute the next day inside the loan's collection window.

    Used to tell the client when we will attempt collection again after a
    decline. Falls back to tomorrow if the window is unknown or nonsensical.
    """
    try:
        start, end = loan.effective_collection_window
    except Exception:
        return (from_date or date.today()) + timedelta(days=1)

    if not (1 <= start <= 31 and 1 <= end <= 31):
        return (from_date or date.today()) + timedelta(days=1)

    today = from_date or date.today()
    candidate = today + timedelta(days=1)

    # Still before the window opens this month → jump to the start day.
    if candidate.day < start:
        try:
            return candidate.replace(day=start)
        except ValueError:
            # Start day doesn't exist in this month (e.g. 31 in April)
            pass

    # Within the window → retry tomorrow.
    if start <= candidate.day <= end:
        return candidate

    # Past the window → next month's start day.
    year, month = candidate.year, candidate.month
    month += 1
    if month > 12:
        month = 1
        year += 1
    try:
        return date(year, month, start)
    except ValueError:
        # start > days in that month; clamp to the last day
        last_day = calendar.monthrange(year, month)[1]
        return date(year, month, min(start, last_day))


class PaymentService:

    # ── Debit instructions ───────────────────────────────────────
    @staticmethod
    def create_debit_instruction(loan, instruction_data, actor=None, ip_address=None):
        """Legacy helper — used when creating a mandate outside the client UI."""
        provider = get_payment_provider()

        raw_number = ''.join(ch for ch in str(instruction_data['account_number']) if ch.isdigit())
        last4 = raw_number[-4:] if len(raw_number) >= 4 else raw_number
        number_hash = hashlib.sha256(raw_number.encode()).hexdigest()

        instruction = DebitInstruction.objects.create(
            loan=loan,
            provider=instruction_data.get('provider', 'mock'),
            account_holder_name=instruction_data['account_holder_name'],
            bank_name=instruction_data['bank_name'],
            branch_code=instruction_data.get('branch_code', ''),
            account_type=instruction_data.get('account_type', 'cheque'),
            account_number_last4=last4,
            account_number_encrypted=number_hash,
            status='pending_client',
            created_by=actor,
        )

        try:
            result = provider.create_debit_instruction({
                'loan_id': str(loan.id),
                'account_holder_name': instruction.account_holder_name,
                'account_number': raw_number,
                'bank_name': instruction.bank_name,
                'branch_code': instruction.branch_code,
                'account_type': instruction.account_type,
            })
            instruction.provider_reference = result.get('provider_reference', '')
            instruction.save(update_fields=['provider_reference', 'updated_at'])
        except Exception as e:
            logger.exception("Provider call for debit instruction failed: %s", e)

        AuditService.record(
            actor=actor, action='debit_instruction_created',
            object_type='debit_instruction', object_id=str(instruction.id),
            ip_address=ip_address,
            after_value={'loan_id': str(loan.id), 'provider': instruction.provider,
                         'last4': last4},
        )
        return instruction

    # ── Payments ─────────────────────────────────────────────────
    @staticmethod
    def submit_payment(loan, amount, idempotency_key=None, schedule_id=None,
                       method='debit_order', actor=None, ip_address=None):
        idem = idempotency_key or _make_idem_key(
            'pay', loan.id, amount, timezone.now().isoformat(),
        )
        existing = PaymentTransaction.objects.filter(idempotency_key=idem).first()
        if existing:
            logger.info("Idempotent payment reuse: %s", idem)
            return existing

        provider = get_payment_provider()
        txn = PaymentTransaction.objects.create(
            loan=loan,
            repayment_schedule_id=schedule_id,
            provider=getattr(provider, '__class__').__name__.lower(),
            idempotency_key=idem,
            amount=amount,
            status='processing',
            payment_method=method,
        )
        try:
            result = provider.submit_payment({
                'amount': str(amount),
                'reference': str(loan.id),
                'instruction_reference': (
                    loan.debit_instructions.filter(status='active', is_active=True)
                    .values_list('provider_reference', flat=True).first() or ''
                ),
                'idempotency_key': idem,
            })
            txn.provider_transaction_id = result.get('provider_transaction_id', '')
            txn.status = result.get('status', 'failed')
            txn.raw_payload = result.get('raw', {})
            if txn.status == 'failed':
                txn.decline_code = result.get('decline_code', '')
                txn.decline_reason = result.get('decline_reason', '')
        except Exception as e:
            logger.exception("submit_payment failed: %s", e)
            txn.status = 'failed'
            txn.error_message = str(e)[:1000]
        txn.save(update_fields=[
            'provider_transaction_id', 'status', 'raw_payload',
            'decline_code', 'decline_reason', 'error_message', 'updated_at',
        ])

        AuditService.record(
            actor=actor, action='payment_submitted',
            object_type='payment_transaction', object_id=str(txn.id),
            ip_address=ip_address,
            after_value={'amount': str(amount), 'status': txn.status},
        )

        # If the very first attempt fails synchronously, notify the client.
        if txn.status == 'failed':
            PaymentService._notify_client_payment_failed(txn, is_retry=False)

        return txn

    # ── Client decline notifications ─────────────────────────────
    @staticmethod
    def _notify_client_payment_failed(txn, is_retry: bool = False) -> None:
        """
        Best-effort notification to the client when a debit is declined.

        Never raises — a notification failure must not break the caller
        (webhook processing, poll task, retry submission).
        """
        try:
            from apps.notifications.services import NotificationService

            loan = txn.loan
            client = loan.client
            attempt = txn.attempt_number or 1
            # If this is explicitly a retry, or the attempt number > 1,
            # use the retry template.
            use_retry_template = is_retry or attempt > 1

            reason = (
                txn.decline_reason
                or txn.decline_code
                or txn.error_message
                or 'no reason provided by the bank'
            )

            context = {
                'loan_id': str(loan.id)[:8].upper(),
                'amount': f"{txn.amount:.2f}",
                'failure_date': timezone.localtime(timezone.now()).strftime('%d %B %Y'),
                'decline_reason': reason[:200],
                'attempt_number': attempt,
            }

            if use_retry_template:
                NotificationService.dispatch(
                    client,
                    'payment_retry_failed',
                    context=context,
                    channels=['email', 'in_app'],
                )
            else:
                next_retry = _next_retry_date(loan)
                context['retry_date'] = (
                    next_retry.strftime('%d %B %Y')
                    if next_retry else 'the next working day'
                )
                NotificationService.dispatch(
                    client,
                    'payment_failed',
                    context=context,
                    channels=['email', 'in_app'],
                )
        except Exception:
            logger.exception(
                "Failed to notify client of declined payment for txn %s",
                getattr(txn, 'id', '?'),
            )

    # ── Retry / undisputable handling ────────────────────────────
    @staticmethod
    def schedule_retry(txn, actor, *, retry_at, undisputable=True, reason='',
                       ip_address=None):
        """
        Flag a failed transaction for retry. Set `undisputable=True` when the
        client has signed a mandate that permits irrevocable collection.

        Enforces the loan's max_retry_attempts limit.
        """
        if txn.status != 'failed':
            raise ValueError('Only failed transactions can be retried.')

        loan = txn.loan
        retries = PaymentTransaction.objects.filter(parent_transaction=txn).count()
        if retries >= loan.max_retry_attempts:
            raise ValueError(
                f'Retry limit reached ({loan.max_retry_attempts}) for this instalment. '
                'Write the amount off or escalate to collections.'
            )

        txn.is_undisputable = undisputable
        txn.next_retry_at = retry_at
        txn.retry_reason = reason or ('Undisputable retry' if undisputable else 'Retry')
        txn.retry_scheduled_by = actor
        txn.retry_scheduled_at = timezone.now()
        txn.save(update_fields=[
            'is_undisputable', 'next_retry_at', 'retry_reason',
            'retry_scheduled_by', 'retry_scheduled_at', 'updated_at',
        ])

        AuditService.record(
            actor=actor,
            action='payment_retry_scheduled',
            object_type='payment_transaction',
            object_id=str(txn.id),
            ip_address=ip_address,
            after_value={
                'undisputable': undisputable,
                'retry_at': retry_at.isoformat(),
                'attempt_number': txn.attempt_number,
                'reason': txn.retry_reason,
            },
        )
        logger.info(
            'Retry scheduled for txn %s at %s (undisputable=%s)',
            txn.id, retry_at, undisputable,
        )
        return txn

    @staticmethod
    def cancel_retry(txn, actor, *, reason='', ip_address=None):
        """Cancel a scheduled retry (e.g., client paid manually)."""
        if txn.next_retry_at is None:
            raise ValueError('No retry is scheduled for this transaction.')

        txn.next_retry_at = None
        txn.retry_reason = reason or 'Retry cancelled'
        txn.save(update_fields=['next_retry_at', 'retry_reason', 'updated_at'])

        AuditService.record(
            actor=actor,
            action='payment_retry_cancelled',
            object_type='payment_transaction',
            object_id=str(txn.id),
            ip_address=ip_address,
            after_value={'reason': txn.retry_reason},
        )
        return txn

    @staticmethod
    def _submit_retry(original):
        """
        Internal: create and submit a new PaymentTransaction as a retry of `original`.
        Called by the Celery task when next_retry_at is due.
        """
        loan = original.loan
        instruction = loan.debit_instructions.filter(
            status='active', is_active=True,
        ).first()
        if not instruction:
            logger.warning('Retry skipped — no active mandate on loan %s', loan.id)
            original.next_retry_at = None
            original.save(update_fields=['next_retry_at', 'updated_at'])
            return None

        provider = get_payment_provider()
        idem = _make_idem_key('retry', original.id, timezone.now().isoformat())

        retry = PaymentTransaction.objects.create(
            loan=loan,
            repayment_schedule_id=original.repayment_schedule_id,
            debit_instruction=instruction,
            provider=getattr(provider, '__class__').__name__.lower(),
            idempotency_key=idem,
            amount=original.amount,
            status='processing',
            payment_method=original.payment_method,
            attempt_number=original.attempt_number + 1,
            is_undisputable=original.is_undisputable,
            parent_transaction=original,
            retry_reason=original.retry_reason,
        )

        try:
            result = provider.submit_payment({
                'amount': str(original.amount),
                'reference': str(loan.id),
                'instruction_reference': instruction.provider_reference,
                'idempotency_key': idem,
                'undisputable': original.is_undisputable,
            })
            retry.provider_transaction_id = result.get('provider_transaction_id', '')
            retry.status = result.get('status', 'failed')
            retry.raw_payload = result.get('raw', {})
            if retry.status == 'failed':
                retry.decline_code = result.get('decline_code', '')
                retry.decline_reason = result.get('decline_reason', '')
        except Exception as e:
            logger.exception('Retry submission failed: %s', e)
            retry.status = 'failed'
            retry.error_message = str(e)[:1000]

        retry.save()
        original.next_retry_at = None
        original.save(update_fields=['next_retry_at', 'updated_at'])

        # If the retry also failed, tell the client their account is now overdue.
        if retry.status == 'failed':
            PaymentService._notify_client_payment_failed(retry, is_retry=True)

        return retry

    # ── Webhook handling ─────────────────────────────────────────
    @staticmethod
    @transaction.atomic
    def handle_webhook(provider_name, payload, signature, raw_body: bytes):
        provider = get_payment_provider(provider_name)
        if not provider.verify_webhook_signature(raw_body, signature):
            logger.warning("Invalid webhook signature from %s", provider_name)
            raise ValueError("Invalid signature")

        event = provider.handle_webhook(payload, signature)
        event_id = event.get('provider_event_id') or ''

        if event_id:
            already = PaymentWebhook.objects.filter(
                provider=provider_name, provider_event_id=event_id,
            ).first()
            if already:
                logger.info("Duplicate webhook: %s/%s", provider_name, event_id)
                return already

        webhook = PaymentWebhook.objects.create(
            provider=provider_name,
            webhook_type=event.get('event_type', ''),
            provider_event_id=event_id,
            payload=payload,
            signature=signature,
        )

        txn_to_notify = None
        try:
            txn_id = event.get('provider_transaction_id')
            txn = (
                PaymentTransaction.objects
                .select_for_update()
                .filter(provider_transaction_id=txn_id)
                .first()
            ) if txn_id else None

            if txn:
                previous_status = txn.status
                txn.status = event.get('status', txn.status)
                txn.raw_payload = {**txn.raw_payload, 'webhook': event.get('raw', {})}
                if txn.status == 'failed':
                    txn.decline_code = event.get('decline_code', txn.decline_code)
                    txn.decline_reason = event.get('decline_reason', txn.decline_reason)
                txn.save(update_fields=[
                    'status', 'raw_payload', 'decline_code', 'decline_reason', 'updated_at',
                ])
                webhook.transaction = txn

                if txn.status == 'successful':
                    from apps.repayments.services import RepaymentService
                    RepaymentService.apply_payment(
                        txn.loan, txn.amount,
                        method='debit_order',
                        reference=f'WEBHOOK-{txn.provider_transaction_id}',
                        notes='Applied via provider webhook',
                    )
                elif txn.status == 'failed' and previous_status != 'failed':
                    # Only notify on the transition into 'failed' — this
                    # prevents duplicate emails when the provider resends.
                    txn_to_notify = txn

            webhook.processed = True
        except Exception as e:
            logger.exception("Webhook processing failed: %s", e)
            webhook.processed = False
            webhook.error_message = str(e)[:1000]

        webhook.save(update_fields=['processed', 'error_message', 'transaction', 'updated_at'])

        # Fire the notification outside the transaction so an email failure
        # cannot roll back the webhook record.
        if txn_to_notify is not None:
            PaymentService._notify_client_payment_failed(
                txn_to_notify,
                is_retry=(txn_to_notify.attempt_number or 1) > 1,
            )

        return webhook

    # ── Reconciliation ───────────────────────────────────────────
    @staticmethod
    def reconcile_loan(loan):
        from apps.repayments.models import RepaymentSchedule
        expected = list(
            RepaymentSchedule.objects.filter(
                loan=loan, status__in=['pending', 'partial', 'overdue'],
            ).values('id', 'total_amount', 'scheduled_date')
        )
        actual_txns = list(
            PaymentTransaction.objects.filter(loan=loan, status='successful')
            .values('id', 'amount', 'provider_transaction_id', 'created_at')
        )

        expected_norm = [
            {'id': str(e['id']), 'amount': str(e['total_amount']),
             'date': e['scheduled_date'].isoformat()}
            for e in expected
        ]
        actual_norm = [
            {'id': str(a['id']), 'amount': str(a['amount']),
             'provider_transaction_id': a['provider_transaction_id'],
             'date': a['created_at'].isoformat()}
            for a in actual_txns
        ]

        provider = get_payment_provider()
        results = provider.reconcile_transactions(expected_norm, actual_norm)

        created = []
        for r in results:
            exp_amt = Decimal(r['expected']['amount']) if r['expected'] else Decimal('0.00')
            act_amt = Decimal(r['actual']['amount']) if r['actual'] else Decimal('0.00')
            created.append(ReconciliationRecord.objects.create(
                loan=loan,
                expected_amount=exp_amt,
                actual_amount=act_amt,
                difference=act_amt - exp_amt,
                status=r['status'],
                notes=f"Expected={r['expected']} Actual={r['actual']}",
            ))
        return created

    @staticmethod
    def reconcile_all_active_loans():
        from apps.loans.models import Loan
        summary = {'loans_checked': 0, 'records_created': 0}
        for loan in Loan.objects.filter(status='active').iterator():
            records = PaymentService.reconcile_loan(loan)
            summary['loans_checked'] += 1
            summary['records_created'] += len(records)
        return summary