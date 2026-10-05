"""Tests for MFARecoveryCode model."""
from django.utils import timezone
import pytest

from apps.accounts.models import MFARecoveryCode, User


@pytest.fixture
def mfa_user(db):
    return User.objects.create_user(
        email='mfa@wethu.test',
        password='TestPass123!',
    )


@pytest.mark.django_db
class TestMFARecoveryCode:

    def test_create_code(self, mfa_user):
        code = MFARecoveryCode.objects.create(
            user=mfa_user,
            code_hash='sha256hexvalue',
        )
        assert code.used_at is None
        assert 'active' in str(code)

    def test_mark_used(self, mfa_user):
        code = MFARecoveryCode.objects.create(
            user=mfa_user, code_hash='abc',
        )
        code.used_at = timezone.now()
        code.save()
        assert 'used' in str(code)

    def test_user_can_have_multiple_codes(self, mfa_user):
        for i in range(5):
            MFARecoveryCode.objects.create(user=mfa_user, code_hash=f'hash-{i}')
        assert mfa_user.mfa_recovery_codes.count() == 5