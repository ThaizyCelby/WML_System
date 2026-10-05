from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import AffordabilityViewSet

router = DefaultRouter()
router.register(r'assessments', AffordabilityViewSet, basename='affordability-assessment')

urlpatterns = [
    path('', include(router.urls)),
]
