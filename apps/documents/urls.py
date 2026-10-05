from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import DocumentViewSet, DocumentReviewViewSet

router = DefaultRouter()
# IMPORTANT: register 'review' BEFORE the empty '' prefix.
router.register(r'review', DocumentReviewViewSet, basename='document-review')
router.register(r'', DocumentViewSet, basename='document')

urlpatterns = [
    path('', include(router.urls)),
]