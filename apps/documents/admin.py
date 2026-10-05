from django.contrib import admin

from .models import Document, DocumentVersion


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('id', 'client', 'document_type', 'status', 'virus_scan_status', 'created_at')
    list_filter = ('document_type', 'status', 'virus_scan_status')
    search_fields = ('client__email', 'original_filename')
    readonly_fields = ('id', 'client', 'original_filename', 'mime_type', 'file_size',
                       'storage_key', 'status', 'virus_scan_status', 'virus_scan_result',
                       'created_at', 'updated_at')


@admin.register(DocumentVersion)
class DocumentVersionAdmin(admin.ModelAdmin):
    list_display = ('document', 'version_number', 'file_hash', 'uploaded_by', 'uploaded_at')
    list_filter = ('uploaded_at',)
    search_fields = ('file_hash',)
    readonly_fields = ('id', 'document', 'version_number', 'storage_key', 'file_hash',
                       'uploaded_by', 'uploaded_at')
