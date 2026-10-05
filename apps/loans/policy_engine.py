"""
Deterministic lending policy engine.

Pure function. Given an application + profile, returns a structured result
with rule-by-rule evidence. No AI, no external calls, no DB writes beyond
reading the models passed in.

Verdicts:
    eligible                — all hard rules pass
    conditionally_eligible  — soft warnings but no hard fails
    needs_review            — data missing or ambiguous; human must decide
    not_eligible            — one or more hard rules fail

Every rule returns:
    code, label, status (pass|warn|fail|skip|info), detail, evidence

Caller decides what to do with the result. This module never raises for
business-rule reasons; it only raises ValueError if given invalid input.
"""
from dataclasses import dataclass, field, asdict
from datetime import date
from decimal import Decimal
from typing import Optional

from django.utils import timezone


# ──────────────────────────────────────────────────────────────────────
# Default policy (can be overridden per product via product.eligibility_rules)
# ──────────────────────────────────────────────────────────────────────
DEFAULT_POLICY = {
    'version': '1.0',

    # Hard gates (any fail => not_eligible)
    'require_kyc_verified': True,
    'require_employment': True,           # not unemployed
    'require_income_verified': True,      # monthly_income > 0
    'min_age': 18,
    'min_employment_months': 3,
    'max_dti': Decimal('0.45'),           # debt-to-income
    'min_disposable_income': Decimal('500.00'),

    # Soft gates (fail/warn only adds warnings)
    'warn_dti': Decimal('0.35'),
    'warn_loan_to_income': Decimal('0.30'),   # loan / annual income
    'warn_missing_documents': True,

    # Data requirements (missing => needs_review, not fail)
    'require_dob': True,
    'require_employment_type': True,
    'require_address': True,
    'require_bank_statement': True,
}


# ──────────────────────────────────────────────────────────────────────
# Result dataclasses
# ──────────────────────────────────────────────────────────────────────
@dataclass
class RuleResult:
    code: str
    label: str
    status: str          # 'pass' | 'warn' | 'fail' | 'skip' | 'info'
    detail: str
    evidence: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


@dataclass
class PolicyResult:
    verdict: str         # 'eligible' | 'conditionally_eligible' | 'not_eligible' | 'needs_review'
    label: str
    summary: str
    rules: list
    hard_fails: int
    warnings: int
    missing_data: int
    policy_version: str
    evaluated_at: str

    def to_dict(self):
        d = asdict(self)
        d['rules'] = [r.to_dict() if hasattr(r, 'to_dict') else r for r in self.rules]
        return d


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────
def _dec(value) -> Decimal:
    if value is None:
        return Decimal('0')
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal('0')


def _merge_policy(product) -> dict:
    """Start with defaults; overlay per-product eligibility_rules."""
    policy = dict(DEFAULT_POLICY)
    if product and isinstance(getattr(product, 'eligibility_rules', None), dict):
        for k, v in product.eligibility_rules.items():
            if k in policy:
                # Coerce numeric overrides back to Decimal where the default is Decimal
                if isinstance(policy[k], Decimal) and not isinstance(v, Decimal):
                    try:
                        v = Decimal(str(v))
                    except Exception:
                        continue
                policy[k] = v
    return policy


# ──────────────────────────────────────────────────────────────────────
# Individual rules
# ──────────────────────────────────────────────────────────────────────
def _rule_kyc(profile, policy) -> RuleResult:
    if not profile:
        return RuleResult(
            'kyc_verified', 'KYC verified', 'fail',
            'No client profile on file.',
        )
    status = getattr(profile, 'kyc_status', 'pending')
    if status == 'verified':
        return RuleResult(
            'kyc_verified', 'KYC verified', 'pass',
            'Client KYC is verified.',
            {'kyc_status': status},
        )
    if not policy['require_kyc_verified']:
        return RuleResult(
            'kyc_verified', 'KYC verified', 'info',
            f'KYC is "{status}" but not required by policy.',
            {'kyc_status': status},
        )
    return RuleResult(
        'kyc_verified', 'KYC verified', 'fail',
        f'KYC status is "{status}" — must be verified.',
        {'kyc_status': status},
    )


