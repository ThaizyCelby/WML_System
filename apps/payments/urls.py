from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    PaymentTransactionViewSet, DebitInstructionViewSet, ReconciliationViewSet,
    payment_webhook,
)

router = DefaultRouter()
router.register(r'transactions', PaymentTransactionViewSet, basename='payment-transaction')
router.register(r'debit-instructions', DebitInstructionViewSet, basename='debit-instruction')
router.register(r'reconciliation', ReconciliationViewSet, basename='reconciliation')

urlpatterns = [
    path('webhook/', payment_webhook, name='payment-webhook'),
    path('', include(router.urls)),
]
