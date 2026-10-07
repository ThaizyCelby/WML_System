"""
Django base settings for Wethu Micro Lenders.

All environment-specific settings are in development.py, production.py, or testing.py.
"""
import os
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from celery.schedules import crontab
import environ

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Environment variables
env = environ.Env(
    DEBUG=(bool, True),
    ALLOWED_HOSTS=(list, ['127.0.0.1:800']),
    CSRF_TRUSTED_ORIGINS=(list, []),
)

# Read .env file if it exists
environ.Env.read_env(BASE_DIR / '.env')

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env('DJANGO_SECRET_KEY', default='dev-only-secret-key-change-me')
FIELD_ENCRYPTION_KEY = env.str('FIELD_ENCRYPTION_KEY', default='')
DEBUG = env.bool('DJANGO_DEBUG', default=False)

ALLOWED_HOSTS = env.list('DJANGO_ALLOWED_HOSTS', default=['localhost', '127.0.0.1'])

# ----------------------------------------------------------------------
# APPLICATIONS
# ----------------------------------------------------------------------
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',
    'drf_spectacular',
    'django_redis',
    'storages',
    'mptt',
]

LOCAL_APPS = [
    'core',
    'apps.accounts',
    'apps.audit',
    'apps.security',
    'apps.kyc',
    'apps.documents',
    'apps.loans',
    'apps.repayments',
    'apps.payments',
    'apps.banking',
    'apps.affordability',
    'apps.ai',
    'apps.chat',
    'apps.notifications',
    'apps.reports',
    'apps.support',
    'apps.compliance',
    'apps.vendors',
    'apps.web',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'apps.accounts.middleware_org.OrganisationMiddleware',
    'apps.accounts.middleware_mfa.MFAEnforcementMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.audit.middleware.AuditLogMiddleware',
    'apps.security.middleware.SecurityEventMiddleware',
    'apps.security.middleware.RateLimitMiddleware',
    'apps.security.middleware.SecurityHeadersMiddleware',
]

# ── MFA CONFIGURATION ───────────────────────────────────────────
MFA_ISSUER = env.str('MFA_ISSUER', default='Wethu Micro Lenders')
MFA_RECOVERY_CODE_COUNT = env.int('MFA_RECOVERY_CODE_COUNT', default=10)
MFA_ENFORCE_FOR_STAFF = env.bool('MFA_ENFORCE_FOR_STAFF', default=False)

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.web.context_processors.branding',
                'apps.web.context_processors.notifications_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# ----------------------------------------------------------------------
# DATABASE
# ----------------------------------------------------------------------
DATABASES = {
    'default': {
        'ENGINE': env.str('DB_ENGINE', default='django.db.backends.postgresql'),
        'NAME': env.str('DB_NAME', default='wethu_micro_lenders'),
        'USER': env.str('DB_USER', default='wethu_micro_lenders'),
        'PASSWORD': env.str('DB_PASSWORD', default='wethu_micro_lenders'),
        'HOST': env.str('DB_HOST', default='localhost'),
        'PORT': env.str('DB_PORT', default='5432'),
        'CONN_MAX_AGE': env.int('DB_CONN_MAX_AGE', default=60),
        'OPTIONS': {
            'connect_timeout': 10,
            'sslmode': 'prefer',
        },
        'ATOMIC_REQUESTS': True,
    }
}

# ----------------------------------------------------------------------
# REDIS / CACHE
# ----------------------------------------------------------------------
REDIS_URL = env.str('REDIS_URL', default='redis://localhost:6379/0')

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'SOCKET_CONNECT_TIMEOUT': 5,
            'SOCKET_TIMEOUT': 5,
            'RETRY_ON_TIMEOUT': True,
            'MAX_CONNECTIONS': 50,
            'COMPRESSOR': 'django_redis.compressors.zlib.ZlibCompressor',
            'IGNORE_EXCEPTIONS': False,
            'KEY_PREFIX': 'wethu',
        },
        'KEY_PREFIX': 'wethu',
        'TIMEOUT': 300,
    },
    'rate_limit': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': env.str('RATE_LIMIT_REDIS_URL', default='redis://localhost:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'MAX_CONNECTIONS': 20,
            'KEY_PREFIX': 'wethu_rl',
        },
    },
    'sessions': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': env.str('SESSION_REDIS_URL', default='redis://localhost:6379/2'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'MAX_CONNECTIONS': 30,
            'KEY_PREFIX': 'wethu_sess',
        },
    },
}

SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'sessions'

# ----------------------------------------------------------------------
# AUTHENTICATION
# ----------------------------------------------------------------------
AUTH_USER_MODEL = 'accounts.User'

AUTHENTICATION_BACKENDS = [
    'apps.accounts.auth.EmailBackend',
    'django.contrib.auth.backends.ModelBackend',
]

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 12},
    },
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
    {'NAME': 'apps.accounts.validators.PasswordStrengthValidator'},
]

LOGIN_RATE_LIMIT = {
    'max_attempts': 3,
    'lockout_duration': 1200,
    'window_seconds': 900,
    'progressive_throttle': True,
    'initial_delay': 1,
    'max_delay': 60,
    'backoff_factor': 2,
}

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/portal/'
LOGOUT_REDIRECT_URL = '/'

# ----------------------------------------------------------------------
# SESSION & COOKIE SECURITY
# ----------------------------------------------------------------------
SESSION_COOKIE_AGE = 1800
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_NAME = '__Secure-sessionid' if not DEBUG else 'sessionid'
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_NAME = '__Secure-csrftoken' if not DEBUG else 'csrftoken'
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'https://localhost:443',
])

# ----------------------------------------------------------------------
# CORS
# ----------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[
    'http://localhost:3000',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
])
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']
CORS_ALLOW_HEADERS = [
    'accept', 'accept-encoding', 'authorization', 'content-type', 'dnt',
    'origin', 'user-agent', 'x-csrftoken', 'x-requested-with', 'x-idempotency-key',
]

# ----------------------------------------------------------------------
# SECURITY HEADERS
# ----------------------------------------------------------------------
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC = ("'self'", 'https://cdn.jsdelivr.net')
CSP_STYLE_SRC = ("'self'", 'https://cdn.jsdelivr.net', "'unsafe-inline'")
CSP_IMG_SRC = ("'self'", 'data:', 'https:')
CSP_FONT_SRC = ("'self'", 'https://cdn.jsdelivr.net')
CSP_CONNECT_SRC = ("'self'", 'wss:', 'https:')
CSP_FRAME_SRC = ("'none'",)
CSP_FRAME_ANCESTORS = ("'none'",)

# ----------------------------------------------------------------------
# REST FRAMEWORK
# ----------------------------------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
        'apps.security.throttling.ScopedRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/min',
        'user': '120/min',
        'login': '3/h',
        'registration': '5/hour',
        'password_reset': '3/hour',
        'file_upload': '10/min',
        'loan_application': '5/hour',
        'chatbot': '30/min',
        'admin': '300/min',
        'security_sensitive': '10/min',
    },
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'core.pagination.StandardResultsSetPagination',
    'PAGE_SIZE': 25,
    'MAX_PAGE_SIZE': 100,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'EXCEPTION_HANDLER': 'core.exceptions.custom_exception_handler',
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.MultiPartParser',
        'rest_framework.parsers.FormParser',
    ],
    'DATETIME_FORMAT': '%Y-%m-%dT%H:%M:%S%z',
    'COERCE_DECIMAL_TO_STRING': True,
    'TEST_REQUEST_DEFAULT_FORMAT': 'json',
}

# ----------------------------------------------------------------------
# SIMPLE JWT
# ----------------------------------------------------------------------
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': 'wethu_micro_lenders',
    'JWK_URL': None,
    'LEEWAY': 0,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'USER_AUTHENTICATION_RULE':
        'rest_framework_simplejwt.authentication.default_user_authentication_rule',
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'TOKEN_USER_CLASS': 'rest_framework_simplejwt.models.TokenUser',
    'JTI_CLAIM': 'jti',
    'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
    'SLIDING_TOKEN_LIFETIME': timedelta(minutes=15),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=7),
}

