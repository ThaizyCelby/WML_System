"""
Django system checks for the payments app.

These run automatically at startup (any management command, gunicorn boot,
`manage.py check`, etc.) and refuse to let the process start if the payments
configuration is unsafe for the current environment.
"""
from django.conf import settings
from django.core.checks import Error, register


@register()
def nupay_production_config_check(app_configs, **kwargs):
    """
    Fail startup if NuPay is the active provider in production but the
    webhook secret is not configured.

    Silent acceptance of unsigned webhooks is not a deployable state —
    anyone who can reach /api/v1/payments/webhook/ would be able to forge
    payment events.
    """
    errors = []

    if getattr(settings, 'DEBUG', True):
        return errors  # dev / test — nothing to enforce here

    payment_provider = getattr(settings, 'PAYMENT_PROVIDER', 'mock')
    if payment_provider != 'nupay':
        return errors  # not using NuPay — no constraint

    webhook_secret = getattr(settings, 'NUPAY_WEBHOOK_SECRET', '') or ''
    if not webhook_secret:
        errors.append(
            Error(
                'NUPAY_WEBHOOK_SECRET must be set when PAYMENT_PROVIDER=nupay '
                'and DEBUG=False.',
                hint=(
                    'Add NUPAY_WEBHOOK_SECRET to your production .env. '
                    'Unsigned webhooks cannot be accepted in production.'
                ),
                id='payments.E001',
            )
        )

    return errors