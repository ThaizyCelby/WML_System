"""Serializers for affordability."""
from rest_framework import serializers
from .models import AffordabilityAssessment


class AffordabilityRequestSerializer(serializers.Serializer):
    gross_income = serializers.DecimalField(max_digits=15, decimal_places=2)
    monthly_expenses = serializers.DecimalField(max_digits=15, decimal_places=2)
    existing_debt = serializers.DecimalField(max_digits=15, decimal_places=2)
    proposed_repayment = serializers.DecimalField(max_digits=15, decimal_places=2)


class AffordabilityAssessmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = AffordabilityAssessment
        fields = '__all__'
        read_only_fields = ['id', 'client', 'status', 'explanation', 'result_data', 'created_at']