# ----------------------------------------------------------------------
# CELERY
# ----------------------------------------------------------------------
CELERY_BROKER_URL = env.str('CELERY_BROKER_URL', default='redis://localhost:6379/3')
CELERY_RESULT_BACKEND = env.str('CELERY_RESULT_BACKEND', default='redis://localhost:6379/4')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Africa/Johannesburg'
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60
CELERY_WORKER_MAX_TASKS_PER_CHILD = 100
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

CELERY_BEAT_SCHEDULE = {
    'submit-due-debits': {
        'task': 'apps.payments.tasks.submit_due_debits',
        'schedule': crontab(hour=2, minute=0),
    },
    'retry-failed-debits': {
        'task': 'apps.payments.tasks.retry_failed_debits',
        'schedule': crontab(hour=2, minute=30),
    },
    'poll-pending-transactions': {
        'task': 'apps.payments.tasks.poll_pending_transactions',
        'schedule': crontab(minute='*/15'),
    },
    'run-reconciliation': {
        'task': 'apps.payments.tasks.run_reconciliation',
        'schedule': crontab(hour=3, minute=0),
    },
    'security-sweep': {
        'task': 'apps.security.tasks.run_security_sweep',
        'schedule': crontab(minute='*/30'),
    },
    'send-payment-reminders': {
        'task': 'apps.notifications.tasks.send_payment_reminders',
        'schedule': crontab(hour=7, minute=0),
    },
    'send-overdue-notifications': {
        'task': 'apps.notifications.tasks.send_overdue_notifications',
        'schedule': crontab(hour=8, minute=0),
    },
    'recompute-default-risk': {
        'task': 'apps.loans.tasks.recompute_default_risk',
        'schedule': crontab(hour=2, minute=30),
    },
    'weekly-portfolio-summary': {
        'task': 'apps.reports.tasks.weekly_portfolio_summary',
        'schedule': crontab(day_of_week=1, hour=6, minute=0),
    },
}

# ----------------------------------------------------------------------
# SPECTACULAR (OpenAPI)
# ----------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    'TITLE': 'Wethu Micro Lenders API',
    'DESCRIPTION': (
        'Financial Management and Digital Lending Platform - '
        'Wethu Micro Lenders. Responsible micro-lending, '
        'powered by financial intelligence.'
    ),
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'CONTACT': {
        'name': 'Wethu Micro Lenders Support',
        'email': env.str('SITE_SUPPORT_EMAIL', default='support@wethumicrolenders.co.za'),
    },
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'persistAuthorization': True,
        'displayOperationId': True,
    },
    'SECURITY': [{'bearerAuth': []}],
    'COMPONENT_SPLIT_REQUEST': True,
}

# ----------------------------------------------------------------------
# SITE / BRANDING
# ----------------------------------------------------------------------
SITE_NAME = env.str('SITE_NAME', default='Wethu Micro Lenders')
SITE_SHORT_NAME = env.str('SITE_SHORT_NAME', default='Wethu')
SITE_DESCRIPTION = env.str(
    'SITE_DESCRIPTION',
    default='Responsible micro-lending, powered by financial intelligence.',
)
SITE_SUPPORT_EMAIL = env.str('SITE_SUPPORT_EMAIL', default='support@wethumicrolenders.co.za')
SITE_SUPPORT_PHONE = env.str('SITE_SUPPORT_PHONE', default='+27 10 000 0000')
SITE_COMPANY_REG = env.str('SITE_COMPANY_REG', default='NCRCP-XXXXX')

