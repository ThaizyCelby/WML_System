from django.contrib import admin
from .models import BankStatement, BankTransaction


@admin.register(BankStatement)
class BankStatementAdmin(admin.ModelAdmin):
    list_display = ('id', 'client', 'bank_name', 'processing_status', 'created_at')
    list_filter = ('processing_status', 'bank_name')
    search_fields = ('client__email', 'account_number_masked')


@admin.register(BankTransaction)
class BankTransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'statement', 'transaction_date', 'description', 'amount', 'transaction_type', 'category')
    list_filter = ('transaction_type', 'category', 'is_salary', 'is_debit_order')
    search_fields = ('description', 'merchant_name')
