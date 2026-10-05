"""Tenant resolution and enforcement helpers."""
from typing import Optional

from .models import Organisation


class OrganisationService:

    @staticmethod
    def get_default() -> Optional[Organisation]:
        return Organisation.objects.filter(is_active=True).order_by('created_at').first()

    @staticmethod
    def get_by_slug(slug: str) -> Optional[Organisation]:
        return Organisation.objects.filter(slug=slug, is_active=True).first()

    @staticmethod
    def resolve_for_request(request) -> Optional[Organisation]:
        """
        Resolve the organisation for a request.
        Order: authenticated user's org → URL param ?org= for superusers → None.
        """
        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            org = getattr(user, 'organisation', None)
            if org:
                return org
            # Superusers may pass ?org=<uuid>
            if user.is_superuser:
                org_id = request.GET.get('org') or request.POST.get('org')
                if org_id:
                    return Organisation.objects.filter(id=org_id).first()
        return None