"""Loan application workflow tests."""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.loans.models import LoanProduct
from apps.loans.services import LoanApplicationService

User = get_user_model()


@pytest.mark.django_db
class TestLoanWorkflow:

    def _fixtures(self, suffix=''):
        user = User.objects.create_user(
            email=f'workflow{suffix}@wethu.test', password='TestPass123!',
        )
        staff = User.objects.create_user(
            email=f'staff{suffix}@wethu.test', password='TestPass123!',
            is_staff=True, is_superuser=True,
        )
        product = LoanProduct.objects.create(
            name=f'Test Loan{suffix}',
            interest_rate=Decimal('30.00'),
            interest_type='flat',
        )
        return user, staff, product

    def test_full_workflow(self, complete_client):
        """Full workflow with a fully compliant client — ticks each gate."""
        staff = User.objects.create_user(
            email='staff2@wethu.test', password='TestPass123!',
            is_staff=True, is_superuser=True,
        )
        product = LoanProduct.objects.create(
            name='Workflow Loan',
            interest_rate=Decimal('30.00'),
            interest_type='flat',
        )

        app = LoanApplicationService.create_application(
            complete_client, product.id, Decimal('5000.00'), 12,
        )
        LoanApplicationService.submit_application(app, complete_client)
        app.refresh_from_db()
        assert app.status == 'submitted'

        # Walk the review stage, ticking each gate just before its
        # dependent transition fires.
        for status in (
            'document_review',
            'kyc_review',
            'affordability_review',
            'credit_review',
            'approved',
            'contract_pending',
        ):
            if status == 'kyc_review':
                LoanApplicationService.mark_documents_reviewed(app, staff)
            if status == 'credit_review':
                LoanApplicationService.mark_transactions_reviewed(app, staff)

            LoanApplicationService.transition(app, status, staff)
            app.refresh_from_db()
            assert app.status == status

        # A loan with a 12-period schedule should now exist.
        assert hasattr(app, 'loan')
        assert app.loan.repayment_schedule.count() == 12

    def test_submit_requires_complete_profile(self):
        """A user with an incomplete profile cannot submit."""
        user, _, product = self._fixtures('a')
        app = LoanApplicationService.create_application(
            user, product.id, Decimal('1000.00'), 6,
        )
        with pytest.raises(ValueError, match='upload'):
            LoanApplicationService.submit_application(app, user)

    def test_invalid_transition_rejected(self, complete_client):
        """Skipping a stage must raise."""
        _, staff, product = self._fixtures('b')
        app = LoanApplicationService.create_application(
            complete_client, product.id, Decimal('1000.00'), 6,
        )
        with pytest.raises(ValueError, match='Invalid transition'):
            LoanApplicationService.transition(app, 'active', staff)