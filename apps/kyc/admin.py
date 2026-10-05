from django.contrib import admin

from .models import KYCDocumentRequirement, KYCReview


@admin.register(KYCDocumentRequirement)
class KYCDocumentRequirementAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_mandatory', 'is_active', 'order')
    list_filter = ('is_mandatory', 'is_active')
    search_fields = ('name', 'description')


@admin.register(KYCReview)
class KYCReviewAdmin(admin.ModelAdmin):
    list_display = ('client_profile', 'previous_status', 'new_status', 'reviewed_by', 'reviewed_at')
    list_filter = ('new_status',)
    search_fields = ('client_profile__user__email',)
    readonly_fields = ('id', 'client_profile', 'reviewed_by', 'previous_status', 'new_status', 'notes', 'reviewed_at')
