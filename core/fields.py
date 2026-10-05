"""Custom Django model fields for encryption at rest."""
import json
import logging

from django.db import models

from .crypto import decrypt, encrypt, _is_ciphertext

logger = logging.getLogger('core.fields')


class EncryptedTextField(models.TextField):
    """
    TextField transparently encrypted with Fernet.

    Ciphertext is stored as base64 text. Reads decrypt automatically.
    Exact-value lookups on the ciphertext are not supported (Fernet is
    non-deterministic). Use a companion blind-index field for equality
    search.
    """

    description = 'Text field encrypted at rest (Fernet)'

    def from_db_value(self, value, expression, connection):
        if value is None or value == '':
            return value
        return decrypt(value)

    def to_python(self, value):
        if value is None or value == '':
            return value
        if _is_ciphertext(value):
            return decrypt(value)
        return value

    def get_prep_value(self, value):
        if value is None or value == '':
            return value
        return encrypt(value)


class EncryptedJSONField(models.TextField):
    """
    JSON-serialized value encrypted with Fernet.

    Reads return the original Python object (dict, list, etc.).
    """

    description = 'JSON field encrypted at rest (Fernet)'

    def from_db_value(self, value, expression, connection):
        if value is None or value == '':
            return None
        if not _is_ciphertext(value):
            # Pre-migration plaintext — decode and return the original object.
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return None
        try:
            return json.loads(decrypt(value))
        except Exception as e:
            logger.error('Failed to decrypt JSON field: %s', e)
            return None

    def to_python(self, value):
        if value is None or value == '':
            return None
        if isinstance(value, (dict, list)):
            return value
        if _is_ciphertext(value):
            try:
                return json.loads(decrypt(value))
            except Exception:
                return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None

    def get_prep_value(self, value):
        if value is None:
            return value
        if _is_ciphertext(value):
            return value
        if isinstance(value, str):
            # Some legacy paths store JSON as a string; treat as already-encoded.
            return encrypt(value)
        return encrypt(json.dumps(value, default=str))
