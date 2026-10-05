"""URLs for the AI app."""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import AIAnalysisViewSet, ai_health

router = DefaultRouter()
router.register(r'analyses', AIAnalysisViewSet, basename='ai-analysis')

urlpatterns = [
    path('health/', ai_health, name='ai-health'),
    path('', include(router.urls)),
]
