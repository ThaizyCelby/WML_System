"""Provider factory: returns an instance based on config."""
import logging
from django.conf import settings

from .base import PaymentProvider, PaymentProviderError
from .mock import MockPaymentProvider
from .nupay import NuPayProvider

logger = logging.getLogger('apps.payments')


def get_payment_provider(name: str = None) -> PaymentProvider:
    name = name or getattr(settings, 'PAYMENT_PROVIDER', 'mock')

    if name == 'mock':
        return MockPaymentProvider(config={})

    if name == 'nupay':
        cfg = getattr(settings, 'NUPAY_CONFIG', {}) or {}
        return NuPayProvider(cfg)

    raise PaymentProviderError(f"Unknown payment provider: {name}")
