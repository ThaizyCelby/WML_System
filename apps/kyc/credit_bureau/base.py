"""Credit bureau provider interface.

Real integrations require:
  * NCR credit-provider registration
  * A commercial contract with the bureau (TransUnion / Experian / XDS / Compuscan / CPB)
  * A permissible purpose under section 70(2) of the NCA
  * POPIA-compliant consent from the data subject

This module defines the interface and a mock adapter. Real adapters must be
enabled once the credentials and legal agreements are in place.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


class CreditBureauError(Exception):
    """Raised when a credit bureau call fails."""


class CreditBureauConsentRequired(CreditBureauError):
    """Raised when the client has not given consent to be checked."""


@dataclass
class TradeLine:
    """A single credit account returned by the bureau."""
    creditor_name: str
    account_type: str                 # e.g. 'credit_card', 'personal_loan', 'retail'
    account_number_masked: str
    monthly_installment: float
    outstanding_balance: float
    original_amount: Optional[float]
    opened_date: Optional[str]        # ISO
    status: str                       # 'current', 'delinquent', 'default', 'closed'
    arrears_amount: float = 0.0
    months_in_arrears: int = 0
    is_secured: bool = False
    raw: dict = field(default_factory=dict)


@dataclass
class CreditReport:
    """Normalized credit report from a bureau."""
    id_number: str
    bureau: str
    score: Optional[int]              # 0–850 depending on bureau
    risk_band: Optional[str]
    trade_lines: list[TradeLine]
    total_monthly_obligations: float  # sum of instalments on active tradelines
    total_outstanding_debt: float
    worst_arrears_months: int
    has_defaults: bool
    has_judgments: bool
    raw_response: dict = field(default_factory=dict)


class CreditBureauProvider(ABC):
    """Interface every credit-bureau adapter must implement."""

    name: str = 'base'

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if credentials are present."""

    @abstractmethod
    def pull_report(self, *, id_number: str, first_name: str, last_name: str) -> CreditReport:
        """
        Pull a credit report for a natural person.

        Requires a valid consent record on file — enforced by the caller.
        """