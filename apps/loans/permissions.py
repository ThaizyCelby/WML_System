"""Permissions for loan endpoints."""
from rest_framework import permissions


class IsClientOwner(permissions.BasePermission):
    """Object-level permission: only the client owner or staff can access."""
    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser or request.user.has_role('Administrator') or request.user.has_role('Credit Officer'):
            return True
        return obj.client == request.user


class CanReviewLoan(permissions.BasePermission):
    """Allow only staff with appropriate roles."""
    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False
        return (
            user.is_superuser or
            user.has_role('Credit Officer') or
            user.has_role('Administrator')
        )
