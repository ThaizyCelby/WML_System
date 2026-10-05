"""Admin configuration for security app."""
from django.contrib import admin

from .models import BlockedIP, RiskAssessment, SecurityEvent
from .models import FraudAlert, LoginAttempt, UserDevice

@admin.register(SecurityEvent)
class SecurityEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'event_type', 'risk_score', 'severity', 'ip_address', 'resolution', 'created_at')
    list_filter = ('event_type', 'severity', 'resolution', 'created_at')
    search_fields = ('ip_address', 'description', 'event_type')
    readonly_fields = (
        'id', 'event_type', 'risk_score', 'severity', 'ip_address',
        'user_agent', 'description', 'ai_explanation', 'action_taken',
        'resolution', 'reviewed_by', 'reviewed_at', 'created_at',
    )
    ordering = ('-created_at',)


@admin.register(BlockedIP)
class BlockedIPAdmin(admin.ModelAdmin):
    list_display = ('id', 'ip_address', 'is_active', 'blocked_until', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('ip_address', 'reason')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(RiskAssessment)
class RiskAssessmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'risk_score', 'risk_level', 'created_at')
    list_filter = ('risk_level', 'created_at')
    search_fields = ('user__email',)
    readonly_fields = ('id', 'user', 'risk_score', 'risk_level', 'factors', 'ai_analysis', 'created_at', 'updated_at')


@admin.register(FraudAlert)
class FraudAlertAdmin(admin.ModelAdmin):
    list_display = ('id', 'alert_type', 'severity', 'risk_score', 'status',
                    'assigned_to', 'created_at')
    list_filter = ('severity', 'status', 'alert_type')
    search_fields = ('summary', 'alert_type', 'user_id')
    readonly_fields = ('id', 'user_id', 'source_event', 'alert_type', 'risk_score',
                       'severity', 'summary', 'details', 'signals', 'ai_analysis',
                       'created_at', 'updated_at')


@admin.register(UserDevice)
class UserDeviceAdmin(admin.ModelAdmin):
    list_display = ('user', 'fingerprint', 'is_trusted', 'seen_count', 'last_seen')
    list_filter = ('is_trusted',)
    search_fields = ('user__email', 'fingerprint')


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ('email', 'ip_address', 'success', 'created_at')
    list_filter = ('success',)
    search_fields = ('email', 'ip_address')
    readonly_fields = ('id', 'user', 'email', 'ip_address', 'user_agent',
                       'success', 'failure_reason', 'created_at')
