"""Affordability engine tests."""
from decimal import Decimal
import pytest
from apps.affordability.engine import AffordabilityEngine


@pytest.mark.django_db
class TestAffordability:

    def test_affordable(self):
        r = AffordabilityEngine.calculate(
            gross_income=Decimal('20000'),
            monthly_expenses=Decimal('7000'),
            existing_debt=Decimal('5000'),
            proposed_repayment=Decimal('2000'),
        )
        assert r['status'] == 'AFFORDABLE'

    def test_borderline(self):
        r = AffordabilityEngine.calculate(
            gross_income=Decimal('20000'),
            monthly_expenses=Decimal('7000'),
            existing_debt=Decimal('5000'),
            proposed_repayment=Decimal('3000'),
        )
        assert r['status'] == 'BORDERLINE'

    def test_not_affordable(self):
        r = AffordabilityEngine.calculate(
            gross_income=Decimal('20000'),
            monthly_expenses=Decimal('7000'),
            existing_debt=Decimal('5000'),
            proposed_repayment=Decimal('6000'),
        )
        assert r['status'] == 'NOT_AFFORDABLE'

    def test_insufficient_data(self):
        r = AffordabilityEngine.calculate(
            gross_income=Decimal('0'),
            monthly_expenses=Decimal('0'),
            existing_debt=Decimal('0'),
            proposed_repayment=Decimal('100'),
        )
        assert r['status'] == 'INSUFFICIENT_DATA'

    def test_zero_repayment_always_affordable(self):
        r = AffordabilityEngine.calculate(
            gross_income=Decimal('10000'),
            monthly_expenses=Decimal('5000'),
            existing_debt=Decimal('0'),
            proposed_repayment=Decimal('0'),
        )
        assert r['status'] == 'AFFORDABLE'
