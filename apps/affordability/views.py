"""Views for affordability calculation."""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import AffordabilityAssessment
from .serializers import AffordabilityRequestSerializer, AffordabilityAssessmentSerializer
from .engine import AffordabilityEngine


def _convert_decimals_to_strings(obj):
    """Recursively convert Decimal objects to strings for JSON serialization."""
    from decimal import Decimal
    import json
    if isinstance(obj, Decimal):
        return str(obj)
    elif isinstance(obj, dict):
        return {key: _convert_decimals_to_strings(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [_convert_decimals_to_strings(item) for item in obj]
    else:
        return obj


class AffordabilityViewSet(viewsets.ModelViewSet):
    """Endpoints to calculate and store affordability results."""
    serializer_class = AffordabilityAssessmentSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['post', 'get', 'head', 'options']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return AffordabilityAssessment.objects.none()
        user = self.request.user
        if not user.is_authenticated:
            return AffordabilityAssessment.objects.none()
        return AffordabilityAssessment.objects.filter(client=user)

    def create(self, request, *args, **kwargs):
        request_serializer = AffordabilityRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        data = request_serializer.validated_data

        result = AffordabilityEngine.calculate(
            gross_income=data['gross_income'],
            monthly_expenses=data['monthly_expenses'],
            existing_debt=data['existing_debt'],
            proposed_repayment=data['proposed_repayment'],
        )

        result_for_json = _convert_decimals_to_strings(result)

        assessment = AffordabilityAssessment.objects.create(
            client=request.user,
            gross_income=data['gross_income'],
            monthly_expenses=data['monthly_expenses'],
            existing_debt_obligations=data['existing_debt'],
            proposed_repayment=data['proposed_repayment'],
            status=result['status'],
            explanation=result['explanation'],
            result_data=result_for_json,
        )

        output_serializer = AffordabilityAssessmentSerializer(assessment)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)
