from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import RepaymentScheduleViewSet, RepaymentViewSet

router = DefaultRouter()
router.register(r'schedules', RepaymentScheduleViewSet, basename='repayment-schedule')
router.register(r'payments', RepaymentViewSet, basename='repayment')

urlpatterns = [path('', include(router.urls))]
