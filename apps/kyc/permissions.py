"""Permissions for KYC endpoints."""
from rest_framework import permissions


class CanReviewKYC(permissions.BasePermission):
    """
    Allow staff to view KYC records and start reviews.

    Includes Credit Officer because credit officers need to see the KYC
    state of an application they are reviewing.
    """
    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False
        return (
            user.is_superuser or
            user.has_role('Credit Officer') or
            user.has_role('Compliance Officer') or
            user.has_role('Administrator')
        )


class CanVerifyKYC(permissions.BasePermission):
    """
    Allow only Compliance Officer or Superuser to make final KYC
    decisions (approve, reject, request additional info, suspend).

    SECURITY - Segregation of duties:
    A Credit Officer who reviews loan applications must NOT be the same
    person who verifies the client's identity documents. This prevents
    a single staff member from fabricating KYC approvals for fraudulent
    applications.
    """
    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False
        return (
            user.is_superuser or
            user.has_role('Compliance Officer') or
            user.has_role('Administrator')
        )