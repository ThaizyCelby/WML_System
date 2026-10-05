"""Affordability engine (deterministic)."""
from decimal import Decimal, ROUND_HALF_UP


class AffordabilityEngine:
    @staticmethod
    def calculate(
        gross_income: Decimal,
        monthly_expenses: Decimal,
        existing_debt: Decimal,
        proposed_repayment: Decimal,
    ) -> dict:
        """
        Deterministic affordability calculation.
        Returns a dictionary with status and detailed breakdown.
        """
        gross_income = Decimal(gross_income or 0)
        monthly_expenses = Decimal(monthly_expenses or 0)
        existing_debt = Decimal(existing_debt or 0)
        proposed_repayment = Decimal(proposed_repayment or 0)

        if gross_income <= 0:
            return {
                'status': 'INSUFFICIENT_DATA',
                'explanation': 'Gross income must be greater than zero.',
                'discretionary_income': Decimal('0'),
                'affordability_ratio': None,
                'debt_to_income_ratio': None,
                'remaining_after_repayment': Decimal('0'),
            }

        discretionary_income = gross_income - monthly_expenses - existing_debt
        dti = existing_debt / gross_income if gross_income > 0 else Decimal('0')

        if discretionary_income <= 0:
            status = 'NOT_AFFORDABLE'
            explanation = 'No discretionary income available.'
            affordability_ratio = Decimal('1') if proposed_repayment > 0 else Decimal('0')
            remaining = discretionary_income - proposed_repayment
        else:
            affordability_ratio = proposed_repayment / discretionary_income
            remaining = discretionary_income - proposed_repayment

            if affordability_ratio <= Decimal('0.30'):
                status = 'AFFORDABLE'
                explanation = 'Proposed repayment is within 30% of discretionary income.'
            elif affordability_ratio <= Decimal('0.50'):
                status = 'BORDERLINE'
                explanation = 'Proposed repayment consumes 30-50% of discretionary income.'
            else:
                status = 'NOT_AFFORDABLE'
                explanation = 'Proposed repayment exceeds 50% of discretionary income.'

        if remaining < 0:
            status = 'NOT_AFFORDABLE'
            explanation = 'Proposed repayment leaves negative remaining income.'

        return {
            'gross_income': gross_income,
            'monthly_expenses': monthly_expenses,
            'existing_debt_obligations': existing_debt,
            'discretionary_income': discretionary_income,
            'proposed_repayment': proposed_repayment,
            'affordability_ratio': affordability_ratio.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'debt_to_income_ratio': dti.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'remaining_after_repayment': remaining.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'status': status,
            'explanation': explanation,
        }

    @classmethod
    def from_client_with_report(cls, client_profile, credit_report, proposed_repayment):
        """
        Compute affordability using verified income (profile) and verified debt
        (credit report). This is the authoritative path for loan applications.
        """
        gross = client_profile.monthly_income
        expenses = client_profile.monthly_expenses

        if credit_report is not None:
            existing_debt = credit_report.total_monthly_obligations
        else:
            existing_debt = client_profile.existing_debt_obligations

        return cls.calculate(gross, expenses, existing_debt, proposed_repayment)