# ----------------------------------------------------------------------
# FINANCIAL CONFIGURATION
# ----------------------------------------------------------------------
FINANCIAL_CONFIG = {
    'DEFAULT_INTEREST_RATE': Decimal(env.str('DEFAULT_INTEREST_RATE', default='30.00')),
    'INTEREST_RATE_MIN': Decimal(env.str('INTEREST_RATE_MIN', default='0.00')),
    'INTEREST_RATE_MAX': Decimal(env.str('INTEREST_RATE_MAX', default='36.00')),
    'CURRENCY': 'ZAR',
    'ROUNDING': 'ROUND_HALF_UP',
    'DECIMAL_PLACES': 2,
    'DEFAULT_REPAYMENT_FREQUENCY': 'monthly',
    'LATE_PAYMENT_FEE': Decimal(env.str('LATE_PAYMENT_FEE', default='50.00')),
    'ORIGINATION_FEE_PERCENT': Decimal(env.str('ORIGINATION_FEE_PERCENT', default='2.50')),
}

# ----------------------------------------------------------------------
# AI PROVIDER CONFIGURATION
# ----------------------------------------------------------------------
AI_PROVIDERS = {
    'grok': {
        'enabled': env.bool('GROK_ENABLED', default=True),
        'api_key': env.str('GROK_API_KEY', default=''),
        'model': env.str('GROK_MODEL', default='grok-3-mini'),
        'base_url': env.str('GROK_BASE_URL', default='https://api.x.ai/v1'),
        'max_tokens': env.int('GROK_MAX_TOKENS', default=800),
        'temperature': env.float('GROK_TEMPERATURE', default=0.05),
        'timeout_seconds': env.int('GROK_TIMEOUT_SECONDS', default=30),
        'retry_count': env.int('GROK_RETRY_COUNT', default=2),
        'circuit_breaker_threshold': env.int('GROK_CIRCUIT_BREAKER_THRESHOLD', default=3),
    },
    'glm': {
        'enabled': env.bool('GLM_ENABLED', default=True),
        'api_key': env.str('GLM_API_KEY', default=''),
        'model': env.str('GLM_MODEL', default='glm-4.6'),
        'base_url': env.str('GLM_BASE_URL', default='https://api.z.ai/api/paas/v4'),
        'max_tokens': env.int('GLM_MAX_TOKENS', default=2000),
        'max_input_chars': env.int('GLM_MAX_INPUT_CHARS', default=50000),
        'temperature': env.float('GLM_TEMPERATURE', default=0.05),
        'top_p': env.float('GLM_TOP_P', default=0.8),
        'timeout_seconds': env.int('GLM_TIMEOUT_SECONDS', default=30),
        'retry_count': env.int('GLM_RETRY_COUNT', default=4),
        'circuit_breaker_threshold': env.int('GLM_CIRCUIT_BREAKER_THRESHOLD', default=3),
    },
    'gemini': {
        'enabled': env.bool('GEMINI_ENABLED', default=False),
        'api_key': env.str('GEMINI_API_KEY', default=''),
        'model': env.str('GEMINI_MODEL', default='gemini-3.8-flash'),
        'max_tokens': 4000,
        'temperature': 0.05,
        'timeout_seconds': 45,
        'retry_count': 3,
        'circuit_breaker_threshold': 5,
    },
    'openai': {
        'enabled': env.bool('OPENAI_ENABLED', default=False),
        'api_key': env.str('OPENAI_API_KEY', default=''),
        'model': env.str('OPENAI_MODEL', default='gpt-4o-mini'),
        'max_tokens': 2000,
        'temperature': 0.1,
        'timeout_seconds': 30,
        'retry_count': 3,
        'circuit_breaker_threshold': 5,
    },
}

AI_FALLBACK_TO_MOCK = env.bool('AI_FALLBACK_TO_MOCK', default=True)
AI_DEFAULT_PROVIDER = env.str('AI_DEFAULT_PROVIDER', default='grok')
AI_FALLBACK_PROVIDER = env.str('AI_FALLBACK_PROVIDER', default='glm')

# ----------------------------------------------------------------------
# PAYMENT PROVIDER CONFIGURATION
# ----------------------------------------------------------------------
PAYMENT_PROVIDER = env.str('PAYMENT_PROVIDER', default='mock')

