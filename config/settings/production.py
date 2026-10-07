from .base import *
import os

DEBUG = False


SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Production email backend
EMAIL_BACKEND = env.str('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = env.str('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
EMAIL_HOST_USER = env.str('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env.str('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = env.str('DEFAULT_FROM_EMAIL', default='noreply@Wethu Micro Lenders.example')
SERVER_EMAIL = env.str('SERVER_EMAIL', default='server@Wethu Micro Lenders.example')

# Sentry
if env.bool('SENTRY_ENABLED', default=False):
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=env.str('SENTRY_DSN'),
        integrations=[DjangoIntegration()],
        traces_sample_rate=env.float('SENTRY_TRACES_SAMPLE_RATE', default=0.1),
        send_default_pii=False,
        environment='production',
    )

# S3 storage
STORAGES['default']['BACKEND'] = 'storages.backends.s3boto3.S3Boto3Storage'
STORAGES['staticfiles']['BACKEND'] = 'storages.backends.s3boto3.S3Boto3Storage'

# Production database pooling
DATABASES['default']['CONN_MAX_AGE'] = 300
DATABASES['default']['OPTIONS']['sslmode'] = 'require'

# Rate limiting (stricter in production)
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['anon'] = '30/min'
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['user'] = '60/min'

# Audit logging to file
LOGGING['handlers']['file']['level'] = 'INFO'
