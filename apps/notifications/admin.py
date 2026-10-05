from django.contrib import admin
from .models import Notification, NotificationPreference, NotificationTemplate


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ('code', 'channel', 'subject', 'is_active')
    list_filter = ('channel', 'is_active')
    search_fields = ('code', 'subject', 'body')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'code', 'channel', 'status', 'sent_at', 'created_at')
    list_filter = ('channel', 'status', 'code')
    search_fields = ('user__email', 'title', 'message')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ('user', 'email_enabled', 'sms_enabled', 'in_app_enabled')
