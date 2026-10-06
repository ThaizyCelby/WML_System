import os

# Only auto-pick a settings module if Django hasn't already been told which one to use.
# When Django imports e.g. config.settings.pythonanywhere, DJANGO_SETTINGS_MODULE
# is already set, so we skip this dispatch entirely and avoid side effects.
if 'DJANGO_SETTINGS_MODULE' not in os.environ:
    DJANGO_ENV = os.environ.get('DJANGO_ENV', 'development')
    if DJANGO_ENV == 'production':
        from .production import *
    elif DJANGO_ENV == 'testing':
        from .testing import *
    else:
        from .development import *