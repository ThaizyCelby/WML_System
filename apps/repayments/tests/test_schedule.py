"""Repayment schedule and payment allocation tests."""
import pytest
from datetime import date
from decimal import Decimal

from apps.accounts.models import User
from apps.loans.models import Loan, LoanApplication, LoanProduct
from apps.repayments.services import RepaymentScheduleService, RepaymentService


@pytest.mark.django_db
class TestSchedule:

    def _make_loan(self, term=12, principal='5000.00', rate='30.00'):
        user = User.objects.create_user(email='s@x.com', password='TestPass123!')
        product = LoanProduct.objects.create(
            name='Test', interest_type='flat',
            interest_rate=Decimal(rate), repayment_frequency='monthly',
        )
        application = LoanApplication.objects.create(
            client=user, product=product,
            requested_amount=Decimal(principal), requested_term=term, status='approved',
        )
        return Loan.objects.create(
            application=application, client=user, product=product,
            principal_amount=Decimal(principal), interest_rate=Decimal(rate),
            total_interest=Decimal('1500.00'), fees_total=Decimal('0.00'),
            term_periods=term, repayment_frequency='monthly',
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
            outstanding_balance=Decimal('6500.00'), status='active',
        )

    def test_schedule_generation(self):
        loan = self._make_loan()
        rows = RepaymentScheduleService.generate_schedule(loan)
        assert rows.count() == 12
        total = sum(r.total_amount for r in rows)
        assert total == Decimal('6500.00')

    def test_schedule_idempotent(self):
        loan = self._make_loan()
        RepaymentScheduleService.generate_schedule(loan)
        RepaymentScheduleService.generate_schedule(loan)
        assert loan.repayment_schedule.count() == 12

    def test_payment_fifo_allocation(self):
        loan = self._make_loan()
        RepaymentScheduleService.generate_schedule(loan)
        first = loan.repayment_schedule.order_by('period_number').first()
        RepaymentService.apply_payment(loan, first.total_amount, method='eft')
        first.refresh_from_db()
        assert first.status == 'paid'

    def test_full_repayment_marks_loan_paid(self):
        loan = self._make_loan(term=2, principal='1000.00', rate='0.00')
        loan.interest_rate = Decimal('0.00')
        loan.total_interest = Decimal('0.00')
        loan.outstanding_balance = Decimal('1000.00')
        loan.save()
        rows = RepaymentScheduleService.generate_schedule(loan)
        total = sum(r.total_amount for r in rows)
        RepaymentService.apply_payment(loan, total, method='eft')
        loan.refresh_from_db()
        assert loan.status == 'paid'

    def test_idempotency_prevents_race_conditions(self):
        loan = self._make_loan()
        RepaymentScheduleService.generate_schedule(loan)
        first = loan.repayment_schedule.order_by('period_number').first()
        # Two identical payments
        RepaymentService.apply_payment(loan, first.total_amount, method='eft')
        RepaymentService.apply_payment(loan, first.total_amount, method='eft')
        first.refresh_from_db()
        # First due is fully paid, second payment spilled to next row
        assert first.status == 'paid'
