from django.contrib import admin

from .models import SupportTicket, TicketMessage


class TicketMessageInline(admin.TabularInline):
    model = TicketMessage
    extra = 0
    readonly_fields = ('author', 'role', 'body', 'is_internal_note', 'created_at')
    can_delete = False


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'subject', 'client', 'category', 'priority', 'status',
                    'assigned_to', 'last_message_at')
    list_filter = ('status', 'priority', 'category')
    search_fields = ('subject', 'client__email', 'client__first_name', 'client__last_name')
    readonly_fields = ('id', 'created_at', 'updated_at', 'sla_first_response_due',
                       'first_response_at', 'resolution_due', 'resolved_at', 'closed_at')
    inlines = [TicketMessageInline]


@admin.register(TicketMessage)
class TicketMessageAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'role', 'author', 'is_internal_note', 'created_at')
    list_filter = ('role', 'is_internal_note')
    search_fields = ('body',)
    readonly_fields = ('id', 'created_at', 'updated_at')