"""Views for the AI app."""
from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import AIAnalysis
from .serializers import AIAnalysisSerializer


class AIAnalysisViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only list/detail of AI analyses."""
    serializer_class = AIAnalysisSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['provider', 'model_name', 'human_reviewed']
    search_fields = ['input_reference', 'provider', 'model_name']
    ordering_fields = ['created_at', 'confidence']
    ordering = ['-created_at']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return AIAnalysis.objects.none()
        user = self.request.user
        if not user.is_authenticated:
            return AIAnalysis.objects.none()
        if user.is_superuser or user.has_role('Administrator'):
            return AIAnalysis.objects.all()
        statement_ids = user.bank_statements.values_list('id', flat=True)
        return AIAnalysis.objects.filter(
            input_reference__in=[str(sid) for sid in statement_ids]
        )


@extend_schema(
    operation_id='ai_health',
    responses={200: OpenApiTypes.OBJECT},
    description=(
        'Return configuration status for each AI provider. '
        'Never exposes API keys — only boolean flags and model names.'
    ),
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def ai_health(request):
    """Return configuration status for each AI provider (no keys exposed)."""
    result = {}
    for name, cfg in settings.AI_PROVIDERS.items():
        result[name] = {
            'enabled': bool(cfg.get('enabled')),
            'has_key': bool(cfg.get('api_key')),
            'model': cfg.get('model', ''),
        }
    result['mock'] = {'enabled': True, 'has_key': True, 'model': 'mock'}
    result['fallback_to_mock'] = getattr(settings, 'AI_FALLBACK_TO_MOCK', True)
    return Response(result)