NUPAY_CONFIG = {
    'endpoint': env.str('NUPAY_ENDPOINT', default=''),
    'api_key': env.str('NUPAY_API_KEY', default=''),
    'api_secret': env.str('NUPAY_API_SECRET', default=''),
    'merchant_id': env.str('NUPAY_MERCHANT_ID', default=''),
    'webhook_secret': env.str('NUPAY_WEBHOOK_SECRET', default=''),
    'timeout_seconds': env.int('NUPAY_TIMEOUT', default=30),
    'retry_count': env.int('NUPAY_RETRIES', default=3),
}

# ----------------------------------------------------------------------
# CREDIT BUREAU CONFIGURATION
# ----------------------------------------------------------------------
CREDIT_BUREAU_PROVIDER = env.str('CREDIT_BUREAU_PROVIDER', default='mock')

TRANSUNION_CONFIG = {
    'base_url': env.str('TRANSUNION_BASE_URL', default=''),
    'api_key': env.str('TRANSUNION_API_KEY', default=''),
    'api_secret': env.str('TRANSUNION_API_SECRET', default=''),
    'member_code': env.str('TRANSUNION_MEMBER_CODE', default=''),
    'product_code': env.str('TRANSUNION_PRODUCT_CODE', default=''),
    'timeout_seconds': env.int('TRANSUNION_TIMEOUT', default=30),
}

CREDIT_REPORT_VALIDITY_DAYS = env.int('CREDIT_REPORT_VALIDITY_DAYS', default=30)

# ----------------------------------------------------------------------
# SECURITY CONFIGURATION
# ----------------------------------------------------------------------
SECURITY_CONFIG = {
    'RISK_SCORE_THRESHOLDS': {
        'low': 0,
        'medium': 30,
        'high': 60,
        'critical': 80,
    },
    'AUTO_RESPONSES': {
        'low': 'log_only',
        'medium': 'increase_monitoring',
        'high': 'require_additional_auth',
        'critical': 'temporary_block',
    },
    'IP_BLOCK_DURATION': 3600,
    'ACCOUNT_SUSPENSION_DURATION': 86400,
    'MAX_FILE_UPLOAD_SIZE': 10 * 1024 * 1024,
    'ALLOWED_FILE_TYPES': [
        'application/pdf',
        'image/jpeg',
        'image/png',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    ],
}

SECURITY_ALERT_RECIPIENTS = env.list('SECURITY_ALERT_RECIPIENTS', default=[])
DEVELOPER_EMAIL = env.str('DEVELOPER_EMAIL', default='')

# ----------------------------------------------------------------------
# INTERNATIONALIZATION
# ----------------------------------------------------------------------
LANGUAGE_CODE = 'en-za'
TIME_ZONE = 'Africa/Johannesburg'
USE_I18N = True
USE_TZ = True

# ----------------------------------------------------------------------
# STATIC & MEDIA FILES
# ----------------------------------------------------------------------
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ----------------------------------------------------------------------
# STORAGE
# ----------------------------------------------------------------------
STORAGES = {
    'default': {
        'BACKEND': env.str(
            'DEFAULT_FILE_STORAGE',
            default='django.core.files.storage.FileSystemStorage',
        ),
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}

AWS_ACCESS_KEY_ID = env.str('AWS_ACCESS_KEY_ID', default='')
AWS_SECRET_ACCESS_KEY = env.str('AWS_SECRET_ACCESS_KEY', default='')
AWS_STORAGE_BUCKET_NAME = env.str('AWS_STORAGE_BUCKET_NAME', default='')
AWS_S3_REGION_NAME = env.str('AWS_S3_REGION_NAME', default='af-south-1')
AWS_S3_ENDPOINT_URL = env.str('AWS_S3_ENDPOINT_URL', default='')
AWS_DEFAULT_ACL = 'private'
AWS_S3_OBJECT_PARAMETERS = {'ServerSideEncryption': 'AES256'}
AWS_S3_SIGNATURE_VERSION = 's3v4'
AWS_QUERYSTRING_EXPIRE = 3600

# ----------------------------------------------------------------------
# LOGGING
# ----------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.db.backends": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.utils.autoreload": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# ----------------------------------------------------------------------
# DEFAULTS
# ----------------------------------------------------------------------
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Ensure logs directory exists
os.makedirs(BASE_DIR / 'logs', exist_ok=True)