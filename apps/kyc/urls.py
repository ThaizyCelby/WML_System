from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    DocumentReplacementRequestViewSet,
    KYCViewSet,
    latest_credit_report,
    profile_completeness,
    pull_credit_report,
)

router = DefaultRouter()
router.register(r'profiles', KYCViewSet, basename='kyc-profile')
router.register(
    r'document-replacement-requests',
    DocumentReplacementRequestViewSet,
    basename='document-replacement-request',
)

urlpatterns = [
    # Credit bureau + completeness (client-facing)
    path('profile-completeness/', profile_completeness, name='profile-completeness'),
    path('credit-report/pull/', pull_credit_report, name='credit-report-pull'),
    path('credit-report/latest/', latest_credit_report, name='credit-report-latest'),

    # Viewset routes
    path('', include(router.urls)),
]