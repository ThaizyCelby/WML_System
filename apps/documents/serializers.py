from rest_framework import serializers

from .models import Document, DocumentVersion


class DocumentSerializer(serializers.ModelSerializer):
    uploaded_by_email = serializers.EmailField(source='uploaded_by.email', read_only=True)

    class Meta:
        model = Document
        fields = [
            'id', 'document_type', 'original_filename', 'mime_type',
            'file_size', 'status', 'virus_scan_status', 'created_at',
            'updated_at', 'uploaded_by_email',
        ]
        read_only_fields = fields


class DocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField(required=True)
    document_type = serializers.CharField(required=True, max_length=50)
