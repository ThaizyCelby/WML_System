"""Interest calculation engine."""
from decimal import Decimal, ROUND_HALF_UP
from typing import List


def calculate_flat_interest(principal: Decimal, annual_rate: Decimal, term_months: int) -> Decimal:
    """
    Flat interest: Interest = P * r * t, where t is in years.
    Annual rate is a percentage (e.g., 30.00 for 30%).
    """
    rate_decimal = annual_rate / Decimal('100')
    years = Decimal(term_months) / Decimal('12')
    interest = principal * rate_decimal * years
    return interest.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def calculate_simple_interest(principal: Decimal, annual_rate: Decimal, term_months: int) -> Decimal:
    """Simple interest (same as flat for single period, but provided for clarity)."""
    return calculate_flat_interest(principal, annual_rate, term_months)


def calculate_amortized_monthly_payment(principal: Decimal, annual_rate: Decimal, term_months: int) -> Decimal:
    """
    Monthly payment for amortized loan using standard formula.
    Payment = P * r * (1+r)^n / ((1+r)^n - 1)
    """
    if term_months == 0:
        return principal
    monthly_rate = annual_rate / Decimal('100') / Decimal('12')
    if monthly_rate == 0:
        return principal / Decimal(term_months)

    factor = (1 + monthly_rate) ** term_months
    payment = principal * monthly_rate * factor / (factor - 1)
    return payment.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def generate_amortization_schedule(principal: Decimal, annual_rate: Decimal, term_months: int) -> List[dict]:
    """Generate a full amortization schedule (principal + interest breakdown)."""
    payment = calculate_amortized_monthly_payment(principal, annual_rate, term_months)
    monthly_rate = annual_rate / Decimal('100') / Decimal('12')
    balance = principal
    schedule = []
    for period in range(1, term_months + 1):
        interest_payment = balance * monthly_rate
        principal_payment = payment - interest_payment
        if principal_payment > balance:  # last payment adjustment
            principal_payment = balance
            interest_payment = payment - principal_payment
        balance -= principal_payment
        schedule.append({
            'period': period,
            'payment': payment.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'principal': principal_payment.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'interest': interest_payment.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'remaining_balance': balance.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        })
    return schedule


def calculate_total_repayment(principal: Decimal, annual_rate: Decimal, term_months: int, interest_type: str) -> dict:
    """Unified method returns total interest, total repayment, and schedule."""
    if interest_type == 'flat':
        interest = calculate_flat_interest(principal, annual_rate, term_months)
        schedule = []
        monthly_principal = (principal / Decimal(term_months)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        monthly_interest = (interest / Decimal(term_months)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        for i in range(1, term_months+1):
            schedule.append({
                'period': i,
                'payment': (monthly_principal + monthly_interest).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
                'principal': monthly_principal,
                'interest': monthly_interest,
                'remaining_balance': (principal - monthly_principal * i).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            })
        total_interest = interest
        total_repayment = principal + interest
    elif interest_type == 'amortized':
        schedule = generate_amortization_schedule(principal, annual_rate, term_months)
        total_interest = sum(item['interest'] for item in schedule)
        total_repayment = principal + total_interest
    else:  # simple
        interest = calculate_simple_interest(principal, annual_rate, term_months)
        schedule = []
        monthly_principal = (principal / Decimal(term_months)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        monthly_interest = (interest / Decimal(term_months)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        for i in range(1, term_months+1):
            schedule.append({
                'period': i,
                'payment': (monthly_principal + monthly_interest).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
                'principal': monthly_principal,
                'interest': monthly_interest,
                'remaining_balance': (principal - monthly_principal * i).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            })
        total_interest = interest
        total_repayment = principal + interest

    return {
        'principal': principal,
        'total_interest': total_interest.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        'total_repayment': total_repayment.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        'schedule': schedule,
    }
