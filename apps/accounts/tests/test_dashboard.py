"""Dashboard endpoint tests."""
import pytest
from decimal import Decimal
from datetime import date

from apps.accounts.models import User
from apps.loans.models import Loan, LoanApplication, LoanProduct


@pytest.mark.django_db
class TestDashboard:

    def _loan(self, user, amount='5000.00'):
        product = LoanProduct.objects.create(name='P', interest_rate=Decimal('30.00'))
        application = LoanApplication.objects.create(
            client=user, product=product,
            requested_amount=Decimal(amount), requested_term=12, status='active',
        )
        return Loan.objects.create(
            application=application, client=user, product=product,
            principal_amount=Decimal(amount), interest_rate=Decimal('30.00'),
            total_interest=Decimal('0.00'), fees_total=Decimal('0.00'),
            term_periods=12, repayment_frequency='monthly',
            start_date=date.today(), end_date=date.today(),
            outstanding_balance=Decimal(amount), status='active',
        )

    def test_client_dashboard(self, client):
        user = User.objects.create_user(email='cd@x.com', password='TestPass123!')
        self._loan(user)
        client.force_login(user)
        resp = client.get('/api/v1/accounts/dashboard/')
        assert resp.status_code == 200
        assert resp.json()['role'] == 'client'
        assert resp.json()['loans']['active_count'] == 1

    def test_staff_dashboard(self, client):
        staff = User.objects.create_user(
            email='sd@x.com', password='TestPass123!', is_staff=True, is_superuser=True,
        )
        client.force_login(staff)
        resp = client.get('/api/v1/accounts/dashboard/')
        assert resp.status_code == 200
        assert resp.json()['role'] == 'staff'


@pytest.mark.django_db
class TestAuthFlow:

    def test_register_and_login(self, client):
        resp = client.post('/api/v1/accounts/register/', data={
            'email': 'new@x.com', 'password': 'TestPass123!',
            'password_confirm': 'TestPass123!', 'first_name': 'New', 'last_name': 'User',
        }, content_type='application/json')
        assert resp.status_code == 201

        resp = client.post('/api/v1/accounts/login/', data={
            'email': 'new@x.com', 'password': 'TestPass123!',
        }, content_type='application/json')
        assert resp.status_code == 200
        assert 'access' in resp.json()

    def test_weak_password_rejected(self, client):
        resp = client.post('/api/v1/accounts/register/', data={
            'email': 'w@x.com', 'password': '123',
            'password_confirm': '123', 'first_name': 'W', 'last_name': 'U',
        }, content_type='application/json')
        assert resp.status_code == 400
