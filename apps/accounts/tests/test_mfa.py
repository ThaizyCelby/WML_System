"""MFA / TOTP tests."""
import pyotp
import pytest
from django.contrib.auth import get_user_model

from apps.accounts.mfa_service import MFAService
from apps.accounts.models import MFARecoveryCode

User = get_user_model()


@pytest.mark.django_db
class TestMFAService:

    def _user(self):
        return User.objects.create_user(
            email='mfa@wethu.test', password='TestPass123!',
        )

    def test_generate_secret_is_base32(self):
        secret = MFAService.generate_secret()
        assert len(secret) >= 16
        pyotp.TOTP(secret)

    def test_verify_code_happy_path(self):
        secret = MFAService.generate_secret()
        code = pyotp.TOTP(secret).now()
        ok, counter = MFAService.verify_code(secret, code)
        assert ok is True
        assert counter > 0

    def test_verify_code_rejects_invalid(self):
        secret = MFAService.generate_secret()
        ok, _ = MFAService.verify_code(secret, '000000')
        assert ok is False

    def test_verify_code_rejects_replay(self):
        secret = MFAService.generate_secret()
        code = pyotp.TOTP(secret).now()
        ok, counter = MFAService.verify_code(secret, code)
        assert ok is True
        ok2, _ = MFAService.verify_code(secret, code, last_counter=counter)
        assert ok2 is False

    def test_recovery_codes_generate_and_verify(self):
        user = self._user()
        codes = MFAService.generate_recovery_codes(user, count=3)
        assert len(codes) == 3
        assert MFARecoveryCode.objects.filter(user=user).count() == 3
        assert MFAService.verify_recovery_code(user, codes[0]) is True
        assert MFAService.verify_recovery_code(user, codes[0]) is False
        assert MFAService.verify_recovery_code(user, codes[1]) is True

    def test_user_requires_mfa(self):
        user = self._user()
        assert MFAService.user_requires_mfa(user) is False
        user.mfa_enabled = True
        user.mfa_secret = MFAService.generate_secret()
        user.save()
        assert MFAService.user_requires_mfa(user) is True


@pytest.mark.django_db
class TestMFAViews:

    def _enrolled_user(self):
        user = User.objects.create_user(
            email='mfa-view@wethu.test', password='TestPass123!',
        )
        secret = MFAService.generate_secret()
        user.mfa_enabled = True
        user.mfa_secret = secret
        user.save()
        return user, secret

    def test_challenge_page_renders(self, client):
        user, _ = self._enrolled_user()
        client.force_login(user)
        resp = client.get('/mfa/challenge/')
        assert resp.status_code == 200

    def test_challenge_accepts_valid_totp(self, client):
        user, secret = self._enrolled_user()
        client.force_login(user)
        code = pyotp.TOTP(secret).now()
        resp = client.post('/mfa/challenge/', {'code': code})
        assert resp.status_code == 302
        assert client.session.get('mfa_verified') is True

    def test_challenge_rejects_invalid_totp(self, client):
        user, _ = self._enrolled_user()
        client.force_login(user)
        resp = client.post('/mfa/challenge/', {'code': '000000'})
        assert resp.status_code == 302
        assert not client.session.get('mfa_verified')

    def test_challenge_accepts_recovery_code(self, client):
        user, _ = self._enrolled_user()
        codes = MFAService.generate_recovery_codes(user, count=1)
        client.force_login(user)
        resp = client.post('/mfa/challenge/', {'code': codes[0]})
        assert client.session.get('mfa_verified') is True