"""Settings package — routes to the right module based on DJANGO_ENV."""
import os

# If Django already told us which settings module to load
# (e.g. DJANGO_SETTINGS_MODULE=config.settings.pythonanywhere),
# do not dispatch to development/production/testing here. That would
# drag in side effects like debug_toolbar onto every settings module.
if 'DJANGO_SETTINGS_MODULE' not in os.environ:
    DJANGO_ENV = os.environ.get('DJANGO_ENV', 'development')
    if DJANGO_ENV == 'production':
        from .production import *          # noqa
    elif DJANGO_ENV == 'testing':
        from .testing import *             # noqa
    else:
        from .development import *         # noqa