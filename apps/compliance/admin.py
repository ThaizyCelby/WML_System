from django.contrib import admin

from .models import (
    CompliancePolicy, ComplianceTask, DataProcessor,
    DataSubjectRequest, SecurityIncident,
)


@admin.register(CompliancePolicy)
class CompliancePolicyAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'version', 'status', 'effective_date', 'next_review_date')
    list_filter = ('category', 'status')
    search_fields = ('name', 'summary')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(DataProcessor)
class DataProcessorAdmin(admin.ModelAdmin):
    list_display = ('name', 'processor_type', 'country', 'is_active', 'contract_expires_at')
    list_filter = ('processor_type', 'is_active', 'is_cross_border')
    search_fields = ('name', 'contact_email')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(ComplianceTask)
class ComplianceTaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'frequency', 'status', 'due_date', 'owner')
    list_filter = ('category', 'status', 'frequency')
    search_fields = ('title', 'description')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(DataSubjectRequest)
class DataSubjectRequestAdmin(admin.ModelAdmin):
    list_display = ('requestor_email', 'request_type', 'status', 'received_at', 'sla_due_at')
    list_filter = ('request_type', 'status')
    search_fields = ('requestor_name', 'requestor_email', 'request_details')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(SecurityIncident)
class SecurityIncidentAdmin(admin.ModelAdmin):
    list_display = ('title', 'incident_type', 'severity', 'status', 'detected_at', 'requires_notification')
    list_filter = ('incident_type', 'severity', 'status', 'requires_notification')
    search_fields = ('title', 'description')
    readonly_fields = ('id', 'created_at', 'updated_at')