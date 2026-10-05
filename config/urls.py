"""Wethu Micro Lenders URL configuration."""
from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

from .views import home_redirect
from apps.accounts.health_check import health_check, readiness_check, liveness_check

urlpatterns = [
    path('mfa/', include('apps.accounts.urls_mfa')),
    # Root redirect
    path('', include('apps.web.urls')),
    path('', home_redirect, name='home'),

    # Health endpoints
    path('health/', health_check, name='health-check'),
    path('readiness/', readiness_check, name='readiness-check'),
    path('liveness/', liveness_check, name='liveness-check'),

    # Django admin
    path('django-admin/', admin.site.urls),

    # API documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # API v1
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    path('api/v1/accounts/', include('apps.accounts.urls')),
    path('api/v1/audit/', include('apps.audit.urls')),
    path('api/v1/security/', include('apps.security.urls')),
    path('api/v1/kyc/', include('apps.kyc.urls')),
    path('api/v1/documents/', include('apps.documents.urls')),
    path('api/v1/loans/', include('apps.loans.urls')),
    path('api/v1/repayments/', include('apps.repayments.urls')),
    path('api/v1/payments/', include('apps.payments.urls')),
    path('api/v1/banking/', include('apps.banking.urls')),
    path('api/v1/affordability/', include('apps.affordability.urls')),
    path('api/v1/ai/', include('apps.ai.urls')),

    path('api/v1/chat/', include('apps.chat.urls')),
    path('api/v1/notifications/', include('apps.notifications.urls')),
    path('api/v1/reports/', include('apps.reports.urls')),
    path('api/v1/support/', include('apps.support.urls')),
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Not yet implemented (uncomment as each phase is built)
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # path('api/v1/vendors/', include('apps.vendors.urls')),
    # path('api/v1/fraud/', include('apps.fraud.urls')),
    # path('api/v1/notifications/', include('apps.notifications.urls')),
    # path('api/v1/chat/', include('apps.chat.urls')),
    # path('api/v1/reports/', include('apps.reports.urls')),
    # path('api/v1/compliance/', include('apps.compliance.urls')),
    # path('api/v1/support/', include('apps.support.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

    # Django debug toolbar
    import debug_toolbar
    urlpatterns.insert(0, path('__debug__/', include(debug_toolbar.urls)))
