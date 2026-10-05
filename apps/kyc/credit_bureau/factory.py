"""Credit bureau factory."""
import logging

from django.conf import settings

from .base import CreditBureauProvider, CreditBureauError
from .mock import MockCreditBureauProvider
from .transunion import TransUnionProvider

logger = logging.getLogger('apps.kyc.credit_bureau')


def get_credit_bureau_provider(name: str = None) -> CreditBureauProvider:
    name = name or getattr(settings, 'CREDIT_BUREAU_PROVIDER', 'mock')

    if name == 'mock':
        return MockCreditBureauProvider()
    if name == 'transunion':
        return TransUnionProvider(getattr(settings, 'TRANSUNION_CONFIG', {}))
    raise CreditBureauError(f"Unknown credit bureau: {name}")