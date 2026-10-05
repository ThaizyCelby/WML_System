"""Vendor (tenant) models."""
from django.db import models

from core.models import TimeStampedModel, UUIDPrimaryKeyModel


class Vendor(UUIDPrimaryKeyModel, TimeStampedModel):
    """
    A credit provider operating on the platform.
    Each Vendor is a tenant — their staff can only see their own data.
    """
    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=200, unique=True, db_index=True)
    registration_number = models.CharField(max_length=50, blank=True, default='')
    ncr_number = models.CharField(max_length=50, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    phone = models.CharField(max_length=20, blank=True, default='')
    address = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    settings = models.JSONField(default=dict, blank=True)
    max_exposure = models.DecimalField(
        max_digits=15, decimal_places=2, default=1000000,
    )

    class Meta:
        db_table = 'vendors'
        ordering = ['name']

    def __str__(self):
        return self.name


class VendorUser(UUIDPrimaryKeyModel, TimeStampedModel):
    """Links a user to a vendor with an optional per-vendor role."""
    user = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE, related_name='vendor_memberships',
    )
    vendor = models.ForeignKey(
        Vendor, on_delete=models.CASCADE, related_name='members',
    )
    is_admin = models.BooleanField(default=False)
    job_title = models.CharField(max_length=100, blank=True, default='')
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'vendor_users'
        unique_together = [('user', 'vendor')]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} @ {self.vendor.name}"


def user_vendor_ids(user):
    """Return the IDs of vendors a user belongs to (for query filtering)."""
    if not user.is_authenticated:
        return []
    return list(
        VendorUser.objects.filter(user=user, is_active=True)
        .values_list('vendor_id', flat=True)
    )