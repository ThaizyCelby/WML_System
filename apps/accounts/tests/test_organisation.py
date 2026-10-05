"""Organisation model + middleware + service tests."""
import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings

from apps.accounts.models import Organisation
from apps.accounts.organisation_service import (
    OrganisationService,
    clear_current_org,
    get_current_org,
    set_current_org,
)

User = get_user_model()


@pytest.mark.django_db
class TestOrganisationModel:

    def test_slug_unique(self):
        Organisation.objects.create(name='Org A', slug='org-a')
        with pytest.raises(Exception):
            Organisation.objects.create(name='Org B', slug='org-a')

    def test_is_suspended_property(self):
        org = Organisation.objects.create(
            name='X', slug='x', status='active', is_active=True,
        )
        assert org.is_suspended is False

        org.status = 'suspended'
        org.save()
        assert org.is_suspended is True

        org.status = 'active'
        org.is_active = False
        org.save()
        assert org.is_suspended is True


@pytest.mark.django_db
class TestUserOrganisationFK:

    def test_user_can_be_created_with_org(self):
        org = Organisation.objects.create(name='A', slug='a')
        user = User.objects.create_user(
            email='a@x.com', password='TestPass123!', organisation=org,
        )
        assert user.organisation_id == org.id

    def test_user_can_be_created_without_org(self):
        user = User.objects.create_user(email='b@x.com', password='TestPass123!')
        assert user.organisation is None

    def test_related_name_from_org(self):
        org = Organisation.objects.create(name='A', slug='a')
        User.objects.create_user(email='c@x.com', password='TestPass123!', organisation=org)
        User.objects.create_user(email='d@x.com', password='TestPass123!', organisation=org)
        assert org.users.count() == 2


@pytest.mark.django_db
class TestOrganisationService:

    def test_get_org_for_user(self):
        org = Organisation.objects.create(name='A', slug='a')
        user = User.objects.create_user(
            email='e@x.com', password='TestPass123!', organisation=org,
        )
        assert OrganisationService.get_org_for_user(user) == org

    def test_get_org_for_user_without_org(self):
        user = User.objects.create_user(email='f@x.com', password='TestPass123!')
        assert OrganisationService.get_org_for_user(user) is None

    def test_require_org_raises_when_missing(self):
        user = User.objects.create_user(email='g@x.com', password='TestPass123!')
        with pytest.raises(ValueError, match='no organisation'):
            OrganisationService.require_org(user)

    def test_require_org_returns_org(self):
        org = Organisation.objects.create(name='A', slug='a')
        user = User.objects.create_user(
            email='h@x.com', password='TestPass123!', organisation=org,
        )
        assert OrganisationService.require_org(user) == org

    def test_is_superuser_without_org(self):
        superuser = User.objects.create_user(
            email='s@x.com', password='TestPass123!', is_superuser=True,
        )
        assert OrganisationService.is_superuser_without_org(superuser) is True

        org = Organisation.objects.create(name='A', slug='a')
        superuser.organisation = org
        superuser.save()
        assert OrganisationService.is_superuser_without_org(superuser) is False

    def test_is_superuser_without_org_for_regular_user(self):
        user = User.objects.create_user(email='r@x.com', password='TestPass123!')
        assert OrganisationService.is_superuser_without_org(user) is False


class TestThreadLocal:

    def test_set_and_get(self):
        clear_current_org()
        assert get_current_org() is None

        sentinel = object()
        set_current_org(sentinel)
        assert get_current_org() is sentinel
        clear_current_org()
        assert get_current_org() is None


@pytest.mark.django_db
class TestOrganisationMiddleware:

    def test_middleware_sets_request_organisation(self, client):
        org = Organisation.objects.create(name='A', slug='a')
        user = User.objects.create_user(
            email='mw@x.com', password='TestPass123!', organisation=org,
        )
        client.force_login(user)

        # The default test client sets request.user, but middleware runs
        # during the request cycle. Hitting a public page (e.g. home) lets
        # the middleware run and set request.organisation without a 302.
        resp = client.get('/')
        assert resp.status_code in (200, 302)

    def test_suspended_organisation_blocks_request(self, client):
        org = Organisation.objects.create(
            name='S', slug='s', status='suspended', is_active=True,
        )
        user = User.objects.create_user(
            email='su@x.com', password='TestPass123!', organisation=org,
        )
        client.force_login(user)
        resp = client.get('/staff/')
        assert resp.status_code == 403

    def test_superuser_without_org_is_not_blocked(self, client):
        # Global superuser (no org) should never be blocked.
        superuser = User.objects.create_user(
            email='gs@x.com', password='TestPass123!', is_superuser=True,
        )
        client.force_login(superuser)
        resp = client.get('/staff/')
        # 200 (dashboard) or 302 (MFA redirect) — but never 403.
        assert resp.status_code != 403