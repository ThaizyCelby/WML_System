"""Debit-order mandate lifecycle: signing, review, activation."""
import hashlib
import logging
import uuid

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone

from apps.audit.services import AuditService

logger = logging.getLogger('apps.payments')


class MandateService:

    @staticmethod
    @transaction.atomic
    def create_mandate(
        *,
        loan,
        account_holder_name,
        account_number,
        bank_name,
        branch_code='',
        account_type='cheque',
        signed_by,
        ip_address=None,
        user_agent='',
    ):
        """
        Create a new mandate in 'pending_client' status.
        Called by the client when entering their banking details.
        """
        from .models import DebitInstruction

        # Prevent duplicate active/pending mandates for the same loan
        existing = DebitInstruction.objects.filter(
            loan=loan, status__in=['pending_client', 'pending_review', 'active'],
        ).first()
        if existing:
            raise ValueError('A mandate already exists for this loan.')

        # Mask the account number (only last 4 chars stored in clear)
        clean_number = ''.join(ch for ch in account_number if ch.isdigit())
        last4 = clean_number[-4:] if len(clean_number) >= 4 else clean_number

        # Simple hash of the raw number (for integrity verification)
        # In production: encrypt the full number using a KMS-managed key.
        number_hash = hashlib.sha256(clean_number.encode()).hexdigest()

        instruction = DebitInstruction.objects.create(
            loan=loan,
            provider='mock',
            account_holder_name=account_holder_name.strip(),
            bank_name=bank_name.strip(),
            branch_code=branch_code.strip(),
            account_type=account_type,
            account_number_last4=last4,
            account_number_encrypted=number_hash,  # TODO: encrypt with KMS
            status='pending_client',
            is_active=False,
        )
        instruction.mandate_signed_by = signed_by
        instruction.mandate_ip = ip_address
        instruction.mandate_user_agent = user_agent or ''
        instruction.save(update_fields=[
            'mandate_signed_by', 'mandate_ip', 'mandate_user_agent', 'updated_at',
        ])

        AuditService.record(
            actor=signed_by,
            action='debit_mandate_created',
            object_type='debit_instruction',
            object_id=str(instruction.id),
            ip_address=ip_address,
            after_value={'bank': bank_name, 'last4': last4},
        )
        return instruction

    @staticmethod
    @transaction.atomic
    def sign_mandate(instruction, signed_by, ip_address=None, user_agent=''):
        if instruction.status not in ('draft', 'pending_client'):
            raise ValueError('This mandate cannot be signed in its current state.')

        instruction.mandate_signed_at = timezone.now()
        instruction.mandate_ip = ip_address
        instruction.mandate_user_agent = user_agent or ''

        pdf_bytes = MandateService._build_pdf(instruction, signed_by)
        pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()
        storage_key = f"mandates/{instruction.loan_id}/mandate-{uuid.uuid4().hex}.pdf"
        default_storage.save(storage_key, ContentFile(pdf_bytes))

        instruction.mandate_pdf_storage_key = storage_key
        instruction.mandate_hash = pdf_hash
        instruction.mandate_reference_number = uuid.uuid4().hex[:12].upper()
        instruction.status = 'pending_review'
        instruction.save()

        AuditService.record(
            actor=signed_by,
            action='debit_mandate_signed',
            object_type='debit_instruction',
            object_id=str(instruction.id),
            ip_address=ip_address,
            after_value={'hash': pdf_hash, 'reference': instruction.mandate_reference_number},
        )

        # Advance the loan application
        application = getattr(instruction.loan, 'application', None)
        if application and application.status == 'mandate_required':
            from apps.loans.services import LoanApplicationService
            try:
                LoanApplicationService.transition(
                    application, 'mandate_signed', signed_by,
                    notes='Client signed debit mandate', ip_address=ip_address,
                )
            except ValueError as e:
                logger.warning("Could not advance application: %s", e)
                pass

        return instruction

    @staticmethod
    @transaction.atomic
    def activate(instruction, actor, notes='', ip_address=None):
        if instruction.status != 'pending_review':
            raise ValueError('Only mandates pending review can be activated.')

        instruction.status = 'active'
        instruction.is_active = True
        instruction.reviewed_by = actor
        instruction.reviewed_at = timezone.now()
        instruction.review_notes = notes
        instruction.save()

        AuditService.record(
            actor=actor,
            action='debit_mandate_activated',
            object_type='debit_instruction',
            object_id=str(instruction.id),
            ip_address=ip_address,
        )

        # Advance the application: mandate_signed → agreement_pending
        application = getattr(instruction.loan, 'application', None)
        if application and application.status == 'mandate_signed':
            from apps.loans.services import LoanApplicationService
            LoanApplicationService.transition(
                application, 'agreement_pending', actor,
                notes='Mandate activated; agreement generated',
                ip_address=ip_address,
            )

        return instruction

    @staticmethod
    @transaction.atomic
    def reject(instruction, actor, reason='', ip_address=None):
        if instruction.status != 'pending_review':
            raise ValueError('Only mandates pending review can be rejected.')

        instruction.status = 'rejected'
        instruction.is_active = False
        instruction.reviewed_by = actor
        instruction.reviewed_at = timezone.now()
        instruction.rejection_reason = reason
        instruction.save()

        AuditService.record(
            actor=actor,
            action='debit_mandate_rejected',
            object_type='debit_instruction',
            object_id=str(instruction.id),
            ip_address=ip_address,
            after_value={'reason': reason},
        )
        return instruction

    @staticmethod
    def _build_pdf(instruction, signed_by) -> bytes:
        """Generate the mandate PDF the client signs."""
        import io
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            leftMargin=2 * cm, rightMargin=2 * cm,
            topMargin=2 * cm, bottomMargin=2 * cm,
        )
        styles = getSampleStyleSheet()
        story = [
            Paragraph("Wethu Micro Lenders — Debit Order Mandate", styles['Title']),
            Spacer(1, 0.5 * cm),
            Paragraph(
                f"Mandate Reference: {instruction.mandate_reference_number or 'pending'}<br/>"
                f"Loan: {instruction.loan_id}<br/>"
                f"Client: {signed_by.email}<br/>"
                f"Date: {timezone.now().strftime('%Y-%m-%d %H:%M')} SAST",
                styles['Normal'],
            ),
            Spacer(1, 0.5 * cm),
            Paragraph(
                "<b>Account Holder:</b> "
                f"{instruction.account_holder_name}<br/>"
                f"<b>Bank:</b> {instruction.bank_name}<br/>"
                f"<b>Account:</b> ****{instruction.account_number_last4}<br/>"
                f"<b>Branch Code:</b> {instruction.branch_code or 'N/A'}<br/>"
                f"<b>Account Type:</b> {instruction.account_type.title()}",
                styles['Normal'],
            ),
            Spacer(1, 0.7 * cm),
            Paragraph(
                "I hereby authorise Wethu Micro Lenders and its authorised payment "
                "service providers to debit my account for the amounts and on the "
                "dates set out in my loan agreement. I understand that I may cancel "
                "this mandate at any time by giving notice as set out in the "
                "agreement, and that reasonable advance notice will be given before "
                "each collection. This mandate is governed by South African law.",
                styles['Normal'],
            ),
            Spacer(1, 0.7 * cm),
            Paragraph(
                f"<b>Signed by:</b> {signed_by.full_name}<br/>"
                f"<b>Email:</b> {signed_by.email}<br/>"
                f"<b>Signed at (IP):</b> {instruction.mandate_ip or 'unknown'}",
                styles['Normal'],
            ),
        ]
        doc.build(story)
        pdf = buffer.getvalue()
        buffer.close()
        return pdf