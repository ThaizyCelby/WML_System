from rest_framework import serializers
from .models import AIAnalysis


class AIAnalysisSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIAnalysis
        fields = [
            'id', 'provider', 'model_name', 'input_reference',
            'output_data', 'confidence', 'explanation',
            'human_reviewed', 'reviewed_by', 'created_at',
        ]
        read_only_fields = fields
