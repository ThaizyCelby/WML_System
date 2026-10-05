from rest_framework import serializers
from .models import RepaymentSchedule, Repayment


class RepaymentScheduleSerializer(serializers.ModelSerializer):
    outstanding = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)

    class Meta:
        model = RepaymentSchedule
        fields = [
            'id', 'period_number', 'scheduled_date',
            'principal_portion', 'interest_portion', 'fees_portion',
            'total_amount', 'amount_paid', 'outstanding',
            'balance_after', 'status',
        ]
        read_only_fields = fields


class RepaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Repayment
        fields = ['id', 'loan', 'schedule', 'amount', 'actual_date', 'method', 'reference', 'status', 'created_at']
        read_only_fields = ['id', 'loan', 'schedule', 'status', 'created_at']
