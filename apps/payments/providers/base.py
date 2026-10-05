"""Payment provider interface and shared exceptions."""
from abc import ABC, abstractmethod
from typing import Any, Dict, List



class PaymentProviderError(Exception):
    """Raised when a payment provider call fails."""
    pass


class PaymentProvider(ABC):
    """Abstract interface for all payment providers."""

    @abstractmethod
    def create_debit_instruction(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a debit-order mandate/instruction at the provider."""

    @abstractmethod
    def update_debit_instruction(self, instruction_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing debit instruction."""

    @abstractmethod
    def cancel_debit_instruction(self, instruction_id: str) -> Dict[str, Any]:
        """Cancel a debit instruction."""

    @abstractmethod
    def submit_payment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Submit a collection against an existing instruction."""

    @abstractmethod
    def get_payment_status(self, provider_transaction_id: str) -> Dict[str, Any]:
        """Get the current status of a payment."""

    @abstractmethod
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify the signature on an incoming webhook."""

    @abstractmethod
    def handle_webhook(self, payload: Dict[str, Any], signature: str) -> Dict[str, Any]:
        """Normalize an incoming webhook into a standard event dict."""

    @abstractmethod
    def reconcile_transactions(
        self,
        expected: List[Dict[str, Any]],
        actual: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Match expected payments with actual provider transactions."""
