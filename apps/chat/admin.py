"""Admin configuration for the chat app."""
from django.contrib import admin

from .models import ChatConversation, ChatMessage


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    readonly_fields = (
        'role', 'content', 'ai_provider', 'ai_model',
        'latency_ms', 'created_at',
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ChatConversation)
class ChatConversationAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'title', 'channel',
        'is_active', 'message_count', 'last_message_at',
    )
    list_filter = ('channel', 'is_active')
    search_fields = ('user__email', 'title')
    readonly_fields = (
        'id', 'created_at', 'updated_at',
        'message_count', 'last_message_at',
    )
    inlines = [ChatMessageInline]


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'conversation', 'role', 'ai_provider', 'short_content', 'created_at')
    list_filter = ('role', 'ai_provider')
    search_fields = ('content',)
    readonly_fields = (
        'id', 'conversation', 'role', 'content',
        'ai_provider', 'ai_model', 'ai_metadata',
        'latency_ms', 'token_count', 'created_at', 'updated_at',
    )

    def short_content(self, obj):
        return obj.content[:80] if obj.content else ''
    short_content.short_description = 'Content'