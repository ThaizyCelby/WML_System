"""Admin configuration for accounts app."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User, Role, Permission, UserRole, ClientProfile


@admin.register(User)
class CustomUserAdmin(DjangoUserAdmin):
    """Custom user admin."""
    list_display = ('email', 'first_name', 'last_name', 'is_active', 'is_staff', 'last_login_at')
    list_filter = ('is_active', 'is_staff', 'is_superuser', 'email_verified', 'phone_verified')
    search_fields = ('email', 'first_name', 'last_name', 'phone_number')
    ordering = ('email',)
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'phone_number')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Security', {'fields': ('email_verified', 'phone_verified', 'failed_login_attempts', 'locked_until')}),
        ('MFA', {'fields': ('mfa_enabled',)}),
        ('Important dates', {'fields': ('last_login_at', 'created_at', 'updated_at')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'first_name', 'last_name'),
        }),
    )
    readonly_fields = ('last_login_at', 'created_at', 'updated_at')


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent', 'is_active', 'is_system_role')
    list_filter = ('is_active', 'is_system_role')
    search_fields = ('name', 'description')


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ('codename', 'name', 'app_label', 'is_active')
    list_filter = ('app_label', 'is_active')
    search_fields = ('codename', 'name', 'description')


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'assigned_by', 'created_at')
    list_filter = ('role',)
    search_fields = ('user__email', 'role__name')


@admin.register(ClientProfile)
class ClientProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'id_number', 'kyc_status', 'monthly_income', 'created_at')
    list_filter = ('kyc_status', 'employment_type')
    search_fields = ('user__email', 'id_number', 'employer_name')
    readonly_fields = ('user', 'created_at', 'updated_at')
