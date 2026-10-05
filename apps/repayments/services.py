"""Repayment schedule generation and loan allocation."""
import logging
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction

from apps.loans.interest_engine import calculate_total_repayment

from .models import RepaymentSchedule, Repayment

logger = logging.getLogger('apps.repayments')


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        nxt = date(year + 1, 1, 1)
    else:
        nxt = date(year, month + 1, 1)
    return (nxt - date(year, month, 1)).days


def _add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, _days_in_month(year, month))
    return date(year, month, day)


def _snap_to_day(d: date, day: int) -> date:
    """Return the date in the same month on `day`. Clamps if day > days_in_month."""
    year, month = d.year, d.month
    last_day = _days_in_month(year, month)
    return date(year, month, min(day, last_day))


def _compute_dates(start_date: date, frequency: str, count: int,
                   collection_day: int = None) -> list:
    """
    Compute repayment dates. If `collection_day` is set and the frequency is
    monthly, each date is snapped to that day-of-month.
    """
    dates = []
    current = start_date
    for _ in range(count):
        if frequency == 'monthly':
            current = _add_months(current, 1)
            if collection_day:
                current = _snap_to_day(current, collection_day)
        elif frequency == 'weekly':
            current = current + timedelta(days=7)
        elif frequency == 'fortnightly':
            current = current + timedelta(days=14)
        elif frequency == 'daily':
            current = current + timedelta(days=1)
        else:
            current = _add_months(current, 1)
        dates.append(current)
    return dates


class RepaymentScheduleService:

    @staticmethod
    @transaction.atomic
    def generate_schedule(loan):
        if RepaymentSchedule.objects.filter(loan=loan).exists():
            return RepaymentSchedule.objects.filter(loan=loan)

        product = loan.product
        interest_type = product.interest_type if product else 'flat'
        result = calculate_total_repayment(
            principal=loan.principal_amount,
            annual_rate=loan.interest_rate,
            term_months=loan.term_periods,
            interest_type=interest_type,
        )
        schedule_data = result['schedule']
        expected_total = result['total_repayment']
        dates = _compute_dates(
            loan.start_date or date.today(),
            loan.repayment_frequency,
            len(schedule_data),
            collection_day=loan.collection_day,
        )

        # Build rows with running balance, absorb rounding drift in last row
        rows_data = []
        balance = loan.principal_amount
        running_total = Decimal('0.00')
        for i, row in enumerate(schedule_data):
            balance -= row['principal']
            if balance < 0:
                balance = Decimal('0.00')
            running_total += row['payment']
            rows_data.append({
                'period': row['period'],
                'scheduled_date': dates[i],
                'principal': row['principal'],
                'interest': row['interest'],
                'payment': row['payment'],
                'balance_after': balance,
            })

        drift = expected_total - running_total
        if drift != Decimal('0.00') and rows_data:
            last = rows_data[-1]
            last['payment'] = (last['payment'] + drift).quantize(Decimal('0.01'))
            last['principal'] = (last['principal'] + drift).quantize(Decimal('0.01'))
            rows_data[-1] = last

        objects = [
            RepaymentSchedule(
                loan=loan,
                period_number=r['period'],
                scheduled_date=r['scheduled_date'],
                principal_portion=r['principal'],
                interest_portion=r['interest'],
                fees_portion=Decimal('0.00'),
                total_amount=r['payment'],
                balance_after=r['balance_after'],
                status='pending',
            )
            for r in rows_data
        ]
        RepaymentSchedule.objects.bulk_create(objects)
        logger.info("Generated %d schedule rows for loan %s", len(objects), loan.id)
        return RepaymentSchedule.objects.filter(loan=loan)


class RepaymentService:

    @staticmethod
    @transaction.atomic
    def apply_payment(loan, amount, actual_date=None, method='debit_order',
                      reference='', notes=''):
        from apps.loans.models import Loan

        amount = Decimal(str(amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if amount <= 0:
            raise ValueError("Amount must be positive.")
        actual_date = actual_date or date.today()

        locked_loan = Loan.objects.select_for_update().get(pk=loan.pk)
        payment = Repayment.objects.create(
            loan=locked_loan, amount=amount, actual_date=actual_date,
            method=method, reference=reference, status='successful', notes=notes,
        )

        remaining = amount
        schedules = RepaymentSchedule.objects.select_for_update().filter(
            loan=locked_loan, status__in=['pending', 'partial', 'overdue'],
        ).order_by('period_number')

        for sched in schedules:
            if remaining <= 0:
                break
            outstanding = sched.total_amount - sched.amount_paid
            if outstanding <= 0:
                continue
            allocation = min(remaining, outstanding)
            sched.amount_paid += allocation
            sched.status = 'paid' if sched.amount_paid >= sched.total_amount else 'partial'
            sched.save(update_fields=['amount_paid', 'status', 'updated_at'])
            if payment.schedule_id is None:
                payment.schedule = sched
                payment.save(update_fields=['schedule'])
            remaining -= allocation

        total_outstanding = sum(
            (s.total_amount - s.amount_paid)
            for s in RepaymentSchedule.objects.filter(loan=locked_loan)
        )
        locked_loan.outstanding_balance = total_outstanding
        if total_outstanding <= Decimal('0.00'):
            locked_loan.status = 'paid'
        locked_loan.save(update_fields=['outstanding_balance', 'status', 'updated_at'])
        return payment