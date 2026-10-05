from rest_framework import permissions


class IsDocumentOwner(permissions.BasePermission):
    """Object-level permission: only the owner can access their document."""
    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser:
            return True
        if request.user.has_role('Administrator') or request.user.has_role('Credit Officer'):
            return True  # staff can view any document for review
        return obj.client == request.user


class CanUploadDocument(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated
