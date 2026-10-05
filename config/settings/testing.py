from .base import *

DEBUG = False

# Use in-memory SQLite for fast tests
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Use local memory cache
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    },
    'rate_limit': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    },
    'sessions': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    },
}

# Speed up password hashing in tests
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# Disable throttling in tests
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {
    'anon': None,
    'user': None,
}

# Use console email backend
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# Disable celery eager
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Security relaxed for tests
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Disable throttling in tests (set to None so DRF allows all requests)
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {
    'anon': None,
    'user': None,
    'login': None,
    'registration': None,
    'password_reset': None,
    'file_upload': None,
    'loan_application': None,
    'chatbot': None,
    'admin': None,
    'security_sensitive': None,
}


# ─────────────────────────────────────────────────────────────────
# AI — disable real network calls in tests
#
# Tests must never hit Grok, GLM, Gemini, or OpenAI. All providers
# except mock are force-disabled regardless of what .env says. The
# provider-chain preference order is preserved (so the fallback-walk
# logic is still exercised), but only mock is ever available.
# ─────────────────────────────────────────────────────────────────
AI_PROVIDERS = {
    'grok':   {**AI_PROVIDERS.get('grok', {}),   'enabled': False, 'api_key': ''},
    'glm':    {**AI_PROVIDERS.get('glm', {}),    'enabled': False, 'api_key': ''},
    'gemini': {**AI_PROVIDERS.get('gemini', {}), 'enabled': False, 'api_key': ''},
    'openai': {**AI_PROVIDERS.get('openai', {}), 'enabled': False, 'api_key': ''},
}
AI_FALLBACK_TO_MOCK = True