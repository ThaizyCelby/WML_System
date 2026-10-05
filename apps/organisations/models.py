"""Organisation (tenant) model."""
from django.db import models

from core.models import TimeStampedModel, UUIDPrimaryKeyModel


class Organisation(UUIDPrimaryKeyModel, TimeStampedModel):
    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=80, unique=True, db_index=True)
    legal_name = models.CharField(max_length=200, blank=True, default='')
    registration_number = models.CharField(max_length=80, blank=True, default='')
    ncr_number = models.CharField(max_length=80, blank=True, default='')
    vat_number = models.CharField(max_length=50, blank=True, default='')

    contact_email = models.EmailField(blank=True, default='')
    contact_phone = models.CharField(max_length=30, blank=True, default='')
    website = models.URLField(blank=True, default='')

    address_line1 = models.CharField(max_length=200, blank=True, default='')
    address_line2 = models.CharField(max_length=200, blank=True, default='')
    city = models.CharField(max_length=100, blank=True, default='')
    province = models.CharField(max_length=100, blank=True, default='')
    postal_code = models.CharField(max_length=20, blank=True, default='')
    country = models.CharField(max_length=100, default='South Africa')

    status = models.CharField(
        max_length=20, default='active',
        choices=[
            ('pending', 'Pending'),
            ('active', 'Active'),
            ('suspended', 'Suspended'),
            ('inactive', 'Inactive'),
        ],
        db_index=True,
    )
    is_active = models.BooleanField(default=True, db_index=True)

    subscription_plan = models.CharField(max_length=50, default='standard')
    subscription_expires_at = models.DateTimeField(null=True, blank=True)

    feature_flags = models.JSONField(default=dict, blank=True)
    lending_policy = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'organisations'
        ordering = ['name']
        indexes = [
            models.Index(fields=['status', 'is_active']),
        ]

    def __str__(self):
        return self.name

    @property
    def primary_color(self):
        return (self.feature_flags or {}).get('primary_color', '#1c78f5')