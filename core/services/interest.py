from decimal import Decimal

DEFAULT_ANNUAL_RATE = Decimal("0.30")

def simple_interest(principal: Decimal, annual_rate: Decimal, years: Decimal) -> Decimal:
    return (principal * annual_rate * years).quantize(Decimal("0.01"))
