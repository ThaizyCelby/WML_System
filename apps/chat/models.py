"""Chat conversation and message models."""
from django.db import models

from core.models import TimeStampedModel, UUIDPrimaryKeyModel


class ChatConversation(UUIDPrimaryKeyModel, TimeStampedModel):
    """A single chat session between a user and the AI assistant."""
    user = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE,
        related_name='chat_conversations',
    )
    title = models.CharField(max_length=200, blank=True, default='New Conversation')
    channel = models.CharField(
        max_length=20, default='client',
        choices=[('client', 'Client'), ('staff', 'Staff')],
    )
    is_active = models.BooleanField(default=True)
    last_message_at = models.DateTimeField(null=True, blank=True)
    message_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'chat_conversations'
        ordering = ['-last_message_at', '-created_at']
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['last_message_at']),
        ]

    def __str__(self):
        return f"{self.user.email}: {self.title}"


class ChatMessage(UUIDPrimaryKeyModel, TimeStampedModel):
    """A single message in a conversation."""
    conversation = models.ForeignKey(
        ChatConversation, on_delete=models.CASCADE, related_name='messages',
    )
    role = models.CharField(
        max_length=20,
        choices=[('user', 'User'), ('assistant', 'Assistant'), ('system', 'System')],
    )
    content = models.TextField()
    ai_provider = models.CharField(max_length=50, blank=True, default='')
    ai_model = models.CharField(max_length=100, blank=True, default='')
    ai_metadata = models.JSONField(default=dict, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    token_count = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        db_table = 'chat_messages'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['conversation', 'created_at']),
            models.Index(fields=['role']),
        ]

    def __str__(self):
        return f"{self.role}: {self.content[:60]}"