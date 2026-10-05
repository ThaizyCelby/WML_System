from django.contrib import admin

from .models import DebitInstruction, PaymentTransaction, PaymentWebhook, ReconciliationRecord


@admin.register(DebitInstruction)
class DebitInstructionAdmin(admin.ModelAdmin):
    list_display = ('id', 'loan', 'provider', 'provider_reference', 'status', 'is_active', 'created_at')
    list_filter = ('provider', 'status', 'is_active')
    search_fields = ('provider_reference', 'loan__client__email')


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'loan', 'provider', 'amount', 'status', 'payment_method', 'created_at')
    list_filter = ('provider', 'status', 'payment_method')
    search_fields = ('provider_transaction_id', 'idempotency_key', 'loan__client__email')


@admin.register(PaymentWebhook)
class PaymentWebhookAdmin(admin.ModelAdmin):
    list_display = ('id', 'provider', 'webhook_type', 'provider_event_id', 'processed', 'created_at')
    list_filter = ('provider', 'processed')


@admin.register(ReconciliationRecord)
class ReconciliationRecordAdmin(admin.ModelAdmin):
    list_display = ('id', 'loan', 'status', 'expected_amount', 'actual_amount', 'difference', 'created_at')
    list_filter = ('status',)
    search_fields = ('loan__client__email',)
