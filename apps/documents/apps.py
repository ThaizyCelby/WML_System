from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.documents'
    verbose_name = 'Documents'

    def ready(self):
        # Import signals AFTER the app registry is ready.
        from . import signals  # noqa: F401