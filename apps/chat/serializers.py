"""Serializers for the chat app."""
from rest_framework import serializers

from .models import ChatConversation, ChatMessage


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = [
            'id', 'role', 'content', 'ai_provider', 'ai_model',
            'latency_ms', 'created_at',
        ]
        read_only_fields = fields


class ChatConversationSerializer(serializers.ModelSerializer):
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = ChatConversation
        fields = [
            'id', 'title', 'channel', 'is_active',
            'message_count', 'last_message_at', 'created_at', 'last_message',
        ]
        read_only_fields = fields

    def get_last_message(self, obj):
        m = obj.messages.order_by('-created_at').first()
        if not m:
            return None
        return {'role': m.role, 'content': m.content[:200], 'created_at': m.created_at}


class AskRequestSerializer(serializers.Serializer):
    message = serializers.CharField(min_length=1, max_length=2000)
    conversation_id = serializers.UUIDField(required=False, allow_null=True)
    provider = serializers.ChoiceField(
        choices=['openai', 'gemini', 'glm', 'mock'],
        required=False, allow_null=True,
    )