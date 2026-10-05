"""
Tenant-scoping helpers.

Every queryset for a tenant-scoped model must pass through `scope_to_user`.
Staff belonging to a vendor only see their vendor's data. Superusers and
platform Administrators see everything.

Usage:
    qs = Loan.objects.all()
    qs = scope_to_user(qs, request.user)
"""
from apps.vendors.models import VendorUser


def user_vendor_ids(user):
    if not user.is_authenticated:
        return []
    if user.is_superuser or user.has_role('Administrator'):
        return None  # None means "no filter — see all"
    return list(
        VendorUser.objects.filter(user=user, is_active=True)
        .values_list('vendor_id', flat=True)
    )


def scope_to_user(qs, user, vendor_field='vendor'):
    """Apply tenant isolation to a queryset that has a vendor FK."""
    ids = user_vendor_ids(user)
    if ids is None:
        return qs
    return qs.filter(**{f'{vendor_field}_id__in': ids})