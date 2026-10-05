from rest_framework import serializers
from .models import BankStatement, BankTransaction


class BankTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankTransaction
        fields = [
            'id', 'transaction_date', 'description', 'amount',
            'transaction_type', 'category', 'is_salary', 'is_debit_order',
            'merchant_name', 'confidence_score', 'created_at',
        ]
        read_only_fields = fields


class BankStatementSerializer(serializers.ModelSerializer):
    transactions = BankTransactionSerializer(many=True, read_only=True)
    client_email = serializers.EmailField(source='client.email', read_only=True)

    class Meta:
        model = BankStatement
        fields = [
            'id', 'client_email', 'bank_name', 'account_number_masked',
            'statement_period_start', 'statement_period_end',
            'processing_status', 'extraction_confidence',
            'transactions', 'created_at', 'updated_at',
        ]
        read_only_fields = fields


class BankStatementUploadSerializer(serializers.Serializer):
    document_id = serializers.UUIDField(required=True)
    bank_name = serializers.CharField(required=False, allow_blank=True, max_length=100)
    account_number_masked = serializers.CharField(required=False, allow_blank=True, max_length=30)
