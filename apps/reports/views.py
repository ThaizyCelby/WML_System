"""Reporting endpoints."""
import csv
from datetime import date

from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.loans.models import Loan, LoanApplication
from apps.repayments.models import RepaymentSchedule
from .services import ReportsService


def _require_staff(user):
    return (
        user.is_superuser
        or user.has_role('Administrator')
        or user.has_role('Finance Officer')
        or user.has_role('Credit Officer')
        or user.has_role('Auditor')
    )


class ReportsViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def _guard(self, request):
        if not _require_staff(request.user):
            return Response({'detail': 'Not allowed.'}, status=403)
        return None

    @extend_schema(
        operation_id='reports_portfolio',
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=['get'])
    def portfolio(self, request):
        g = self._guard(request)
        if g:
            return g
        return Response(ReportsService.portfolio_summary())

    @extend_schema(
        operation_id='reports_applications',
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=['get'])
    def applications(self, request):
        g = self._guard(request)
        if g:
            return g
        days = int(request.query_params.get('days', 30))
        return Response(ReportsService.application_stats(days))

    @extend_schema(
        operation_id='reports_repayments',
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=['get'])
    def repayments(self, request):
        g = self._guard(request)
        if g:
            return g
        days = int(request.query_params.get('days', 30))
        return Response(ReportsService.repayment_stats(days))

    @extend_schema(
        operation_id='reports_delinquency',
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=['get'])
    def delinquency(self, request):
        g = self._guard(request)
        if g:
            return g
        return Response(ReportsService.delinquency_report())

    @extend_schema(
        operation_id='reports_reconciliation',
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=['get'])
    def reconciliation(self, request):
        g = self._guard(request)
        if g:
            return g
        days = int(request.query_params.get('days', 30))
        return Response(ReportsService.reconciliation_summary(days))

    @extend_schema(
        operation_id='reports_export_loans_csv',
        responses={(200, 'text/csv'): OpenApiTypes.BINARY},
    )
    @action(detail=False, methods=['get'])
    def export_loans_csv(self, request):
        g = self._guard(request)
        if g:
            return g
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = (
            f'attachment; filename="loans-{date.today().isoformat()}.csv"'
        )
        writer = csv.writer(response)
        writer.writerow([
            'Loan ID', 'Client Email', 'Product', 'Principal',
            'Interest Rate', 'Term', 'Outstanding', 'Status', 'Created',
        ])
        for loan in Loan.objects.select_related('client', 'product').iterator():
            writer.writerow([
                str(loan.id), loan.client.email,
                loan.product.name if loan.product else '',
                loan.principal_amount, loan.interest_rate, loan.term_periods,
                loan.outstanding_balance, loan.status,
                loan.created_at.isoformat(),
            ])
        return response

    @extend_schema(
        operation_id='reports_export_repayments_csv',
        responses={(200, 'text/csv'): OpenApiTypes.BINARY},
    )
    @action(detail=False, methods=['get'])
    def export_repayments_csv(self, request):
        g = self._guard(request)
        if g:
            return g
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = (
            f'attachment; filename="repayments-{date.today().isoformat()}.csv"'
        )
        writer = csv.writer(response)
        writer.writerow([
            'Loan ID', 'Period', 'Due Date', 'Total', 'Paid',
            'Outstanding', 'Status',
        ])
        for row in RepaymentSchedule.objects.select_related('loan').iterator():
            writer.writerow([
                str(row.loan_id), row.period_number, row.scheduled_date,
                row.total_amount, row.amount_paid,
                row.total_amount - row.amount_paid, row.status,
            ])
        return response