def _rule_age(profile, policy) -> RuleResult:
    dob = getattr(profile, 'date_of_birth', None) if profile else None
    if not dob:
        if policy['require_dob']:
            return RuleResult(
                'age', 'Age', 'info',
                'Date of birth not on file.',
            )
        return RuleResult('age', 'Age', 'skip', 'Date of birth not required.')

    today = date.today()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if age < policy['min_age']:
        return RuleResult(
            'age', 'Age', 'fail',
            f'Client is {age}; minimum is {policy["min_age"]}.',
            {'age': age, 'min_age': policy['min_age']},
        )
    return RuleResult(
        'age', 'Age', 'pass',
        f'Client is {age}.',
        {'age': age},
    )


def _rule_employment(profile, policy) -> RuleResult:
    if not profile:
        return RuleResult('employment', 'Employment', 'info', 'No profile on file.')
    emp_type = getattr(profile, 'employment_type', '') or ''
    start = getattr(profile, 'employment_start_date', None)

    if not emp_type:
        if policy['require_employment_type']:
            return RuleResult(
                'employment', 'Employment', 'info',
                'Employment type not recorded.',
            )
        return RuleResult('employment', 'Employment', 'skip', 'Employment not required.')

    if emp_type == 'unemployed':
        return RuleResult(
            'employment', 'Employment', 'fail',
            'Client is recorded as unemployed.',
            {'employment_type': emp_type},
        )

    if start:
        months = (date.today().year - start.year) * 12 + (date.today().month - start.month)
        if months < policy['min_employment_months']:
            return RuleResult(
                'employment', 'Employment', 'warn',
                f'Employment duration {months} months; policy suggests {policy["min_employment_months"]}+.',
                {'months': months, 'min_months': policy['min_employment_months']},
            )
        return RuleResult(
            'employment', 'Employment', 'pass',
            f'{emp_type.replace("_", " ").title()} · {months} months.',
            {'employment_type': emp_type, 'months': months},
        )

    return RuleResult(
        'employment', 'Employment', 'pass',
        f'{emp_type.replace("_", " ").title()}.',
        {'employment_type': emp_type},
    )


def _rule_income(profile, policy) -> RuleResult:
    income = _dec(getattr(profile, 'monthly_income', 0)) if profile else Decimal('0')
    if income <= 0:
        if policy['require_income_verified']:
            return RuleResult(
                'income', 'Verified income', 'fail',
                'No monthly income on file.',
                {'monthly_income': str(income)},
            )
        return RuleResult(
            'income', 'Verified income', 'warn',
            'No income recorded.',
        )
    return RuleResult(
        'income', 'Verified income', 'pass',
        f'Monthly income R{income:,.2f}.',
        {'monthly_income': str(income)},
    )


def _rule_dti(profile, proposed_repayment, policy) -> RuleResult:
    income = _dec(getattr(profile, 'monthly_income', 0)) if profile else Decimal('0')
    existing_debt = _dec(getattr(profile, 'existing_debt_obligations', 0)) if profile else Decimal('0')

    if income <= 0:
        return RuleResult(
            'dti', 'Debt-to-income', 'info',
            'Cannot compute DTI — no income on file.',
        )

    total_debt = existing_debt + proposed_repayment
    dti = (total_debt / income).quantize(Decimal('0.01'))
    evidence = {
        'monthly_income': str(income),
        'existing_debt': str(existing_debt),
        'proposed_repayment': str(proposed_repayment),
        'dti': str(dti),
    }

    if dti > policy['max_dti']:
        return RuleResult(
            'dti', 'Debt-to-income', 'fail',
            f'DTI {dti:.0%} exceeds maximum {policy["max_dti"]:.0%}.',
            evidence,
        )
    if dti > policy['warn_dti']:
        return RuleResult(
            'dti', 'Debt-to-income', 'warn',
            f'DTI {dti:.0%} is above the comfortable {policy["warn_dti"]:.0%} threshold.',
            evidence,
        )
    return RuleResult(
        'dti', 'Debt-to-income', 'pass',
        f'DTI {dti:.0%}.',
        evidence,
    )


