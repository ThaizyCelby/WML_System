"""KYC business logic."""
import logging
from typing import List, Dict

from django.db import transaction

from apps.accounts.models import ClientProfile
from apps.audit.services import AuditService

logger = logging.getLogger('apps.kyc')


# ──────────────────────────────────────────────────────────────────────
# Required documents for a loan application
# ──────────────────────────────────────────────────────────────────────
REQUIRED_DOCUMENT_TYPES_FOR_APPLICATION = [
    ('identity_document', 'Identity document (ID or passport)'),
    ('proof_of_address', 'Proof of address'),
    ('payslip', 'Latest payslip'),
    ('bank_statement', 'Bank statement (3 months)'),
]


def get_missing_documents(user) -> List[Dict[str, str]]:
    """
    Return a list of {code, label} for required documents the user has not
    uploaded yet. Documents that are submitted (awaiting staff review) or
    approved count as uploaded — the client should not be blocked while
    waiting for review.
    """
    from apps.documents.models import Document

    acceptable = ('submitted', 'approved', 'awaiting_reupload')

    uploaded_types = set(
        Document.objects
        .filter(client=user, status__in=acceptable)
        .values_list('document_type', flat=True)
        .distinct()
    )

    missing = []
    for code, label in REQUIRED_DOCUMENT_TYPES_FOR_APPLICATION:
        if code not in uploaded_types:
            missing.append({'code': code, 'label': label})
    return missing


def has_all_required_documents(user) -> bool:
    return not get_missing_documents(user)


# ──────────────────────────────────────────────────────────────────────
# KYC status transitions
# ──────────────────────────────────────────────────────────────────────
VALID_TRANSITIONS = {
    'pending': ['submitted', 'under_review', 'failed', 'suspended'],
    'submitted': ['under_review', 'additional_info_required', 'failed', 'suspended'],
    'under_review': ['verified', 'failed', 'additional_info_required', 'suspended'],
    'verified': ['suspended'],
    'failed': ['submitted', 'under_review'],
    'additional_info_required': ['submitted', 'under_review'],
    'suspended': ['pending', 'verified'],
}


class KYCService:
    @staticmethod
    def submit_kyc(client_profile: ClientProfile, actor=None, ip_address=None):
        KYCService._transition(client_profile, 'submitted', actor, ip_address)

    @staticmethod
    def start_review(client_profile: ClientProfile, actor=None, ip_address=None):
        KYCService._transition(client_profile, 'under_review', actor, ip_address)

    @staticmethod
    def approve(client_profile: ClientProfile, actor=None, ip_address=None, notes=''):
        KYCService._transition(client_profile, 'verified', actor, ip_address, notes)

    @staticmethod
    def reject(client_profile: ClientProfile, actor=None, ip_address=None, notes=''):
        KYCService._transition(client_profile, 'failed', actor, ip_address, notes)

    @staticmethod
    def request_additional_info(client_profile: ClientProfile, actor=None, ip_address=None, notes=''):
        KYCService._transition(client_profile, 'additional_info_required', actor, ip_address, notes)

    @staticmethod
    def suspend(client_profile: ClientProfile, actor=None, ip_address=None, notes=''):
        KYCService._transition(client_profile, 'suspended', actor, ip_address, notes)

    @staticmethod
    def _transition(client_profile, new_status, actor=None, ip_address=None, notes=''):
        old_status = client_profile.kyc_status
        if old_status == new_status:
            return

        allowed = VALID_TRANSITIONS.get(old_status, [])
        if new_status not in allowed:
            raise ValueError(
                f"Invalid KYC status transition: {old_status} -> {new_status}"
            )

        with transaction.atomic():
            client_profile.kyc_status = new_status
            client_profile.save(update_fields=['kyc_status', 'updated_at'])

            from .models import KYCReview
            KYCReview.objects.create(
                client_profile=client_profile,
                reviewed_by=actor,
                previous_status=old_status,
                new_status=new_status,
                notes=notes,
            )

            AuditService.record(
                actor=actor,
                action='kyc_status_changed',
                object_type='client_profile',
                object_id=str(client_profile.id),
                before_value={'kyc_status': old_status},
                after_value={'kyc_status': new_status},
                ip_address=ip_address,
                description=f'KYC status changed from {old_status} to {new_status}',
            )


