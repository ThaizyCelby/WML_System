"""Admin configuration for audit app."""
from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Audit log admin (read-only)."""
    list_display = ('id', 'actor_email', 'action', 'object_type', 'object_id', 'created_at')
    list_filter = ('action', 'object_type', 'created_at')
    search_fields = ('actor_email', 'action', 'object_id', 'description')
    readonly_fields = (
        'id', 'actor_email', 'action', 'object_type', 'object_id',
        'before_value', 'after_value', 'ip_address', 'user_agent',
        'correlation_id', 'description', 'created_at',
    )
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
