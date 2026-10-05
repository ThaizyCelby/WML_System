"""Document models for secure file storage."""
import uuid

from django.db import models

from core.models import TimeStampedModel, UUIDPrimaryKeyModel


class Document(UUIDPrimaryKeyModel, TimeStampedModel):
    """
    Main document metadata. Actual files are stored privately.
    """
    organisation = models.ForeignKey(
        'accounts.Organisation', null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='documents',
        db_index=True,
    )

    client = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='documents',
    )
    document_type = models.CharField(max_length=50, db_index=True)
    original_filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=100)
    file_size = models.PositiveBigIntegerField()
    storage_key = models.CharField(max_length=500, unique=True, db_index=True)
    status = models.CharField(
        max_length=20,
        default='pending',
        choices=[
            ('pending', 'Pending'),
            ('scanning', 'Scanning'),
            ('submitted', 'Submitted'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('quarantined', 'Quarantined'),
            ('awaiting_reupload', 'Awaiting Re-upload'),
        ],
    )
    virus_scan_status = models.CharField(
        max_length=20,
        default='pending',
        choices=[
            ('pending', 'Pending'),
            ('clean', 'Clean'),
            ('infected', 'Infected'),
            ('error', 'Error'),
        ],
    )
    virus_scan_result = models.TextField(blank=True, default='')
    retention_until = models.DateTimeField(null=True, blank=True)
    access_count = models.PositiveIntegerField(default=0)
    last_accessed_at = models.DateTimeField(null=True, blank=True)

    # Staff review tracking
    reviewed_by = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='reviewed_documents',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'documents'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['client', 'document_type']),
            models.Index(fields=['status']),
            models.Index(fields=['organisation', 'status']),
        ]

    def __str__(self):
        return f"{self.document_type}: {self.original_filename}"


class DocumentVersion(UUIDPrimaryKeyModel, TimeStampedModel):
    """
    Immutable version of a document. Each upload creates a new version.
    """
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='versions')
    version_number = models.PositiveIntegerField()
    storage_key = models.CharField(max_length=500)
    file_hash = models.CharField(max_length=64)
    uploaded_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='uploaded_document_versions',
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'document_versions'
        unique_together = [('document', 'version_number')]
        ordering = ['-version_number']

    def __str__(self):
        return f"v{self.version_number} of {self.document_id}"


class DocumentReplacementRequest(UUIDPrimaryKeyModel, TimeStampedModel):
    """A client's request to replace an already-approved document."""
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name='replacement_requests',
    )
    requested_by = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE, related_name='replacement_requests',
    )
    reason = models.TextField(blank=True, default='')
    status = models.CharField(
        max_length=20,
        default='pending',
        choices=[
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('consumed', 'Consumed'),
        ],
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='reviewed_replacement_requests',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'document_replacement_requests'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['document', 'status']),
        ]

    def __str__(self):
        return f"Replace {self.document_id} ({self.status})"