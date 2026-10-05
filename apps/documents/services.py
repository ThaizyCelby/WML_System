"""Document storage and retrieval services."""
import hashlib
import logging
import os
import uuid

from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import timezone

from apps.audit.services import AuditService
from apps.security.services import SecurityEventService

from .models import Document, DocumentVersion
from .providers.mock import MockVirusScanner
from .providers.clamav import ClamAVScanner

logger = logging.getLogger('apps.documents')


class DocumentService:
    @staticmethod
    def get_scanner():
        """Return the appropriate virus scanner for the environment."""
        if settings.DEBUG:
            return MockVirusScanner()
        return ClamAVScanner()

    @staticmethod
    def upload_document(client, file_obj, document_type, uploaded_by=None, ip_address=None):
        """
        Upload a new document (or new version). Validates, stores, scans,
        runs KYC extraction for identity documents, and records audit.
        """
        from .validators import validate_file_size, validate_mime_type, validate_file_extension

        # ── Enforce replacement policy ────────────────────────────────
        existing = Document.objects.filter(
            client=client, document_type=document_type,
        ).order_by('-created_at').first()

        if existing and existing.status in ('submitted', 'approved'):
            allowed = existing.replacement_requests.filter(status='approved').exists()
            if not allowed:
                raise ValueError(
                    'This document is under review or has already been approved. '
                    'Request a correction from staff before replacing it.'
                )

        # ── Validate file ─────────────────────────────────────────────
        validate_file_size(file_obj)
        validate_mime_type(file_obj)
        validate_file_extension(file_obj)

        # ── Generate storage key and hash ─────────────────────────────
        file_obj.seek(0)
        content = file_obj.read()
        file_hash = hashlib.sha256(content).hexdigest()
        ext = os.path.splitext(file_obj.name)[1] or ''
        storage_key = f"documents/{uuid.uuid4().hex}/{uuid.uuid4().hex}{ext}"

        # ── Store file (private storage) ──────────────────────────────
        file_obj.seek(0)
        default_storage.save(storage_key, file_obj)
        file_size = file_obj.size
        original_name = file_obj.name
        content_type = file_obj.content_type or 'application/octet-stream'

        # ── Create or version the Document ────────────────────────────
        document = existing
        if document and document.status in (
            'submitted', 'approved', 'awaiting_reupload', 'pending', 'scanning', 'rejected',
        ):
            version_number = document.versions.count() + 1
            document.original_filename = original_name
            document.mime_type = content_type
            document.file_size = file_size
            document.storage_key = storage_key
            document.status = 'scanning'
            document.virus_scan_status = 'pending'
            document.save(update_fields=[
                'original_filename', 'mime_type', 'file_size', 'storage_key',
                'status', 'virus_scan_status', 'updated_at',
            ])
        else:
            document = Document.objects.create(
                client=client,
                document_type=document_type,
                original_filename=original_name,
                mime_type=content_type,
                file_size=file_size,
                storage_key=storage_key,
                status='scanning',
                virus_scan_status='pending',
            )
            version_number = 1

        DocumentVersion.objects.create(
            document=document,
            version_number=version_number,
            storage_key=storage_key,
            file_hash=file_hash,
            uploaded_by=uploaded_by,
        )

        # ── Consume any approved replacement request ──────────────────
        if existing and existing.status == 'awaiting_reupload':
            existing.replacement_requests.filter(status='approved').update(status='consumed')

        # ── Scan for viruses ──────────────────────────────────────────
        DocumentService.scan_document(document.id)

        # ── KYC extraction for identity documents ─────────────────────
        DocumentService._maybe_extract_identity(document, client)

        # ── Audit log ─────────────────────────────────────────────────
        AuditService.record(
            actor=uploaded_by,
            action='document_uploaded',
            object_type='document',
            object_id=str(document.id),
            ip_address=ip_address,
            after_value={'filename': original_name, 'size': file_size},
        )

        return document

    @staticmethod
    def scan_document(document_id):
        """Scan a document for viruses. On success, set status to `submitted`."""
        document = Document.objects.get(id=document_id)
        scanner = DocumentService.get_scanner()

        try:
            file_path = document.storage_key
            if hasattr(default_storage, 'path'):
                try:
                    file_path = default_storage.path(document.storage_key)
                except NotImplementedError:
                    pass

            clean, details = scanner.scan(file_path)
            if clean:
                document.virus_scan_status = 'clean'
                document.status = 'submitted'
                document.virus_scan_result = details
            else:
                document.virus_scan_status = 'infected'
                document.status = 'quarantined'
                document.virus_scan_result = details
                SecurityEventService.record(
                    event_type='malware_detected',
                    user_id=str(document.client_id),
                    risk_score=90,
                    severity='critical',
                    description=f'Malware detected in uploaded file: {document.original_filename}',
                )
        except Exception as e:
            document.virus_scan_status = 'error'
            document.status = 'rejected'
            document.virus_scan_result = str(e)

        document.save(update_fields=['virus_scan_status', 'status', 'virus_scan_result', 'updated_at'])

    @staticmethod
    def _maybe_extract_identity(document, client):
        """OCR / AI extraction for identity documents."""
        identity_types = {'identity_document', 'id_document', 'sa_id', 'passport'}
        if document.document_type not in identity_types:
            return

        try:
            from apps.kyc.ocr_service import extract_identity_from_document
        except ImportError:
            logger.info("OCR service not available; skipping identity extraction.")
            return

        try:
            result = extract_identity_from_document(document)
        except Exception as e:
            logger.exception("KYC extraction crashed: %s", e)
            return

        if not result:
            return

        extracted_id = result.get('id_number')
        if not extracted_id:
            logger.info("No ID number extracted from document %s", document.id)
            return

        try:
            profile = client.client_profile
        except Exception:
            logger.info("Client %s has no ClientProfile; extraction not persisted.", client.id)
            return

        updated_fields = []
        if not profile.id_number:
            profile.id_number = extracted_id
            updated_fields.append('id_number')

        if not profile.date_of_birth and result.get('date_of_birth'):
            from datetime import date
            dob_val = result['date_of_birth']
            if isinstance(dob_val, str):
                try:
                    profile.date_of_birth = date.fromisoformat(dob_val)
                    updated_fields.append('date_of_birth')
                except ValueError:
                    pass

        if updated_fields:
            profile.save(update_fields=updated_fields + ['updated_at'])
            logger.info(
                "Populated ClientProfile for %s from document %s: %s",
                client.email, document.id, updated_fields,
            )

        document.virus_scan_result = (
            f"OCR | source={result.get('source')} | "
            f"confidence={result.get('confidence')} | "
            f"validated={result.get('validated')} | "
            f"document_type={result.get('document_type')}"
        )
        document.save(update_fields=['virus_scan_result', 'updated_at'])

    @staticmethod
    def get_download_url(document: Document, actor=None, ip_address=None) -> str:
        """Return a URL for downloading the latest version."""
        if document.status != 'approved':
            raise PermissionError('Document is not approved for download.')

        document.access_count += 1
        document.last_accessed_at = timezone.now()
        document.save(update_fields=['access_count', 'last_accessed_at', 'updated_at'])

        if settings.DEFAULT_FILE_STORAGE == 'django.core.files.storage.FileSystemStorage':
            return f"/api/v1/documents/{document.id}/download/"

        return default_storage.url(document.storage_key)