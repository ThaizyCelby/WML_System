"""Serializers for audit logs."""
from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = [
            'id', 'actor_email', 'action', 'object_type', 'object_id',
            'ip_address', 'user_agent', 'correlation_id', 'description',
            'created_at',
        ]
        read_only_fields = fields
