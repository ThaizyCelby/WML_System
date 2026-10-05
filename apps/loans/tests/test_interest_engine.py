"""Interest engine boundary tests."""
from decimal import Decimal
from apps.loans.interest_engine import (
    calculate_flat_interest,
    calculate_amortized_monthly_payment,
    calculate_total_repayment,
)


class TestInterestEngine:

    def test_flat_interest_basic(self):
        # R5000 @ 30% for 12 months â†’ R1500
        assert calculate_flat_interest(Decimal('5000'), Decimal('30'), 12) == Decimal('1500.00')

    def test_flat_interest_zero_rate(self):
        assert calculate_flat_interest(Decimal('5000'), Decimal('0'), 12) == Decimal('0.00')

    def test_flat_interest_boundary_small(self):
        # R1 @ 30% for 12 months â†’ R0.30
        assert calculate_flat_interest(Decimal('1'), Decimal('30'), 12) == Decimal('0.30')

    def test_flat_interest_large_amount(self):
        # R1,000,000 @ 30% for 12 months â†’ R300,000
        assert calculate_flat_interest(
            Decimal('1000000'), Decimal('30'), 12,
        ) == Decimal('300000.00')

    def test_amortized_returns_positive(self):
        payment = calculate_amortized_monthly_payment(Decimal('5000'), Decimal('30'), 12)
        assert payment > Decimal('0')

    def test_total_repayment_flat(self):
        r = calculate_total_repayment(Decimal('5000'), Decimal('30'), 12, 'flat')
        assert r['total_interest'] == Decimal('1500.00')
        assert r['total_repayment'] == Decimal('6500.00')
        assert len(r['schedule']) == 12

    def test_total_repayment_amortized(self):
        r = calculate_total_repayment(Decimal('5000'), Decimal('30'), 12, 'amortized')
        assert r['total_repayment'] > Decimal('5000')
        assert len(r['schedule']) == 12

    def test_zero_interest(self):
        r = calculate_total_repayment(Decimal('5000'), Decimal('0'), 12, 'flat')
        assert r['total_interest'] == Decimal('0.00')
        assert r['total_repayment'] == Decimal('5000.00')