def _rule_disposable(profile, proposed_repayment, policy) -> RuleResult:
    income = _dec(getattr(profile, 'monthly_income', 0)) if profile else Decimal('0')
    expenses = _dec(getattr(profile, 'monthly_expenses', 0)) if profile else Decimal('0')
    existing_debt = _dec(getattr(profile, 'existing_debt_obligations', 0)) if profile else Decimal('0')

    if income <= 0:
        return RuleResult(
            'disposable', 'Disposable income', 'info',
            'Cannot compute disposable income — no income on file.',
        )

    disposable = income - expenses - existing_debt - proposed_repayment
    evidence = {
        'income': str(income),
        'expenses': str(expenses),
        'existing_debt': str(existing_debt),
        'proposed_repayment': str(proposed_repayment),
        'disposable': str(disposable),
    }

    if disposable < policy['min_disposable_income']:
        return RuleResult(
            'disposable', 'Disposable income', 'fail',
            f'Disposable income R{disposable:,.2f} is below the R{policy["min_disposable_income"]:,.2f} minimum.',
            evidence,
        )
    return RuleResult(
        'disposable', 'Disposable income', 'pass',
        f'Disposable income R{disposable:,.2f} after proposed repayment.',
        evidence,
    )


def _rule_loan_to_income(application, profile, policy) -> RuleResult:
    income = _dec(getattr(profile, 'monthly_income', 0)) if profile else Decimal('0')
    requested = _dec(application.requested_amount)
    if income <= 0 or requested <= 0:
        return RuleResult(
            'loan_to_income', 'Loan-to-income', 'info',
            'Cannot compute loan-to-income.',
        )

    annual_income = income * 12
    ratio = (requested / annual_income).quantize(Decimal('0.01'))
    evidence = {
        'requested_amount': str(requested),
        'annual_income': str(annual_income),
        'ratio': str(ratio),
    }

    if ratio > policy['warn_loan_to_income']:
        return RuleResult(
            'loan_to_income', 'Loan-to-income', 'warn',
            f'Requested loan is {ratio:.0%} of annual income.',
            evidence,
        )
    return RuleResult(
        'loan_to_income', 'Loan-to-income', 'pass',
        f'{ratio:.0%} of annual income.',
        evidence,
    )


def _rule_product_limits(application, product) -> RuleResult:
    if not product:
        return RuleResult(
            'product_limits', 'Within product limits', 'fail',
            'Application has no loan product.',
        )
    amount = _dec(application.requested_amount)
    term = application.requested_term or 0

    if amount < product.min_amount:
        return RuleResult(
            'product_limits', 'Within product limits', 'fail',
            f'Requested R{amount:,.2f} below minimum R{product.min_amount:,.2f}.',
        )
    if amount > product.max_amount:
        return RuleResult(
            'product_limits', 'Within product limits', 'fail',
            f'Requested R{amount:,.2f} above maximum R{product.max_amount:,.2f}.',
        )
    if term < product.min_term:
        return RuleResult(
            'product_limits', 'Within product limits', 'fail',
            f'Term {term} below minimum {product.min_term}.',
        )
    if term > product.max_term:
        return RuleResult(
            'product_limits', 'Within product limits', 'fail',
            f'Term {term} above maximum {product.max_term}.',
        )
    return RuleResult(
        'product_limits', 'Within product limits', 'pass',
        f'R{amount:,.2f} over {term} months fits {product.name}.',
        {'amount': str(amount), 'term': term},
    )


def _rule_documents(application, policy) -> RuleResult:
    from apps.documents.models import Document
    client = application.client
    docs = Document.objects.filter(client=client)
    total = docs.count()
    approved = docs.filter(status='approved').count()
    pending = docs.filter(status='submitted').count()
    rejected = docs.filter(status='rejected').count()

    evidence = {
        'total': total,
        'approved': approved,
        'pending': pending,
        'rejected': rejected,
    }

    if total == 0:
        return RuleResult(
            'documents', 'Documents', 'warn',
            'No documents uploaded.',
            evidence,
        )
    if rejected > 0:
        return RuleResult(
            'documents', 'Documents', 'warn',
            f'{rejected} document(s) rejected — needs resubmission.',
            evidence,
        )
    if pending > 0:
        return RuleResult(
            'documents', 'Documents', 'info',
            f'{pending} document(s) awaiting review.',
            evidence,
        )
    if approved == total:
        return RuleResult(
            'documents', 'Documents', 'pass',
            f'All {total} document(s) approved.',
            evidence,
        )
    return RuleResult(
        'documents', 'Documents', 'info',
        f'{approved} of {total} documents approved.',
        evidence,
    )