# ──────────────────────────────────────────────────────────────────────
# Staff-side document review (approve / reject uploaded documents)
# ──────────────────────────────────────────────────────────────────────
class DocumentReviewService:
    """Staff review of uploaded documents."""

    @staticmethod
    def approve(document, actor, notes='', ip_address=None):
        from django.utils import timezone

        if document.status not in ('submitted', 'scanning'):
            raise ValueError('Only submitted documents can be approved.')

        document.status = 'approved'
        document.reviewed_by = actor
        document.reviewed_at = timezone.now()
        document.review_notes = notes
        document.save(update_fields=[
            'status', 'reviewed_by', 'reviewed_at', 'review_notes', 'updated_at',
        ])

        try:
            from apps.notifications.services import NotificationService
            NotificationService.dispatch(
                document.client, 'document_approved',
                context={
                    'name': getattr(document.client, 'full_name', document.client.email),
                    'document_type': document.document_type,
                },
            )
        except Exception:
            pass

        AuditService.record(
            actor=actor, action='document_approved',
            object_type='document', object_id=str(document.id),
            ip_address=ip_address,
            after_value={'notes': notes},
        )
        return document

    @staticmethod
    def reject(document, actor, notes='', ip_address=None):
        from django.utils import timezone

        if document.status not in ('submitted', 'scanning'):
            raise ValueError('Only submitted documents can be rejected.')

        document.status = 'rejected'
        document.reviewed_by = actor
        document.reviewed_at = timezone.now()
        document.review_notes = notes
        document.save(update_fields=[
            'status', 'reviewed_by', 'reviewed_at', 'review_notes', 'updated_at',
        ])

        try:
            from apps.notifications.services import NotificationService
            NotificationService.dispatch(
                document.client, 'document_rejected',
                context={
                    'name': getattr(document.client, 'full_name', document.client.email),
                    'document_type': document.document_type,
                    'notes': notes,
                },
            )
        except Exception:
            pass

        AuditService.record(
            actor=actor, action='document_rejected',
            object_type='document', object_id=str(document.id),
            ip_address=ip_address,
            after_value={'notes': notes},
        )
        return document


# ──────────────────────────────────────────────────────────────────────
# Staff-side handling of client document replacement requests
# ──────────────────────────────────────────────────────────────────────
class DocumentReplacementService:
    """Approve or reject a client's request to replace an approved document."""

    @staticmethod
    def approve_request(req, actor, notes='', ip_address=None):
        from django.utils import timezone

        if req.status != 'pending':
            raise ValueError('Only pending requests can be approved.')

        req.status = 'approved'
        req.reviewed_by = actor
        req.reviewed_at = timezone.now()
        req.review_notes = notes
        req.save(update_fields=[
            'status', 'reviewed_by', 'reviewed_at', 'review_notes', 'updated_at',
        ])

        doc = req.document
        doc.status = 'awaiting_reupload'
        doc.save(update_fields=['status', 'updated_at'])

        try:
            from apps.notifications.services import NotificationService
            NotificationService.dispatch(
                req.requested_by, 'document_replacement_approved',
                context={
                    'name': getattr(req.requested_by, 'full_name', req.requested_by.email),
                    'document_type': doc.document_type,
                    'notes': notes,
                },
            )
        except Exception:
            pass

        AuditService.record(
            actor=actor, action='document_replacement_approved',
            object_type='document_replacement_request', object_id=str(req.id),
            ip_address=ip_address,
            after_value={'document_id': str(doc.id), 'notes': notes},
        )
        return req

    @staticmethod
    def reject_request(req, actor, notes='', ip_address=None):
        from django.utils import timezone

        if req.status != 'pending':
            raise ValueError('Only pending requests can be rejected.')

        req.status = 'rejected'
        req.reviewed_by = actor
        req.reviewed_at = timezone.now()
        req.review_notes = notes
        req.save(update_fields=[
            'status', 'reviewed_by', 'reviewed_at', 'review_notes', 'updated_at',
        ])

        try:
            from apps.notifications.services import NotificationService
            NotificationService.dispatch(
                req.requested_by, 'document_replacement_rejected',
                context={
                    'name': getattr(req.requested_by, 'full_name', req.requested_by.email),
                    'document_type': req.document.document_type,
                    'notes': notes,
                },
            )
        except Exception:
            pass

        AuditService.record(
            actor=actor, action='document_replacement_rejected',
            object_type='document_replacement_request', object_id=str(req.id),
            ip_address=ip_address,
            after_value={'notes': notes},
        )
        return req