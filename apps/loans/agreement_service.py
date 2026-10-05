"""Loan agreement generation (PDF) and digital acceptance."""
import hashlib
import io
import logging
import uuid

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.audit.services import AuditService

from .models import Loan, LoanAgreement

logger = logging.getLogger('apps.loans')


def _fmt_zar(v):
    try:
        return f"R {v:,.2f}"
    except Exception:
        return str(v)


class LoanAgreementService:
    @staticmethod
    def generate_agreement(loan: Loan, actor=None, ip_address=None) -> LoanAgreement:
        # Remove prior non-accepted agreements
        LoanAgreement.objects.filter(loan=loan).exclude(status='accepted').delete()
        existing = LoanAgreement.objects.filter(loan=loan).order_by('-version').first()
        version = (existing.version + 1) if existing else 1

        pdf_bytes = LoanAgreementService._build_pdf(loan)
        file_hash = hashlib.sha256(pdf_bytes).hexdigest()
        storage_key = f"agreements/{loan.id}/v{version}-{uuid.uuid4().hex}.pdf"
        default_storage.save(storage_key, ContentFile(pdf_bytes))

        agreement = LoanAgreement.objects.create(
            loan=loan, version=version,
            pdf_storage_key=storage_key,
            agreement_hash=file_hash, status='sent',
        )
        AuditService.record(
            actor=actor, action='loan_agreement_generated',
            object_type='loan_agreement', object_id=str(agreement.id),
            ip_address=ip_address,
            after_value={'loan_id': str(loan.id), 'version': version, 'hash': file_hash},
        )
        return agreement

    @staticmethod
    def accept_agreement(agreement: LoanAgreement, user, ip_address=None, user_agent=''):
        if agreement.status == 'accepted':
            return agreement
        agreement.status = 'accepted'
        agreement.accepted_at = timezone.now()
        agreement.accepted_by = user
        agreement.accepted_ip = ip_address
        agreement.accepted_user_agent = user_agent or ''
        agreement.save(update_fields=[
            'status', 'accepted_at', 'accepted_by', 'accepted_ip',
            'accepted_user_agent', 'updated_at',
        ])
        AuditService.record(
            actor=user, action='loan_agreement_accepted',
            object_type='loan_agreement', object_id=str(agreement.id),
            ip_address=ip_address,
            after_value={'loan_id': str(agreement.loan_id), 'hash': agreement.agreement_hash},
        )
        return agreement

    @staticmethod
    def _build_pdf(loan: Loan) -> bytes:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            leftMargin=2 * cm, rightMargin=2 * cm,
            topMargin=2 * cm, bottomMargin=2 * cm,
        )
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=18, spaceAfter=12)
        h2 = ParagraphStyle('H2', parent=styles['Heading2'], spaceBefore=12, spaceAfter=6)

        story = []
        story.append(Paragraph("Wethu Micro Lenders Loan Agreement", title_style))
        story.append(Paragraph(
            f"Agreement Reference: <b>{loan.id}</b><br/>"
            f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M')} SAST",
            styles['Normal'],
        ))
        story.append(Spacer(1, 0.4 * cm))

        summary_data = [
            ["Borrower", getattr(loan.client, 'full_name', loan.client.email)],
            ["Email", loan.client.email],
            ["Product", loan.product.name if loan.product else "-"],
            ["Principal", _fmt_zar(loan.principal_amount)],
            ["Interest Rate (annual)", f"{loan.interest_rate}%"],
            ["Interest Type", (loan.product.interest_type.title() if loan.product else "Flat")],
            ["Term", f"{loan.term_periods} periods ({loan.repayment_frequency})"],
            ["Total Interest", _fmt_zar(loan.total_interest)],
            ["Fees", _fmt_zar(loan.fees_total)],
            ["Total Repayable", _fmt_zar(loan.principal_amount + loan.total_interest + loan.fees_total)],
            ["Start Date", loan.start_date.strftime('%Y-%m-%d') if loan.start_date else "-"],
            ["End Date", loan.end_date.strftime('%Y-%m-%d') if loan.end_date else "-"],
        ]
        summary_table = Table(summary_data, colWidths=[5 * cm, 10 * cm])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.whitesmoke),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 0.5 * cm))

        story.append(Paragraph("Repayment Schedule", h2))
        schedule = list(loan.repayment_schedule.order_by('period_number'))
        sched_rows = [["#", "Due Date", "Principal", "Interest", "Total", "Balance"]]
        for s in schedule:
            sched_rows.append([
                str(s.period_number),
                s.scheduled_date.strftime('%Y-%m-%d'),
                _fmt_zar(s.principal_portion),
                _fmt_zar(s.interest_portion),
                _fmt_zar(s.total_amount),
                _fmt_zar(s.balance_after),
            ])
        sched_table = Table(sched_rows, colWidths=[1.2 * cm, 2.7 * cm, 3 * cm, 2.5 * cm, 2.5 * cm, 3 * cm])
        sched_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
        ]))
        story.append(sched_table)
        story.append(Spacer(1, 0.5 * cm))

        story.append(Paragraph("Disclosures", h2))
        story.append(Paragraph(
            "1. The Borrower agrees to repay the Principal plus Interest per the schedule above.<br/>"
            "2. Interest is calculated at the stated annual rate using the agreed interest method.<br/>"
            "3. Late payments may incur a fee.<br/>"
            "4. This agreement is governed by applicable South African credit law.<br/>"
            "5. The Borrower confirms they have the authority to enter this agreement.",
            styles['Normal'],
        ))
        story.append(Spacer(1, 0.5 * cm))
        story.append(Paragraph("Acceptance", h2))
        story.append(Paragraph(
            "By accepting electronically, the Borrower acknowledges and agrees to all terms.",
            styles['Normal'],
        ))

        doc.build(story)
        pdf_value = buffer.getvalue()
        buffer.close()
        return pdf_value
