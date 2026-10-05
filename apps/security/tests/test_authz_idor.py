"""IDOR and authorization tests."""
import pytest
from decimal import Decimal
from datetime import date

from apps.accounts.models import User
from apps.loans.models import Loan, LoanApplication, LoanProduct


@pytest.mark.django_db
class TestIDOR:

    def test_user_cannot_view_other_user_loan(self, client):
        u1 = User.objects.create_user(email='a@x.com', password='TestPass123!')
        u2 = User.objects.create_user(email='b@x.com', password='TestPass123!')
        product = LoanProduct.objects.create(name='P')
        application = LoanApplication.objects.create(
            client=u1, product=product,
            requested_amount=Decimal('1000'), requested_term=6, status='active',
        )
        loan = Loan.objects.create(
            application=application, client=u1, product=product,
            principal_amount=Decimal('1000'), interest_rate=Decimal('30'),
            total_interest=Decimal('0'), fees_total=Decimal('0'),
            term_periods=6, repayment_frequency='monthly',
            start_date=date.today(), end_date=date.today(),
            outstanding_balance=Decimal('1000'), status='active',
        )
        client.force_login(u2)
        # Try to access u1's loan
        resp = client.get(f'/api/v1/loans/loans/{loan.id}/')
        assert resp.status_code == 404

    def test_anonymous_cannot_access_protected(self, client):
        resp = client.get('/api/v1/loans/loans/')
        assert resp.status_code in (401, 403)
