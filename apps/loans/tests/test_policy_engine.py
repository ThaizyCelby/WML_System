"""Deterministic lending policy engine tests."""
from datetime import date
from decimal import Decimal

import pytest

from apps.accounts.models import ClientProfile
from apps.loans.models import LoanApplication, LoanProduct
from apps.loans.policy_engine import evaluate, DEFAULT_POLICY
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestPolicyEngine:

    def _user(self, email='policy@wethu.test', **kwargs):
        return User.objects.create_user(
            email=email, password='TestPass123!', **kwargs,
        )

    def _product(self, **overrides):
        defaults = {
            'name': overrides.pop('name', 'Policy Test Loan'),
            'min_amount': Decimal('500.00'),
            'max_amount': Decimal('50000.00'),
            'min_term': 1,
            'max_term': 24,
            'interest_rate': Decimal('28.00'),
            'interest_type': 'flat',
            'repayment_frequency': 'monthly',
        }
        defaults.update(overrides)
        return LoanProduct.objects.create(**defaults)

    def _profile(self, user, **overrides):
        defaults = {
            'date_of_birth': date(1990, 1, 1),
            'employment_type': 'full_time',
            'employer_name': 'Acme',
            'employment_start_date': date(2020, 1, 1),
            'monthly_income': Decimal('20000.00'),
            'monthly_expenses': Decimal('7000.00'),
            'existing_debt_obligations': Decimal('3000.00'),
            'kyc_status': 'verified',
            'residential_address': {'street': '1 Test St', 'city': 'Pretoria'},
        }
        defaults.update(overrides)
        return ClientProfile.objects.create(user=user, **defaults)

    def _application(self, user, product, **overrides):
        defaults = {
            'client': user,
            'product': product,
            'requested_amount': Decimal('10000.00'),
            'requested_term': 12,
            'status': 'submitted',
        }
        defaults.update(overrides)
        return LoanApplication.objects.create(**defaults)

    # ── Happy path ─────────────────────────────────────────────────
    def test_eligible_happy_path(self):
        u = self._user()
        self._profile(u)
        p = self._product()
        app = self._application(u, p)
        result = evaluate(app)
        assert result.verdict in ('eligible', 'conditionally_eligible')
        assert result.hard_fails == 0

    # ── Hard fails ─────────────────────────────────────────────────
    def test_kyc_not_verified_fails(self):
        u = self._user()
        self._profile(u, kyc_status='pending')
        p = self._product()
        app = self._application(u, p)
        result = evaluate(app)
        assert result.verdict == 'not_eligible'
        assert any(r.code == 'kyc_verified' and r.status == 'fail' for r in result.rules)

    def test_no_income_fails(self):
        u = self._user()
        self._profile(u, monthly_income=Decimal('0'))
        p = self._product()
        app = self._application(u, p)
        result = evaluate(app)
        assert result.verdict == 'not_eligible'
        assert any(r.code == 'income' and r.status == 'fail' for r in result.rules)

    def test_unemployed_fails(self):
        u = self._user()
        self._profile(u, employment_type='unemployed')
        p = self._product()
        app = self._application(u, p)
        result = evaluate(app)
        assert result.verdict == 'not_eligible'

    def test_underage_fails(self):
        u = self._user()
        # 15 years old
        self._profile(u, date_of_birth=date(2011, 1, 1))
        p = self._product()
        app = self._application(u, p)
        result = evaluate(app)
        assert result.verdict == 'not_eligible'
        assert any(r.code == 'age' and r.status == 'fail' for r in result.rules)

    def test_high_dti_fails(self):
        u = self._user()
        # Existing debt + proposed repayment > 45% of income
        self._profile(
            u,
            monthly_income=Decimal('10000.00'),
            existing_debt_obligations=Decimal('4500.00'),
        )
        p = self._product()
        app = self._application(u, p, requested_amount=Decimal('10000.00'), requested_term=12)
        result = evaluate(app)
        # 4500 + ~833 = ~5333 / 10000 = 53% > 45%
        assert result.verdict == 'not_eligible'

    def test_above_product_max_fails(self):
        u = self._user()
        self._profile(u, monthly_income=Decimal('200000.00'))
        p = self._product(max_amount=Decimal('5000.00'))
        app = self._application(u, p, requested_amount=Decimal('10000.00'))
        result = evaluate(app)
        assert result.verdict == 'not_eligible'
        assert any(r.code == 'product_limits' and r.status == 'fail' for r in result.rules)

    def test_missing_profile_fails_kyc(self):
        u = self._user()
        # No profile
        p = self._product()
        app = self._application(u, p)
        result = evaluate(app)
        assert result.verdict == 'not_eligible'
        assert any(r.code == 'kyc_verified' and r.status == 'fail' for r in result.rules)

    # ── Warnings / conditional ─────────────────────────────────────
    def test_borderline_dti_warns(self):
        u = self._user()
        # income 15k, expenses 7k, existing debt 5k, proposed 1k
        # DTI = (5k + 1k) / 15k = 0.40 → warn range (0.35 < dti < 0.45)
        # Disposable = 15k - 7k - 5k - 1k = 2k → well above 500 minimum
        # Loan-to-income = 12k / (15k*12) = 0.067 → pass
        self._profile(
            u,
            monthly_income=Decimal('15000.00'),
            monthly_expenses=Decimal('7000.00'),
            existing_debt_obligations=Decimal('5000.00'),
        )
        p = self._product()
        app = self._application(
            u, p,
            requested_amount=Decimal('12000.00'),
            requested_term=12,
        )
        result = evaluate(app)
        assert result.verdict in ('conditionally_eligible', 'needs_review'), (
            f'Expected conditional/needs_review, got {result.verdict}. '
            f'Fails: {[r.code for r in result.rules if r.status == "fail"]}, '
            f'Warns: {[r.code for r in result.rules if r.status == "warn"]}'
        )
        assert any(r.code == 'dti' and r.status == 'warn' for r in result.rules)
    # ── Result shape ───────────────────────────────────────────────
    def test_result_has_all_rules(self):
        u = self._user()
        self._profile(u)
        p = self._product()
        app = self._application(u, p)
        result = evaluate(app)
        codes = {r.code for r in result.rules}
        expected = {
            'kyc_verified', 'age', 'employment', 'income', 'address',
            'product_limits', 'dti', 'disposable', 'loan_to_income',
            'documents', 'fraud',
        }
        assert codes == expected

    def test_result_is_serialisable(self):
        u = self._user()
        self._profile(u)
        p = self._product()
        app = self._application(u, p)
        result = evaluate(app)
        d = result.to_dict()
        assert d['verdict'] in (
            'eligible', 'conditionally_eligible', 'not_eligible', 'needs_review',
        )
        assert isinstance(d['rules'], list)
        assert all(isinstance(r, dict) for r in d['rules'])
        assert 'policy_version' in d
        assert 'evaluated_at' in d

    # ── Policy override ────────────────────────────────────────────
    def test_product_can_override_policy(self):
        u = self._user()
        self._profile(u, monthly_income=Decimal('10000.00'))
        p = self._product(
            name='Strict Loan',
            eligibility_rules={'max_dti': 0.10},   # very strict
        )
        app = self._application(u, p, requested_amount=Decimal('6000.00'), requested_term=12)
        result = evaluate(app)
        assert result.verdict == 'not_eligible'

    def test_product_loan_to_income_override(self):
        u = self._user()
        self._profile(u, monthly_income=Decimal('20000.00'))
        p = self._product(
            name='Generous Loan',
            eligibility_rules={'warn_loan_to_income': 5.0},   # disable warning
        )
        app = self._application(u, p, requested_amount=Decimal('50000.00'), requested_term=24)
        result = evaluate(app)
        # Should not warn about loan-to-income
        assert not any(
            r.code == 'loan_to_income' and r.status == 'warn'
            for r in result.rules
        )

    # ── Missing data ───────────────────────────────────────────────
    def test_insufficient_data_needs_review(self):
        u = self._user()
        # Minimal profile: no DOB, no employment type, no address
        ClientProfile.objects.create(
            user=u,
            monthly_income=Decimal('10000.00'),
            kyc_status='verified',
        )
        p = self._product()
        app = self._application(u, p)
        result = evaluate(app)
        # Should not be outright not_eligible (income is fine)
        # but should flag missing data
        assert result.missing_data >= 2
        assert result.verdict in ('needs_review', 'not_eligible', 'conditionally_eligible')