"""Loan business logic: applications, transitions, loan creation."""
import logging
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from apps.audit.services import AuditService

from .models import LoanApplication, LoanApplicationEvent, Loan, LoanProduct

logger = logging.getLogger('apps.loans')


TRANSITIONS = {
    'draft': ['submitted', 'cancelled'],
    'submitted': ['document_review', 'kyc_review', 'rejected', 'cancelled'],
    'document_review': ['kyc_review', 'rejected', 'cancelled'],
    'kyc_review': ['affordability_review', 'rejected', 'cancelled'],
    'affordability_review': ['credit_review', 'rejected', 'cancelled'],
    'credit_review': ['approved', 'rejected', 'cancelled'],
    'approved': ['contract_pending', 'rejected', 'cancelled'],
    'contract_pending': ['contract_accepted', 'rejected', 'cancelled'],
    'contract_accepted': ['disbursement_pending', 'rejected', 'cancelled'],
    'disbursement_pending': ['active', 'rejected', 'cancelled'],
    'active': ['paid', 'overdue', 'defaulted', 'restructured'],
    'overdue': ['active', 'defaulted', 'restructured'],
    'defaulted': ['restructured'],
    'rejected': ['submitted'],
    'cancelled': [],
}


# ──────────────────────────────────────────────────────────────────────
# Review-gate definitions.
#
# Each entry says: to enter this status, the given boolean field must be
# True. Fields are set explicitly by the corresponding admin action
# (mark_documents_reviewed, mark_transactions_reviewed, verify_contract)
# — they are NOT inferred from status movement.
#
# This prevents the workflow from silently advancing past a gate the
# admin never actually confirmed, which caused the earlier case where a
# client reached contract_accepted with all three flags still PENDING.
# ──────────────────────────────────────────────────────────────────────
GATES = {
    'kyc_review': (
        'documents_reviewed',
        'Confirm the documents have been reviewed before moving to KYC.',
    ),
    'credit_review': (
        'transactions_reviewed',
        'Confirm the bank transactions have been reviewed before credit review.',
    ),
    'disbursement_pending': (
        'contract_verified_by_admin',
        'Verify the signed contract before disbursing funds.',
    ),
}


