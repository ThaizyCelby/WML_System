from .base import *

# ---- No Redis on free tier ----
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'wethu-default',
    },
    'rate_limit': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'wethu-ratelimit',
    },
    'sessions': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'wethu-sessions',
    },
}

# Sessions in DB (survives web worker restarts)
SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# Celery: don't try to connect to a broker
CELERY_TASK_ALWAYS_EAGER = True
CELERY_BROKER_URL = 'memory://'
CELERY_RESULT_BACKEND = 'cache+memory://'

# Local filesystem storage (no S3)
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}

# Explicitly off
DEBUG = False

# Required for PythonAnywhere
ALLOWED_HOSTS = ['GivenPrince.pythonanywhere.com']
CSRF_TRUSTED_ORIGINS = ['https://GivenPrince.pythonanywhere.com']

# Disable MFA enforcement (its middleware needs Redis)
MFA_ENFORCE_FOR_STAFF = False

# HSTS on a free subdomain can cause lockout if anything breaks — disable until stable
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_PRELOAD = False
SECURE_HSTS_INCLUDE_SUBDOMAINS = False

# ---- SQLite for free tier ----
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': '/home/GivenPrince/WML_System/db.sqlite3',
        'ATOMIC_REQUESTS': True,
    }
}

# ---- CSP for the CDNs our templates use ----
# The SecurityHeadersMiddleware only reads CSP_DEFAULT_SRC and sends it as
# "default-src ...", so everything the page needs must live here.
CSP_DEFAULT_SRC = (
    "'self'",
    "'unsafe-inline'",                     # inline <script> blocks (tailwind.config)
    "'unsafe-eval'",                       # tailwind CDN uses new Function() at runtime
    'https://cdn.tailwindcss.com',         # Tailwind CDN
    'https://cdn.jsdelivr.net',            # Alpine, Chart.js
    'https://unpkg.com',                   # HTMX
    'https://fonts.googleapis.com',        # Google Fonts CSS
    'https://fonts.gstatic.com',           # Google Fonts font files
    'data:',                               # data: URIs (favicon, some svg)
    'blob:',                               # blob: URIs (Chart.js occasionally)
)