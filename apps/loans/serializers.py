from rest_framework import serializers
from .models import Loan, LoanAgreement, LoanApplication, LoanProduct, LoanApplicationEvent


class LoanProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoanProduct
        fields = '__all__'


class LoanSerializer(serializers.ModelSerializer):
    client_email = serializers.EmailField(source='client.email', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = Loan
        fields = [
            'id', 'client_email', 'product_name', 'principal_amount',
            'interest_rate', 'total_interest', 'fees_total',
            'term_periods', 'repayment_frequency', 'start_date', 'end_date',
            'outstanding_balance', 'status', 'created_at',
        ]
        read_only_fields = fields


class LoanAgreementSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoanAgreement
        fields = [
            'id', 'loan', 'version', 'status', 'agreement_hash',
            'generated_at', 'accepted_at', 'accepted_by', 'accepted_ip',
        ]
        read_only_fields = fields


class LoanApplicationSerializer(serializers.ModelSerializer):
    client_email = serializers.EmailField(source='client.email', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = LoanApplication
        fields = [
            'id', 'client_email', 'product_name', 'requested_amount', 'requested_term',
            'status', 'kyc_status_snapshot', 'affordability_result',
            'credit_review_notes', 'approved_amount', 'approved_term',
            'interest_rate', 'submitted_at', 'reviewed_at', 'created_at', 'updated_at',
        ]
        read_only_fields = ['client','status','affordability_result','submitted_at','reviewed_at']

    def validate_requested_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError('Amount must be positive.')
        return value

    def validate_requested_term(self, value):
        if value < 1:
            raise serializers.ValidationError('Term must be at least 1 month.')
        return value


class LoanApplicationCreateSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=15, decimal_places=2)
    term = serializers.IntegerField(min_value=1)


class LoanApplicationEventSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source='actor.email', read_only=True)

    class Meta:
        model = LoanApplicationEvent
        fields = ['id', 'from_status', 'to_status', 'actor_email', 'notes', 'timestamp']