class LoanApplicationService:

    @staticmethod
    def create_application(client, product_id, amount, term):
        product = LoanProduct.objects.get(id=product_id, is_active=True)
        application = LoanApplication.objects.create(
            client=client, product=product,
            requested_amount=amount, requested_term=term, status='draft',
        )
        LoanApplicationEvent.objects.create(
            application=application, from_status='', to_status='draft', actor=client,
        )
        AuditService.record(
            actor=client, action='loan_application_created',
            object_type='loan_application', object_id=str(application.id),
            after_value={'product': product.name, 'amount': str(amount), 'term': term},
        )
        return application

    @staticmethod
    def submit_application(application, actor, ip_address=None):
        from apps.kyc.services import get_missing_documents

        if application.status != 'draft':
            raise ValueError("Only draft applications can be submitted.")

        missing = get_missing_documents(actor)
        if missing:
            names = ', '.join(m['label'] for m in missing)
            raise ValueError(
                f"Please upload the following documents before submitting: {names}."
            )

        application.status = 'submitted'
        application.submitted_at = timezone.now()
        application.save(update_fields=['status', 'submitted_at', 'updated_at'])

        LoanApplicationEvent.objects.create(
            application=application,
            from_status='draft', to_status='submitted', actor=actor,
        )
        AuditService.record(
            actor=actor, action='loan_application_submitted',
            object_type='loan_application', object_id=str(application.id),
            ip_address=ip_address,
        )

    # ── Admin review gates ────────────────────────────────────────
    @staticmethod
    @transaction.atomic
    def mark_documents_reviewed(application, actor, reviewed=True, ip_address=None):
        application.documents_reviewed = reviewed
        application.save(update_fields=['documents_reviewed', 'updated_at'])
        AuditService.record(
            actor=actor, action='application_documents_reviewed',
            object_type='loan_application', object_id=str(application.id),
            ip_address=ip_address,
            after_value={'documents_reviewed': reviewed},
        )
        return application

    @staticmethod
    @transaction.atomic
    def mark_transactions_reviewed(application, actor, reviewed=True, ip_address=None):
        application.transactions_reviewed = reviewed
        application.save(update_fields=['transactions_reviewed', 'updated_at'])
        AuditService.record(
            actor=actor, action='application_transactions_reviewed',
            object_type='loan_application', object_id=str(application.id),
            ip_address=ip_address,
            after_value={'transactions_reviewed': reviewed},
        )
        return application

    @staticmethod
    @transaction.atomic
    def verify_contract(application, actor, ip_address=None):
        application.contract_verified_by_admin = True
        application.contract_verified_at = timezone.now()
        application.contract_verified_by = actor
        application.save(update_fields=[
            'contract_verified_by_admin',
            'contract_verified_at',
            'contract_verified_by',
            'updated_at',
        ])
        AuditService.record(
            actor=actor, action='application_contract_verified',
            object_type='loan_application', object_id=str(application.id),
            ip_address=ip_address,
        )
        return application

    # ── Transition ────────────────────────────────────────────────
    @staticmethod
    @transaction.atomic
    def transition(application, to_status, actor, notes='', ip_address=None):
        from_status = application.status
        if to_status not in TRANSITIONS.get(from_status, []):
            raise ValueError(f"Invalid transition: {from_status} -> {to_status}")

        # ── Review-gate enforcement ───────────────────────────────
        # The workflow cannot advance past a gate the admin has not
        # explicitly confirmed. This is the fix for the earlier bug
        # where an application reached contract_accepted with all
        # three flags still PENDING.
        gate = GATES.get(to_status)
        if gate:
            field_name, message = gate
            if not getattr(application, field_name, False):
                raise ValueError(message)

        # ── Mandate gate before disbursement ──────────────────────
        if to_status == 'disbursement_pending':
            loan = getattr(application, 'loan', None)
            if not loan:
                raise ValueError("No loan exists for this application.")
            has_active_mandate = loan.debit_instructions.filter(
                status='active', is_active=True,
            ).exists()
            if not has_active_mandate:
                raise ValueError(
                    'An active debit mandate is required before disbursement.'
                )

        application.status = to_status

        update_fields = ['status', 'updated_at']
        if to_status in (
            'document_review', 'kyc_review', 'affordability_review',
            'credit_review', 'approved', 'rejected',
        ):
            application.reviewed_at = timezone.now()
            update_fields.append('reviewed_at')

        application.save(update_fields=update_fields)

        LoanApplicationEvent.objects.create(
            application=application, from_status=from_status,
            to_status=to_status, actor=actor, notes=notes,
        )
        AuditService.record(
            actor=actor, action=f'loan_application_{to_status}',
            object_type='loan_application', object_id=str(application.id),
            before_value={'status': from_status}, after_value={'status': to_status},
            ip_address=ip_address, description=notes,
        )

        # ── Side effects ─────────────────────────────────────────
        if to_status == 'contract_pending':
            LoanApplicationService._create_loan_for_application(application, actor, ip_address)

        if to_status == 'contract_accepted':
            try:
                from apps.notifications.services import NotificationService
                NotificationService.dispatch(
                    application.client, 'mandate_setup_required',
                    context={
                        'name': application.client.full_name or application.client.email,
                        'loan_id': str(application.loan_id) if hasattr(application, 'loan') else '',
                    },
                )
            except Exception:
                logger.exception(
                    'Failed to dispatch mandate_setup_required for application %s',
                    application.id,
                )

        if to_status == 'active' and hasattr(application, 'loan'):
            loan = application.loan
            loan.status = 'active'
            loan.save(update_fields=['status', 'updated_at'])

        return application

    # ── Internal: create loan + schedule + agreement ─────────────
    @staticmethod
    def _create_loan_for_application(application, actor, ip_address):
        from apps.repayments.services import RepaymentScheduleService
        from apps.loans.interest_engine import calculate_total_repayment
        from .agreement_service import LoanAgreementService

        if hasattr(application, 'loan'):
            return application.loan

        product = application.product
        if not product:
            raise ValueError("No product on application.")

        principal = application.approved_amount or application.requested_amount
        term = application.approved_term or application.requested_term
        rate = application.interest_rate or product.interest_rate

        result = calculate_total_repayment(principal, rate, term, product.interest_type)
        total_interest = result['total_interest']
        origination_fee = (
            principal * (product.origination_fee_percent or Decimal('0')) / Decimal('100')
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        start_date = timezone.now().date()
        end_date = start_date + timedelta(days=30 * term)
        total_outstanding = principal + total_interest + origination_fee

        loan = Loan.objects.create(
            application=application, client=application.client, product=product,
            principal_amount=principal, interest_rate=rate,
            total_interest=total_interest, fees_total=origination_fee,
            term_periods=term, repayment_frequency=product.repayment_frequency,
            start_date=start_date, end_date=end_date,
            outstanding_balance=total_outstanding, status='pending',
            collection_day=application.client_payday,
        )
        RepaymentScheduleService.generate_schedule(loan)
        LoanAgreementService.generate_agreement(loan, actor=actor, ip_address=ip_address)
        logger.info("Created loan %s for application %s", loan.id, application.id)
        return loan


class LoanService:
    """Operations on active/past loans."""

    @staticmethod
    def recompute_default_risk(loan) -> dict:
        from .fallout import compute_risk
        risk = compute_risk(loan)
        loan.default_risk_score = risk['score']
        loan.default_risk_band = risk['band']
        loan.default_risk_updated_at = timezone.now()
        loan.save(update_fields=[
            'default_risk_score', 'default_risk_band',
            'default_risk_updated_at', 'updated_at',
        ])
        return risk

    @staticmethod
    def recompute_all_active_risks():
        """Batch job — recompute for every non-paid loan."""
        summary = {'loans': 0, 'critical': 0, 'high': 0}
        for loan in Loan.objects.exclude(status='paid').iterator():
            risk = LoanService.recompute_default_risk(loan)
            summary['loans'] += 1
            if risk['band'] == 'critical':
                summary['critical'] += 1
            elif risk['band'] == 'high':
                summary['high'] += 1
        return summary