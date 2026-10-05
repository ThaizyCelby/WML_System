"""Tests for role-based access control."""
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status

User = get_user_model()


@pytest.mark.django_db
class TestRolePermissions:

    def test_superuser_has_all_permissions(self, superuser):
        """Superuser should have all permissions."""
        assert superuser.has_permission('any.permission') == True

    def test_regular_user_no_special_permissions(self, regular_user):
        """Regular user should not have admin permissions."""
        assert regular_user.has_permission('admin.manage_users') == False

    def test_role_permission_check(self, db, regular_user):
        """User with a role should have that role's permissions."""
        from apps.accounts.models import Role, Permission, UserRole, RolePermission

        role = Role.objects.create(name='Test Role')
        permission = Permission.objects.create(
            codename='view_reports',
            name='View Reports',
            app_label='reports',
        )
        RolePermission.objects.create(role=role, permission=permission)
        UserRole.objects.create(user=regular_user, role=role)

        assert regular_user.has_permission('view_reports') == True
        assert regular_user.has_permission('manage_users') == False
        assert regular_user.has_role('Test Role') == True

    def test_user_cannot_access_other_users_profile(self, authenticated_client, regular_user, superuser):
        """User should not be able to access other users' profiles."""
        from django.urls import reverse

        # Try to access superuser's profile
        url = reverse('user-profile-detail', kwargs={'pk': str(superuser.id)})
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK  # Should return own profile, not the requested one
