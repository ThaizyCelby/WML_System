"""URL configuration for security app."""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    SecurityEventViewSet,
    BlockedIPViewSet,
    FraudAlertViewSet,
    UserDeviceViewSet,
    LoginAttemptViewSet,
)

router = DefaultRouter()
router.register(r'events', SecurityEventViewSet, basename='security-event')
router.register(r'blocked-ips', BlockedIPViewSet, basename='blocked-ip')
router.register(r'fraud-alerts', FraudAlertViewSet, basename='fraud-alert')
router.register(r'devices', UserDeviceViewSet, basename='user-device')
router.register(r'login-attempts', LoginAttemptViewSet, basename='login-attempt')

urlpatterns = [
    path('', include(router.urls)),
]