def _rule_fraud(application) -> RuleResult:
    try:
        from apps.security.models import FraudAlert
    except Exception:
        return RuleResult('fraud', 'Fraud check', 'skip', 'Fraud module unavailable.')

    alerts = FraudAlert.objects.filter(
        user_id=application.client_id,
        severity__in=['high', 'critical'],
        status__in=['open', 'investigating'],
    )
    count = alerts.count()
    if count > 0:
        return RuleResult(
            'fraud', 'Fraud check', 'fail',
            f'{count} high-severity fraud alert(s) open.',
            {'count': count},
        )
    return RuleResult('fraud', 'Fraud check', 'pass', 'No open high-severity alerts.')


def _rule_address(profile, policy) -> RuleResult:
    addr = getattr(profile, 'residential_address', None) if profile else None
    if not addr:
        if policy['require_address']:
            return RuleResult('address', 'Residential address', 'info', 'Address not on file.')
        return RuleResult('address', 'Residential address', 'skip', 'Address not required.')
    if isinstance(addr, dict):
        street = addr.get('street') or addr.get('line1') or ''
        city = addr.get('city') or addr.get('suburb') or ''
        if street and city:
            return RuleResult(
                'address', 'Residential address', 'pass',
                f'{street}, {city}'.strip(', '),
            )
    return RuleResult(
        'address', 'Residential address', 'warn',
        'Address on file is incomplete.',
        {'raw': str(addr)[:120]},
    )


# ──────────────────────────────────────────────────────────────────────
# Orchestrator
# ──────────────────────────────────────────────────────────────────────
def evaluate(application, profile=None, proposed_repayment: Optional[Decimal] = None) -> PolicyResult:
    """
    Evaluate a loan application against deterministic policy.

    `proposed_repayment` defaults to application.requested_amount / term
    (rough estimate). The staff view can pass a more accurate figure if it
    has already computed the repayment schedule.
    """
    if profile is None:
        try:
            profile = application.client.client_profile
        except Exception:
            profile = None

    product = application.product
    policy = _merge_policy(product)

    if proposed_repayment is None:
        term = application.requested_term or 1
        proposed_repayment = (_dec(application.requested_amount) / Decimal(term)).quantize(Decimal('0.01'))

    rules = [
        _rule_kyc(profile, policy),
        _rule_age(profile, policy),
        _rule_employment(profile, policy),
        _rule_income(profile, policy),
        _rule_address(profile, policy),
        _rule_product_limits(application, product),
        _rule_dti(profile, proposed_repayment, policy),
        _rule_disposable(profile, proposed_repayment, policy),
        _rule_loan_to_income(application, profile, policy),
        _rule_documents(application, policy),
        _rule_fraud(application),
    ]

    hard_fails = sum(1 for r in rules if r.status == 'fail')
    warnings = sum(1 for r in rules if r.status == 'warn')
    missing_data = sum(1 for r in rules if r.status == 'info')

    # Verdict logic
    if hard_fails > 0:
        verdict = 'not_eligible'
        label = 'Not eligible'
        summary = (
            f'{hard_fails} hard rule(s) failed. '
            'Human override is possible with a recorded reason.'
        )
    elif missing_data >= 3 and warnings == 0:
        verdict = 'needs_review'
        label = 'Needs review'
        summary = (
            f'{missing_data} data point(s) missing. '
            'Collect the missing information before deciding.'
        )
    elif warnings > 0:
        verdict = 'conditionally_eligible'
        label = 'Conditionally eligible'
        summary = (
            f'{warnings} warning(s). Product terms may need adjusting '
            'or additional conditions applied.'
        )
    else:
        verdict = 'eligible'
        label = 'Eligible'
        summary = 'All rules pass. Proceed with standard approval flow.'

    return PolicyResult(
        verdict=verdict,
        label=label,
        summary=summary,
        rules=rules,
        hard_fails=hard_fails,
        warnings=warnings,
        missing_data=missing_data,
        policy_version=policy['version'],
        evaluated_at=timezone.now().isoformat(),
    )