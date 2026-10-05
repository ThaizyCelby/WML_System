"""Serializers for the support app."""
from rest_framework import serializers

from .models import SupportTicket, TicketMessage


class TicketMessageSerializer(serializers.ModelSerializer):
    author_email = serializers.EmailField(source='author.email', read_only=True)

    class Meta:
        model = TicketMessage
        fields = [
            'id', 'role', 'body', 'is_internal_note',
            'author_email', 'created_at',
        ]
        read_only_fields = fields


class SupportTicketSerializer(serializers.ModelSerializer):
    client_email = serializers.EmailField(source='client.email', read_only=True)
    assigned_to_email = serializers.EmailField(source='assigned_to.email', read_only=True)
    message_count = serializers.SerializerMethodField()

    class Meta:
        model = SupportTicket
        fields = [
            'id', 'subject', 'category', 'priority', 'status',
            'client_email', 'assigned_to_email',
            'related_loan', 'related_application',
            'sla_first_response_due', 'first_response_at',
            'resolution_due', 'resolved_at', 'closed_at',
            'message_count', 'last_message_at', 'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_message_count(self, obj):
        return obj.messages.filter(is_internal_note=False).count()


class TicketCreateSerializer(serializers.Serializer):
    subject = serializers.CharField(max_length=200)
    body = serializers.CharField(max_length=5000)
    category = serializers.ChoiceField(
        choices=[c[0] for c in SupportTicket.CATEGORY_CHOICES],
        default='other',
    )
    priority = serializers.ChoiceField(
        choices=[c[0] for c in SupportTicket.PRIORITY_CHOICES],
        default='normal',
    )
    related_loan = serializers.UUIDField(required=False, allow_null=True)
    related_application = serializers.UUIDField(required=False, allow_null=True)


class TicketReplySerializer(serializers.Serializer):
    body = serializers.CharField(max_length=5000)
    is_internal_note = serializers.BooleanField(default=False)