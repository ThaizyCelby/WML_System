"""
Deterministic default-risk scorer.

This is intentionally NOT an LLM. The score is derived from observable
loan history, payment behaviour, and current arrears. An AI advisory can
be layered on top (see `enrich_with_ai` below) but the raw score is what
the staff portal uses.
"""
from datetime import date
from decimal import Decimal


def _days_overdue(loan) -> int:
    """Return the maximum days any pending schedule row is overdue."""
    today = date.today()
    overdue = loan.repayment_schedule.filter(
        status__in=['pending', 'partial', 'overdue'],
        scheduled_date__lt=today,
    ).order_by('scheduled_date').first()
    if not overdue:
        return 0
    return (today - overdue.scheduled_date).days


def _missed_count(loan) -> int:
    """Number of schedule rows currently overdue."""
    return loan.repayment_schedule.filter(
        status__in=['pending', 'partial', 'overdue'],
        scheduled_date__lt=date.today(),
    ).count()


def _payment_ratio(loan) -> Decimal:
    """Fraction of the total due that has been paid. 0..1."""
    total_due = loan.principal_amount + loan.total_interest + loan.fees_total
    if total_due <= 0:
        return Decimal('1')
    paid = total_due - loan.outstanding_balance
    return max(Decimal('0'), min(Decimal('1'), paid / total_due))


def _dti(loan) -> Decimal:
    """Debt-to-income ratio at application time (approximate)."""
    try:
        profile = loan.client.client_profile
        income = profile.monthly_income or Decimal('0')
        debts = profile.existing_debt_obligations or Decimal('0')
        if income <= 0:
            return Decimal('1')
        return min(Decimal('2'), debts / income)
    except Exception:
        return Decimal('0.5')


def compute_risk(loan) -> dict:
    """
    Compute the fallout score for a loan.

    Scoring rules (each contributes weighted points):
      - Days overdue (40 pts max)
      - Number of missed instalments (20 pts max)
      - Payment ratio (20 pts max — inverse)
      - DTI (10 pts max)
      - Loan status flag (10 pts max — defaulted/overdue get full)
    """
    days = _days_overdue(loan)
    missed = _missed_count(loan)
    ratio = _payment_ratio(loan)
    dti = _dti(loan)

    # Days overdue: 40 pts at 90+ days, linear below
    days_score = min(40, int(days / 90 * 40))

    # Missed instalments: 20 pts at 4+ misses
    missed_score = min(20, missed * 5)

    # Payment ratio: full 20 pts if ratio = 0, 0 pts if ratio = 1
    ratio_score = int((Decimal('1') - ratio) * 20)

    # DTI: 10 pts at 1.0+, linear below
    dti_score = min(10, int(dti * 10))

    # Status flag
    status_score = {
        'active': 0, 'paid': 0, 'pending': 0,
        'overdue': 5, 'defaulted': 10,
    }.get(loan.status, 0)

    total = days_score + missed_score + ratio_score + dti_score + status_score
    total = max(0, min(100, total))

    if total >= 80:
        band = 'critical'
    elif total >= 60:
        band = 'high'
    elif total >= 30:
        band = 'medium'
    else:
        band = 'low'

    return {
        'score': total,
        'band': band,
        'factors': {
            'days_overdue': days,
            'missed_installments': missed,
            'payment_ratio': float(ratio),
            'dti': float(dti),
            'sub_scores': {
                'days': days_score,
                'missed': missed_score,
                'ratio': ratio_score,
                'dti': dti_score,
                'status': status_score,
            },
        },
    }


def enrich_with_ai(loan, risk: dict) -> dict:
    """
    Optional: ask the configured AI provider for a short narrative.
    Falls back silently if AI is unavailable.
    """
    try:
        from django.conf import settings
        from apps.ai.services import AIService
        provider = getattr(settings, 'AI_DEFAULT_PROVIDER', 'glm')
        record = AIService.run_analysis(
            provider,
            [{'loan_id': str(loan.id), 'risk': risk}],
            'general',
            input_ref=f'loan-risk-{loan.id}',
        )
        if record and record.output_data:
            risk['ai_advisory'] = record.output_data
    except Exception:
        pass
    return risk