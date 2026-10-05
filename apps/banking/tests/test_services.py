"""Tests for BankStatementService — covers the AI-analysis ordering bug."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.accounts.models import User
from apps.banking.models import BankStatement, BankTransaction
from apps.banking.services import BankStatementService, SPENDING_BUCKETS


# ── Fixtures ────────────────────────────────────────────────────────
@pytest.fixture
def bank_client(db):
    return User.objects.create_user(
        email='banker@wethu.test',
        password='TestPass123!',
        first_name='Bank',
        last_name='Client',
    )


@pytest.fixture
def statement(db, bank_client):
    return BankStatement.objects.create(
        client=bank_client,
        bank_name='Capitec',
        processing_status='completed',
    )


@pytest.fixture
def sample_transactions(db, statement):
    rows = [
        # credits
        (date(2026, 8, 25), 'SALARY ACME CORP', Decimal('15000.00'), 'credit', 'salary'),
        (date(2026, 8, 28), 'PAYMENT RECEIVED', Decimal('300.00'), 'credit', 'uncategorized'),
        # debits
        (date(2026, 8, 26), 'CHECKERS GROCERY', Decimal('500.00'), 'debit', 'grocery'),
        (date(2026, 8, 27), 'UBER TRIP', Decimal('120.00'), 'debit', 'transport'),
        (date(2026, 8, 29), 'NETFLIX SUBSCRIPTION', Decimal('199.00'), 'debit', 'entertainment'),
        (date(2026, 8, 30), 'DEBIT ORDER LOAN ABC', Decimal('1250.00'), 'debit', 'debit_order'),
        (date(2026, 9, 1), 'SHELL FUEL', Decimal('850.00'), 'debit', 'transport'),
    ]
    for tx_date, desc, amount, tx_type, cat in rows:
        BankTransaction.objects.create(
            statement=statement,
            transaction_date=tx_date,
            description=desc,
            amount=amount,
            transaction_type=tx_type,
            category=cat,
        )
    return statement.transactions.all()


# ── Categorization ──────────────────────────────────────────────────
@pytest.mark.django_db
class TestCategorizeTransactions:

    def test_salary_is_flagged(self, statement):
        BankTransaction.objects.create(
            statement=statement,
            transaction_date=date(2026, 8, 25),
            description='SALARY ACME CORP',
            amount=Decimal('15000.00'),
            transaction_type='credit',
        )
        BankStatementService.categorize_transactions(statement.transactions.all())
        tx = statement.transactions.first()
        assert tx.category == 'salary'
        assert tx.is_salary is True
        assert tx.is_debit_order is False

    def test_debit_order_is_flagged(self, statement):
        BankTransaction.objects.create(
            statement=statement,
            transaction_date=date(2026, 8, 26),
            description='DEBIT ORDER LOAN ABC',
            amount=Decimal('1250.00'),
            transaction_type='debit',
        )
        BankStatementService.categorize_transactions(statement.transactions.all())
        tx = statement.transactions.first()
        assert tx.category == 'debit_order'
        assert tx.is_debit_order is True
        assert tx.is_salary is False

    def test_unknown_description_is_uncategorized(self, statement):
        BankTransaction.objects.create(
            statement=statement,
            transaction_date=date(2026, 8, 27),
            description='SOMETHING RANDOM',
            amount=Decimal('100.00'),
            transaction_type='debit',
        )
        BankStatementService.categorize_transactions(statement.transactions.all())
        tx = statement.transactions.first()
        assert tx.category == 'uncategorized'
        assert tx.is_salary is False
        assert tx.is_debit_order is False

    def test_blank_description_does_not_crash(self, statement):
        """
        Empty-string description (schema uses NOT NULL, so blank is
        represented as '' — not None) should not crash the categorizer.
        """
        BankTransaction.objects.create(
            statement=statement,
            transaction_date=date(2026, 8, 27),
            description='',
            amount=Decimal('100.00'),
            transaction_type='debit',
        )
        # Should not raise
        BankStatementService.categorize_transactions(statement.transactions.all())
        tx = statement.transactions.first()
        assert tx.category == 'uncategorized'
        assert tx.is_salary is False
        assert tx.is_debit_order is False


# ── analyze_with_ai — order-of-operations ───────────────────────────
@pytest.mark.django_db
class TestAnalyzeWithAI:

    def test_fetches_transactions_before_calling_ai(self, statement, sample_transactions):
        """
        Regression test for the bug where the AI was called with an
        undefined `transactions` variable.
        """
        captured_calls = []

        def fake_run_analysis(provider, transactions, analysis_type, input_ref=''):
            captured_calls.append({
                'provider': provider,
                'count': len(transactions),
                'type': analysis_type,
                'input_ref': input_ref,
            })
            # Return None — picklable, mimics a provider that failed
            # (the real AIService returns None when all providers fail).
            return None

        with patch('apps.ai.services.AIService.run_analysis',
                   side_effect=fake_run_analysis):
            BankStatementService.analyze_with_ai(statement)

        # Three calls: payday, debt, general
        assert len(captured_calls) == 3
        # Every call must have received the 7 transactions
        for call in captured_calls:
            assert call['count'] == 7, \
                f"AI called with {call['count']} transactions"
            assert call['input_ref'] == str(statement.id)

    def test_returns_cached_result_on_second_call(self, statement, sample_transactions):
        with patch('apps.ai.services.AIService.run_analysis',
                   return_value=None) as mock_ai:
            first = BankStatementService.analyze_with_ai(statement)
            second = BankStatementService.analyze_with_ai(statement)

        # Second call must NOT hit the AI — should be served from cache.
        assert mock_ai.call_count == 3  # only the first call made 3 AI calls
        assert first == second

    def test_empty_statement_still_calls_ai_with_empty_list(self, statement):
        """No transactions — AI should still be called (with an empty list)."""
        captured = []

        def fake(provider, transactions, analysis_type, input_ref=''):
            captured.append(len(transactions))
            return None

        with patch('apps.ai.services.AIService.run_analysis', side_effect=fake):
            BankStatementService.analyze_with_ai(statement)

        assert captured == [0, 0, 0]


# ── Spending summary ────────────────────────────────────────────────
@pytest.mark.django_db
class TestSummarizeSpending:

    def test_returns_expected_shape(self, statement, sample_transactions):
        summary = BankStatementService.summarize_spending(statement)
        assert 'buckets' in summary
        assert 'monthly' in summary
        assert 'totals' in summary
        assert summary['totals']['credit'] == 15300.0
        assert summary['totals']['debit'] == 2919.0
        assert summary['totals']['net'] == 12381.0

    def test_buckets_group_correctly(self, statement, sample_transactions):
        summary = BankStatementService.summarize_spending(statement)
        bucket_names = [b['bucket'] for b in summary['buckets']]
        # 'transport' should be present with 970 (120 + 850)
        assert 'transport' in bucket_names
        transport = next(
            b for b in summary['buckets'] if b['bucket'] == 'transport'
        )
        assert transport['amount'] == 970.0

    def test_monthly_series_is_sorted(self, statement, sample_transactions):
        summary = BankStatementService.summarize_spending(statement)
        months = [m['month'] for m in summary['monthly']]
        assert months == sorted(months)
        assert '2026-08' in months
        assert '2026-09' in months

    def test_empty_statement_returns_empty(self, statement):
        summary = BankStatementService.summarize_spending(statement)
        assert summary['buckets'] == []
        assert summary['monthly'] == []
        assert summary['totals'] == {'credit': 0.0, 'debit': 0.0, 'net': 0.0}

    def test_spending_buckets_constant_has_expected_keys(self):
        expected = {
            'groceries', 'transport', 'entertainment', 'debit_orders',
            'loan_repayments', 'airtime_data', 'cash_withdrawal', 'bank_fees',
            'transfers', 'retail', 'insurance', 'education', 'gambling', 'alcohol',
        }
        assert expected.issubset(SPENDING_BUCKETS.keys())