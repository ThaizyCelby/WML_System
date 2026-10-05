from django.contrib import admin

from .models import Vendor, VendorUser


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'ncr_number', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug', 'ncr_number', 'email')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(VendorUser)
class VendorUserAdmin(admin.ModelAdmin):
    list_display = ('user', 'vendor', 'is_admin', 'is_active', 'created_at')
    list_filter = ('is_admin', 'is_active', 'vendor')
    search_fields = ('user__email', 'vendor__name')