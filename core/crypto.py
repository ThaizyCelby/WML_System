"""
Application-level field encryption.

Uses Fernet (AES-128-CBC + HMAC-SHA256) for confidentiality and a keyed
HMAC-SHA256 blind index for searchable equality lookups on encrypted fields.

Key sourcing:
  FIELD_ENCRYPTION_KEY — base64-encoded 32-byte Fernet key.
                         Required in production.
                         In DEBUG, if unset, derives a key from SECRET_KEY
                         so local development works without extra config.

Backward compatibility:
  decrypt() detects plaintext (anything not starting with 'gAAAAA') and
  returns it unchanged. This lets us migrate existing plaintext rows in
  place without breaking reads mid-migration.
"""
import base64
import hashlib
import hmac
import logging

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger('core.crypto')

_fernet_cache = None


def _derive_dev_key() -> bytes:
    """Derive a Fernet key from SECRET_KEY when FIELD_ENCRYPTION_KEY is unset."""
    digest = hashlib.sha256(settings.SECRET_KEY.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Fernet:
    global _fernet_cache
    if _fernet_cache is not None:
        return _fernet_cache

    raw = getattr(settings, 'FIELD_ENCRYPTION_KEY', '') or ''
    if raw:
        try:
            key = raw.encode('utf-8') if isinstance(raw, str) else raw
            Fernet(key)  # validate
            _fernet_cache = Fernet(key)
            return _fernet_cache
        except Exception as e:
            raise ImproperlyConfigured(
                f'FIELD_ENCRYPTION_KEY is invalid: {e}'
            ) from e

    if getattr(settings, 'DEBUG', False):
        logger.warning(
            'FIELD_ENCRYPTION_KEY not set; deriving dev key from SECRET_KEY. '
            'Do NOT run production like this.'
        )
        _fernet_cache = Fernet(_derive_dev_key())
        return _fernet_cache

    raise ImproperlyConfigured(
        'FIELD_ENCRYPTION_KEY must be set in production.'
    )


def _is_ciphertext(value) -> bool:
    """Fernet tokens are URL-safe base64 and always start with 'gAAAAA'."""
    return isinstance(value, str) and value.startswith('gAAAAA')


def encrypt(plaintext) -> str:
    if plaintext is None or plaintext == '':
        return ''
    if _is_ciphertext(plaintext):
        return plaintext  # idempotent
    token = _get_fernet().encrypt(str(plaintext).encode('utf-8'))
    return token.decode('ascii')


def decrypt(ciphertext) -> str:
    if ciphertext is None or ciphertext == '':
        return ''
    # Pre-migration plaintext — pass through unchanged.
    if not _is_ciphertext(ciphertext):
        return ciphertext
    try:
        return _get_fernet().decrypt(ciphertext.encode('ascii')).decode('utf-8')
    except InvalidToken:
        logger.error('Failed to decrypt field value; returning empty string.')
        return ''


def _get_index_key() -> bytes:
    """
    Derive a separate HMAC key for the blind index so it is independent
    from the encryption key. Rotating FIELD_ENCRYPTION_KEY does not
    invalidate the index.
    """
    return hashlib.sha256(
        f'blind-index:{settings.SECRET_KEY}'.encode('utf-8')
    ).digest()


def blind_index(value) -> str:
    """Deterministic HMAC-SHA256 hex digest for equality lookups."""
    if value is None or value == '':
        return ''
    return hmac.new(
        _get_index_key(),
        str(value).strip().lower().encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()


def generate_key() -> str:
    """Return a fresh base64-encoded Fernet key. For ops tooling."""
    return Fernet.generate_key().decode('ascii')