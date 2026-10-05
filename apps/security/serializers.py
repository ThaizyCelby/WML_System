"""Serializers for security app."""
from rest_framework import serializers

from .models import (
    BlockedIP,
    FraudAlert,
    LoginAttempt,
    RiskAssessment,
    SecurityEvent,
    UserDevice,
)


class SecurityEventSerializer(serializers.ModelSerializer):
    risk_level = serializers.CharField(read_only=True)

    class Meta:
        model = SecurityEvent
        fields = [
            'id', 'user_id', 'ip_address', 'event_type', 'risk_score', 'risk_level',
            'severity', 'description', 'ai_explanation', 'action_taken', 'resolution',
            'reviewed_by', 'reviewed_at', 'created_at',
        ]
        read_only_fields = fields


class BlockedIPSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlockedIP
        fields = [
            'id', 'ip_address', 'reason', 'blocked_until', 'is_active',
            'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']


class RiskAssessmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiskAssessment
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']


class FraudAlertSerializer(serializers.ModelSerializer):
    assigned_to_email = serializers.EmailField(source='assigned_to.email', read_only=True)
    reviewed_by_email = serializers.EmailField(source='reviewed_by.email', read_only=True)

    class Meta:
        model = FraudAlert
        fields = [
            'id', 'user_id', 'alert_type', 'risk_score', 'severity',
            'summary', 'details', 'signals', 'ai_analysis',
            'status', 'assigned_to', 'assigned_to_email',
            'reviewed_by', 'reviewed_by_email', 'reviewed_at',
            'resolution_notes', 'action_taken',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'user_id', 'alert_type', 'risk_score', 'severity',
            'summary', 'details', 'signals', 'ai_analysis',
            'created_at', 'updated_at',
        ]


class LoginAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoginAttempt
        fields = [
            'id', 'user', 'email', 'ip_address', 'user_agent',
            'success', 'failure_reason', 'created_at',
        ]
        read_only_fields = fields


class UserDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserDevice
        fields = [
            'id', 'user', 'fingerprint', 'user_agent', 'first_ip',
            'last_ip', 'first_seen', 'last_seen', 'is_trusted', 'seen_count',
        ]
        read_only_fields = fields
