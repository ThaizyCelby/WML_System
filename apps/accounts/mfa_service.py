"""TOTP multi-factor authentication service."""
import hashlib
import logging
import secrets

import pyotp
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger('apps.accounts')


class MFAService:
    """TOTP generation, verification, and recovery codes."""

    ISSUER = getattr(settings, 'MFA_ISSUER', 'Wethu Micro Lenders')
    RECOVERY_CODE_COUNT = getattr(settings, 'MFA_RECOVERY_CODE_COUNT', 10)

    # ── Secret + enrollment ────────────────────────────────────────
    @staticmethod
    def generate_secret() -> str:
        return pyotp.random_base32()

    @staticmethod
    def provisioning_uri(user, secret: str) -> str:
        return pyotp.TOTP(secret).provisioning_uri(
            name=user.email,
            issuer_name=MFAService.ISSUER,
        )

    # ── Verification ───────────────────────────────────────────────
    @staticmethod
    def verify_code(secret: str, code: str, last_counter=None):
        """
        Verify a TOTP code with 1-step skew (30s before/after).
        Returns (is_valid, counter). Rejects replay if counter <= last_counter.
        """
        code = (code or '').strip().replace(' ', '')
        if not code.isdigit() or len(code) != 6:
            return False, 0
        if not secret:
            return False, 0

        totp = pyotp.TOTP(secret)
        base_counter = int(timezone.now().timestamp() // 30)
        for offset in (-1, 0, 1):
            counter = base_counter + offset
            expected = totp.at(counter * 30)
            if secrets.compare_digest(expected, code):
                if last_counter is not None and counter <= last_counter:
                    logger.warning('TOTP replay attempt rejected')
                    return False, counter
                return True, counter
        return False, 0

    # ── Recovery codes ─────────────────────────────────────────────
    @staticmethod
    def generate_recovery_codes(user, count=None):
        """Generate N single-use recovery codes. Returns plaintext list (shown once)."""
        from .models import MFARecoveryCode
        count = count or MFAService.RECOVERY_CODE_COUNT
        MFARecoveryCode.objects.filter(user=user, used_at__isnull=True).delete()
        plaintext = []
        for _ in range(count):
            raw = (
                f"{secrets.token_hex(2)}-"
                f"{secrets.token_hex(2)}-"
                f"{secrets.token_hex(2)}"
            )
            plaintext.append(raw)
            MFARecoveryCode.objects.create(
                user=user,
                code_hash=MFAService._hash_recovery(raw),
            )
        return plaintext

    @staticmethod
    def verify_recovery_code(user, code) -> bool:
        from .models import MFARecoveryCode
        code = (code or '').strip().lower()
        if not code:
            return False
        digest = MFAService._hash_recovery(code)
        entry = MFARecoveryCode.objects.filter(
            user=user, code_hash=digest, used_at__isnull=True,
        ).first()
        if not entry:
            return False
        entry.used_at = timezone.now()
        entry.save(update_fields=['used_at'])
        return True

    @staticmethod
    def _hash_recovery(code: str) -> str:
        salt = getattr(settings, 'SECRET_KEY', '')[:32]
        return hashlib.sha256(f"{salt}:{code}".encode()).hexdigest()

    # ── Policy ─────────────────────────────────────────────────────
    @staticmethod
    def user_requires_mfa(user) -> bool:
        """Return True if this user must pass MFA to use the app."""
        if not user or not user.is_authenticated:
            return False
        if not getattr(user, 'mfa_enabled', False):
            return False
        return bool(getattr(user, 'mfa_secret', ''))

    @staticmethod
    def user_must_enroll(user) -> bool:
        """Return True if org policy requires this user to enroll MFA."""
        if not getattr(settings, 'MFA_ENFORCE_FOR_STAFF', False):
            return False
        if not user or not user.is_authenticated:
            return False
        if getattr(user, 'mfa_enabled', False):
            return False
        return user.is_staff or user.is_superuser