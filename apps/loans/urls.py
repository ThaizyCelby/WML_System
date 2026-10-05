from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import LoanProductViewSet, LoanApplicationViewSet, LoanViewSet

router = DefaultRouter()
router.register(r'products', LoanProductViewSet, basename='loan-product')
router.register(r'applications', LoanApplicationViewSet, basename='loan-application')
router.register(r'loans', LoanViewSet, basename='loan')

urlpatterns = [path('', include(router.urls))]
