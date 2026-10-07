"""Settings package — routes to the right module based on DJANGO_ENV."""
import os

DJANGO_ENV = os.environ.get('DJANGO_ENV', 'development')

if DJANGO_ENV == 'production':
    from .production import *          # noqa
elif DJANGO_ENV == 'testing':
    from .testing import *             # noqa
else:
    from .development import *         # noqa