from django.contrib import admin
from .models import AffordabilityAssessment


@admin.register(AffordabilityAssessment)
class AffordabilityAssessmentAdmin(admin.ModelAdmin):
    list_display = ('client', 'gross_income', 'proposed_repayment', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('client__email',)
    readonly_fields = ('id', 'client', 'status', 'explanation', 'result_data', 'created_at', 'updated_at')
