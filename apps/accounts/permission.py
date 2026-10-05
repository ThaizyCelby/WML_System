"""Custom permissions for accounts app."""
from rest_framework import permissions


class IsOwnerOrAdmin(permissions.BasePermission):
    """Permission that allows access only to the owner or admin."""

    def has_object_permission(self, request, view, obj):
        # Allow if user is accessing their own record
        if obj == request.user:
            return True

        # Allow if user is a superuser
        if request.user.is_superuser:
            return True

        # Check for admin role
        if request.user.has_role('Administrator'):
            return True

        return False


class HasRole(permissions.BasePermission):
    """Permission that checks for a specific role."""

    def __init__(self, role_name: str):
        self.role_name = role_name

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.has_role(self.role_name)


class HasPermission(permissions.BasePermission):
    """Permission that checks for a specific custom permission."""

    def __init__(self, permission_codename: str):
        self.permission_codename = permission_codename

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.has_permission(self.permission_codename)
