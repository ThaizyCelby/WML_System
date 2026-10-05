"""Serializers for KYC, credit bureau, and document replacement."""
from rest_framework import serializers

from apps.accounts.models import ClientProfile
from apps.documents.models import DocumentReplacementRequest

from .models import CreditReport, KYCReview, TradeLine


class ClientProfileKYCSerializer(serializers.ModelSerializer):
    """Staff-facing view of a client's KYC profile."""
    full_name = serializers.CharField(source='user.full_name', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = ClientProfile
        fields = [
            'id', 'email', 'full_name', 'kyc_status',
            'id_number', 'date_of_birth', 'residential_address',
            'employment_type', 'employer_name', 'monthly_income',
            'monthly_expenses', 'existing_debt_obligations',
            'bank_name', 'account_type', 'branch_code',
            'consent_records', 'communication_preferences',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields


class KYCReviewSerializer(serializers.ModelSerializer):
    reviewer_email = serializers.EmailField(source='reviewed_by.email', read_only=True)

    class Meta:
        model = KYCReview
        fields = [
            'id', 'previous_status', 'new_status', 'notes',
            'reviewer_email', 'reviewed_at',
        ]
        read_only_fields = fields


class DocumentReplacementRequestSerializer(serializers.ModelSerializer):
    document_type = serializers.CharField(source='document.document_type', read_only=True)
    document_filename = serializers.CharField(source='document.original_filename', read_only=True)
    requested_by_email = serializers.EmailField(source='requested_by.email', read_only=True)
    reviewed_by_email = serializers.EmailField(source='reviewed_by.email', read_only=True)

    class Meta:
        model = DocumentReplacementRequest
        fields = [
            'id', 'document', 'document_type', 'document_filename',
            'requested_by', 'requested_by_email', 'reason',
            'status', 'reviewed_by', 'reviewed_by_email',
            'reviewed_at', 'review_notes', 'created_at',
        ]
        read_only_fields = [
            'id', 'document', 'requested_by', 'status',
            'reviewed_by', 'reviewed_at', 'review_notes', 'created_at',
        ]


class TradeLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = TradeLine
        fields = [
            'id', 'creditor_name', 'account_type', 'account_number_masked',
            'monthly_installment', 'outstanding_balance', 'original_amount',
            'status', 'arrears_amount', 'months_in_arrears', 'is_secured',
        ]
        read_only_fields = fields


class CreditReportSerializer(serializers.ModelSerializer):
    """
    Serialized credit report.

    Includes the aggregated figures and the individual trade lines. Only the
    owner of the report (or authorised staff) may retrieve it — enforced at
    the queryset level in the view, not here.
    """
    trade_lines = TradeLineSerializer(many=True, read_only=True)

    class Meta:
        model = CreditReport
        fields = [
            'id', 'bureau', 'score', 'risk_band',
            'total_monthly_obligations', 'total_outstanding_debt',
            'worst_arrears_months', 'has_defaults', 'has_judgments',
            'consented_at', 'expires_at', 'created_at',
            'trade_lines',
        ]
        read_only_fields = fields


class ProfileCompletenessSerializer(serializers.Serializer):
    """Read-only representation of a client's profile completeness."""
    complete = serializers.BooleanField(read_only=True)
    gaps = serializers.ListField(
        child=serializers.DictField(), read_only=True,
    )