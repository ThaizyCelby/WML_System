"""Mock payment provider for development and testing."""
import hashlib
import hmac
import time
from typing import Dict, Any, List
from decimal import Decimal

from .base import PaymentProvider


class MockPaymentProvider(PaymentProvider):
    """Mock provider for development and testing."""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.secret = self.config.get('secret', 'mock-secret')
        self.in_memory_store = {}

    def _generate_provider_transaction_id(self) -> str:
        return f"MOCK-{int(time.time() * 1000)}"

    def create_debit_instruction(self, instruction_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'provider_reference': self._generate_provider_transaction_id(),
            'status': 'active',
        }

    def update_debit_instruction(self, instruction_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        return {'status': 'updated', 'provider_reference': instruction_id}

    def cancel_debit_instruction(self, instruction_id: str) -> Dict[str, Any]:
        return {'status': 'cancelled'}

    def submit_payment(self, payment_data: Dict[str, Any]) -> Dict[str, Any]:
        tx_id = self._generate_provider_transaction_id()
        self.in_memory_store[tx_id] = {
            'amount': str(payment_data.get('amount', '0.00')),
            'status': 'successful',
        }
        return {
            'provider_transaction_id': tx_id,
            'status': 'successful',
        }

    def get_payment_status(self, provider_transaction_id: str) -> Dict[str, Any]:
        if provider_transaction_id in self.in_memory_store:
            return self.in_memory_store[provider_transaction_id]
        return {'status': 'unknown'}

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        # In development, accept any signature (except literally 'bad' used in tests)
        return signature != 'bad'

    def handle_webhook(self, payload: Dict[str, Any], signature: str) -> Dict[str, Any]:
        """Normalize webhook payload like the NuPay adapter does."""
        return {
            'event_type': payload.get('event') or payload.get('type', 'unknown'),
            'provider_event_id': payload.get('eventId') or payload.get('id'),
            'provider_transaction_id': (
                payload.get('transactionId')
                or (payload.get('data') or {}).get('transactionId')
            ),
            'status': self._map_status(
                payload.get('status') or (payload.get('data') or {}).get('status', '')
            ),
            'amount': payload.get('amount') or (payload.get('data') or {}).get('amount'),
            'raw': payload,
        }

    def reconcile_transactions(
        self,
        expected: List[Dict[str, Any]],
        actual: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Simple matching by provider_transaction_id, falling back to amount."""
        actual_copy = list(actual)
        results = []
        for exp in expected:
            match = None
            if exp.get('provider_transaction_id'):
                match = next(
                    (a for a in actual_copy
                     if a.get('provider_transaction_id') == exp['provider_transaction_id']),
                    None,
                )
            if not match:
                match = next(
                    (a for a in actual_copy if str(a.get('amount')) == str(exp.get('amount'))),
                    None,
                )
            if match:
                actual_copy.remove(match)
                results.append({'expected': exp, 'actual': match, 'status': 'matched'})
            else:
                results.append({'expected': exp, 'actual': None, 'status': 'missing'})
        for a in actual_copy:
            results.append({'expected': None, 'actual': a, 'status': 'unmatched'})
        return results

    @staticmethod
    def _map_status(s: str) -> str:
        s = (s or '').lower()
        return {
            'paid': 'successful', 'successful': 'successful', 'settled': 'successful',
            'failed': 'failed', 'declined': 'failed', 'rejected': 'failed',
            'reversed': 'reversed', 'refunded': 'reversed',
            'pending': 'pending', 'processing': 'processing', 'accepted': 'processing',
            'cancelled': 'cancelled',
        }.get(s, 'pending')
