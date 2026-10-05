"""Serializers for payment models."""
from rest_framework import serializers

from .models import DebitInstruction, PaymentTransaction, ReconciliationRecord


class DebitInstructionSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for debit instruction (mandate) records.

    Full account numbers are never exposed. Only `account_number_last4` is
    returned. The full number is stored encrypted in
    `account_number_encrypted` on the model and never leaves the server.
    """

    class Meta:
        model = DebitInstruction
        fields = [
            'id', 'loan', 'provider', 'provider_reference',
            'account_holder_name', 'account_number_last4',
            'bank_name', 'branch_code', 'account_type',
            'status', 'is_active', 'created_at',
        ]
        read_only_fields = fields


class PaymentTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentTransaction
        fields = [
            'id', 'loan', 'repayment_schedule_id', 'provider',
            'provider_transaction_id', 'amount', 'status',
            'payment_method', 'error_message', 'created_at', 'updated_at',
        ]
        read_only_fields = fields


class ReconciliationRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReconciliationRecord
        fields = [
            'id', 'loan', 'expected_amount', 'actual_amount', 'difference',
            'status', 'notes', 'created_at',
        ]
        read_only_fields = fields