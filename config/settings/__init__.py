import os

if 'DJANGO_SETTINGS_MODULE' not in os.environ:
    DJANGO_ENV = os.environ.get('DJANGO_ENV', 'development')
    if DJANGO_ENV == 'production':
        from .production import *
    elif DJANGO_ENV == 'testing':
        from .testing import *
    else:
        from .development import *