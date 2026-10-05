"""Pull and persist credit bureau reports."""
import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.services import AuditService

from .credit_bureau.factory import get_credit_bureau_provider
from .credit_bureau.base import CreditBureauError, CreditBureauConsentRequired
from .models import CreditReport, TradeLine

logger = logging.getLogger('apps.kyc')


CONSENT_CODE = 'credit_check_consent'


class CreditBureauService:

    @staticmethod
    def has_valid_report(user) -> CreditReport | None:
        """Return the latest non-expired report for the user, or None."""
        return (
            CreditReport.objects
            .filter(user=user, expires_at__gt=timezone.now())
            .order_by('-created_at')
            .first()
        )

    @staticmethod
    def _has_consent(user) -> bool:
        try:
            profile = user.client_profile
        except Exception:
            return False
        consents = profile.consent_records or {}
        entry = consents.get(CONSENT_CODE) or {}
        return bool(entry.get('granted'))

    @staticmethod
    @transaction.atomic
    def pull_report(user, *, actor=None, ip_address=None) -> CreditReport:
        """
        Pull a fresh credit report. Requires consent; will fail if missing.
        Reuses a valid report if one exists and `force=False`.
        """
        if not CreditBureauService._has_consent(user):
            raise CreditBureauConsentRequired(
                'Client has not consented to a credit bureau check.'
            )

        existing = CreditBureauService.has_valid_report(user)
        if existing:
            return existing

        id_number = getattr(getattr(user, 'client_profile', None), 'id_number', '') or ''
        if not id_number:
            raise CreditBureauError('Client ID number is required for a credit check.')

        provider = get_credit_bureau_provider()
        if not provider.is_configured():
            raise CreditBureauError(f"Credit bureau '{provider.name}' is not configured.")

        report_data = provider.pull_report(
            id_number=id_number,
            first_name=user.first_name or '',
            last_name=user.last_name or '',
        )

        validity = getattr(settings, 'CREDIT_REPORT_VALIDITY_DAYS', 30)

        report = CreditReport.objects.create(
            user=user,
            id_number=id_number,
            bureau=provider.name,
            score=report_data.score,
            risk_band=report_data.risk_band or '',
            total_monthly_obligations=Decimal(str(report_data.total_monthly_obligations)),
            total_outstanding_debt=Decimal(str(report_data.total_outstanding_debt)),
            worst_arrears_months=report_data.worst_arrears_months,
            has_defaults=report_data.has_defaults,
            has_judgments=report_data.has_judgments,
            raw_response=report_data.raw_response,
            pulled_by=actor or user,
            consented_at=timezone.now(),
            expires_at=timezone.now() + timedelta(days=validity),
        )

        for t in report_data.trade_lines:
            TradeLine.objects.create(
                credit_report=report,
                creditor_name=t.creditor_name[:200],
                account_type=t.account_type[:50],
                account_number_masked=t.account_number_masked[:30],
                monthly_installment=Decimal(str(t.monthly_installment)),
                outstanding_balance=Decimal(str(t.outstanding_balance)),
                original_amount=Decimal(str(t.original_amount)) if t.original_amount is not None else None,
                opened_date=None,  # parse ISO if needed
                status=t.status[:20],
                arrears_amount=Decimal(str(t.arrears_amount)),
                months_in_arrears=t.months_in_arrears,
                is_secured=t.is_secured,
                raw=t.raw,
            )

        AuditService.record(
            actor=actor or user,
            action='credit_report_pulled',
            object_type='credit_report',
            object_id=str(report.id),
            ip_address=ip_address,
            after_value={
                'bureau': provider.name,
                'score': report.score,
                'total_monthly_obligations': str(report.total_monthly_obligations),
                'expires_at': report.expires_at.isoformat(),
            },
        )

        logger.info(
            "Credit report pulled for %s via %s: score=%s, monthly obligations=%s",
            user.email, provider.name, report.score, report.total_monthly_obligations,
        )
        return report