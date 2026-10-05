from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.payments'

    def ready(self):
        # Registers Django system checks (see apps/payments/checks.py).
        # Import is required so @register() decorators execute.
        from . import checks  # noqa: F401