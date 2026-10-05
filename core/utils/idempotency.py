"""Idempotency utilities for payment and webhook processing."""
import hashlib
import hmac
import uuid
from typing import Optional

from django.core.cache import cache


def generate_idempotency_key(prefix: str = 'idem') -> str:
    """Generate a unique idempotency key."""
    return f"{prefix}_{uuid.uuid4().hex}"


def check_and_set_idempotency(key: str, ttl: int = 86400) -> bool:
    """Check if an idempotency key has been processed.

    Returns True if the key is new (not processed before),
    False if the key has already been seen.
    """
    cache_key = f"idempotency:{key}"
    # Use Redis SETNX
    return cache.add(cache_key, 'processed', timeout=ttl)


def compute_webhook_signature(secret: str, payload: bytes) -> str:
    """Compute HMAC-SHA256 signature for webhook verification."""
    return hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()


def verify_webhook_signature(
        secret: str,
        payload: bytes,
        provided_signature: str,
) -> bool:
    """Verify a webhook signature using constant-time comparison."""
    expected = compute_webhook_signature(secret, payload)
    return hmac.compare_digest(expected, provided_signature)
