"""Mock credit bureau adapter.

DEVELOPMENT / TESTING ONLY.

This adapter returns deterministic synthetic data. It is NOT connected to any
real credit bureau and MUST NOT be enabled in production.
"""
import hashlib
from datetime import date

from .base import CreditBureauProvider, CreditReport, TradeLine


class MockCreditBureauProvider(CreditBureauProvider):
    name = 'mock'

    def is_configured(self) -> bool:
        return True

    def pull_report(self, *, id_number: str, first_name: str, last_name: str) -> CreditReport:
        # Deterministic seed from the ID number
        seed = int(hashlib.sha256(id_number.encode()).hexdigest(), 16) % 10000

        trade_lines = [
            TradeLine(
                creditor_name='Example Retail Store',
                account_type='retail',
                account_number_masked='****1234',
                monthly_installment=450.00,
                outstanding_balance=3200.00,
                original_amount=8000.00,
                opened_date='2024-03-01',
                status='current',
                is_secured=False,
            ),
            TradeLine(
                creditor_name='Example Bank Credit Card',
                account_type='credit_card',
                account_number_masked='****5678',
                monthly_installment=600.00,
                outstanding_balance=7500.00,
                original_amount=10000.00,
                opened_date='2023-07-15',
                status='current',
                is_secured=False,
            ),
        ]

        # Add a late account for ~30% of IDs
        if seed % 10 < 3:
            trade_lines.append(TradeLine(
                creditor_name='Example Personal Loan',
                account_type='personal_loan',
                account_number_masked='****9012',
                monthly_installment=1200.00,
                outstanding_balance=14500.00,
                original_amount=20000.00,
                opened_date='2023-01-20',
                status='delinquent',
                arrears_amount=1200.00,
                months_in_arrears=2,
                is_secured=False,
            ))

        total_monthly = sum(t.monthly_installment for t in trade_lines)
        total_outstanding = sum(t.outstanding_balance for t in trade_lines)
        worst_arrears = max((t.months_in_arrears for t in trade_lines), default=0)

        return CreditReport(
            id_number=id_number,
            bureau='mock',
            score=650,
            risk_band='medium',
            trade_lines=trade_lines,
            total_monthly_obligations=total_monthly,
            total_outstanding_debt=total_outstanding,
            worst_arrears_months=worst_arrears,
            has_defaults=False,
            has_judgments=False,
            raw_response={'note': 'mock data'},
        )