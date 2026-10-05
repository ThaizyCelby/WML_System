"""Deterministic affordability calculation."""
from decimal import Decimal, ROUND_HALF_UP


def calculate_affordability(
    gross_income: Decimal,
    monthly_expenses: Decimal,
    existing_debt_obligations: Decimal,
    proposed_repayment: Decimal,
) -> dict:
    """
    Calculate affordability based on the NCA approach.
    Returns a dict with status, ratios, and explanation.
    """
    # Ensure all values are Decimal
    gross_income = Decimal(gross_income or 0)
    monthly_expenses = Decimal(monthly_expenses or 0)
    existing_debt_obligations = Decimal(existing_debt_obligations or 0)
    proposed_repayment = Decimal(proposed_repayment or 0)

    # Discretionary income
    discretionary_income = gross_income - monthly_expenses - existing_debt_obligations

    # Debt-to-income ratio (existing debt only)
    dti = existing_debt_obligations / gross_income if gross_income > 0 else Decimal(0)

    # Affordability ratio (proposed repayment vs discretionary income)
    if discretionary_income > 0:
        affordability_ratio = proposed_repayment / discretionary_income
    else:
        affordability_ratio = Decimal(1) if proposed_repayment > 0 else Decimal(0)

    remaining_after_repayment = discretionary_income - proposed_repayment

    # Determine status
    if discretionary_income <= 0:
        status = 'NOT_AFFORDABLE'
        explanation = 'No discretionary income available after expenses and existing debt.'
    elif affordability_ratio <= Decimal('0.30'):
        status = 'AFFORDABLE'
        explanation = 'Proposed repayment is well within discretionary income.'
    elif affordability_ratio <= Decimal('0.50'):
        status = 'BORDERLINE'
        explanation = 'Proposed repayment consumes a significant portion of discretionary income.'
    else:
        status = 'NOT_AFFORDABLE'
        explanation = 'Proposed repayment exceeds 50% of discretionary income.'

    if remaining_after_repayment < Decimal('0'):
        status = 'NOT_AFFORDABLE'
        explanation = 'Proposed repayment leaves negative remaining income.'

    return {
        'gross_income': gross_income,
        'monthly_expenses': monthly_expenses,
        'existing_debt_obligations': existing_debt_obligations,
        'discretionary_income': discretionary_income,
        'proposed_repayment': proposed_repayment,
        'affordability_ratio': affordability_ratio,
        'debt_to_income_ratio': dti,
        'remaining_after_repayment': remaining_after_repayment,
        'status': status,
        'explanation': explanation,
    }
