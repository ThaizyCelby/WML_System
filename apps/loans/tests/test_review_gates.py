"""Tests that workflow transitions cannot skip review gates."""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.loans.models import LoanProduct
from apps.loans.services import LoanApplicationService

User = get_user_model()


@pytest.mark.django_db
class TestReviewGateEnforcement:

    def _staff(self, suffix=''):
        return User.objects.create_user(
            email=f'gatestaff{suffix}@test.com',
            password='TestPass123!',
            is_staff=True, is_superuser=True,
        )

    def _product(self, suffix=''):
        return LoanProduct.objects.create(
            name=f'Gate Test Loan{suffix}',
            min_amount=Decimal('1000.00'),
            max_amount=Decimal('50000.00'),
            min_term=1,
            max_term=24,
            interest_rate=Decimal('28.00'),
            interest_type='flat',
        )

    def _application(self, complete_client, product):
        app = LoanApplicationService.create_application(
            complete_client, product.id, Decimal('10000.00'), 12,
        )
        # complete_client has approved documents, so submit succeeds
        LoanApplicationService.submit_application(app, complete_client)
        return app

    # ── Documents gate ─────────────────────────────────────────────
    def test_document_gate_blocks_kyc_transition(self, complete_client):
        staff = self._staff('1')
        product = self._product('1')
        app = self._application(complete_client, product)

        LoanApplicationService.transition(app, 'document_review', staff)
        with pytest.raises(ValueError, match='documents'):
            LoanApplicationService.transition(app, 'kyc_review', staff)

    def test_document_gate_passes_after_flag(self, complete_client):
        staff = self._staff('2')
        product = self._product('2')
        app = self._application(complete_client, product)

        LoanApplicationService.transition(app, 'document_review', staff)
        LoanApplicationService.mark_documents_reviewed(app, staff)
        LoanApplicationService.transition(app, 'kyc_review', staff)

        app.refresh_from_db()
        assert app.status == 'kyc_review'

    # ── Transactions gate ──────────────────────────────────────────
    def test_transactions_gate_blocks_credit_transition(self, complete_client):
        staff = self._staff('3')
        product = self._product('3')
        app = self._application(complete_client, product)

        LoanApplicationService.transition(app, 'document_review', staff)
        LoanApplicationService.mark_documents_reviewed(app, staff)
        LoanApplicationService.transition(app, 'kyc_review', staff)
        LoanApplicationService.transition(app, 'affordability_review', staff)

        with pytest.raises(ValueError, match='transactions'):
            LoanApplicationService.transition(app, 'credit_review', staff)

    def test_transactions_gate_passes_after_flag(self, complete_client):
        staff = self._staff('4')
        product = self._product('4')
        app = self._application(complete_client, product)

        LoanApplicationService.transition(app, 'document_review', staff)
        LoanApplicationService.mark_documents_reviewed(app, staff)
        LoanApplicationService.transition(app, 'kyc_review', staff)
        LoanApplicationService.transition(app, 'affordability_review', staff)
        LoanApplicationService.mark_transactions_reviewed(app, staff)
        LoanApplicationService.transition(app, 'credit_review', staff)

        app.refresh_from_db()
        assert app.status == 'credit_review'

    # ── Contract gate ──────────────────────────────────────────────
    def test_contract_gate_blocks_disbursement(self, complete_client):
        staff = self._staff('5')
        product = self._product('5')
        app = self._application(complete_client, product)

        # Walk the workflow, ticking the required gates as we go
        LoanApplicationService.transition(app, 'document_review', staff)
        LoanApplicationService.mark_documents_reviewed(app, staff)
        LoanApplicationService.transition(app, 'kyc_review', staff)
        LoanApplicationService.transition(app, 'affordability_review', staff)
        LoanApplicationService.mark_transactions_reviewed(app, staff)
        LoanApplicationService.transition(app, 'credit_review', staff)
        LoanApplicationService.transition(app, 'approved', staff)
        LoanApplicationService.transition(app, 'contract_pending', staff)
        LoanApplicationService.transition(app, 'contract_accepted', staff)

        app.refresh_from_db()

        # Attempt to reach disbursement without verifying the contract
        with pytest.raises(ValueError, match='contract'):
            LoanApplicationService.transition(app, 'disbursement_pending', staff)

        # Verify contract, then the mandate gate fires next
        LoanApplicationService.verify_contract(app, staff)
        with pytest.raises(ValueError, match='mandate'):
            LoanApplicationService.transition(app, 'disbursement_pending', staff)