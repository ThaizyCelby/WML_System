"""
NuPay payment provider adapter.

IMPORTANT — NuPay API integration:
This adapter is written against the documented public interface pattern.
All endpoint paths and payload keys are placeholders that MUST be replaced
with the actual values from NuPay's official developer documentation and
sandbox credentials before going live.

Configuration via .env:
    NUPAY_ENDPOINT
    NUPAY_API_KEY
    NUPAY_API_SECRET
    NUPAY_MERCHANT_ID
    NUPAY_WEBHOOK_SECRET           # required in production
    NUPAY_WEBHOOK_TOLERANCE=300    # optional, seconds (default 300)
    NUPAY_SANDBOX=true|false
"""
import hashlib
import hmac
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests

from .base import PaymentProvider, PaymentProviderError

logger = logging.getLogger('apps.payments')


class NuPayProvider(PaymentProvider):
    """
    Real NuPay adapter. Uses the same interface as MockPaymentProvider so it
    can be swapped by changing the .env setting `PAYMENT_PROVIDER=nupay`.
    """

    def __init__(self, config: dict):
        self.config = config or {}
        self.base_url = (self.config.get('endpoint') or '').rstrip('/')
        self.api_key = self.config.get('api_key') or ''
        self.api_secret = self.config.get('api_secret') or ''
        self.merchant_id = self.config.get('merchant_id') or ''
        self.webhook_secret = self.config.get('webhook_secret') or ''
        self.timeout = self.config.get('timeout_seconds', 30)
        self.retry_count = self.config.get('retry_count', 3)
        # Replay protection window (seconds). Payloads older or newer than
        # this window are rejected. Default 5 minutes.
        self.webhook_tolerance_seconds = int(
            self.config.get('webhook_tolerance_seconds', 300)
        )

        # ------------------------------------------------------------------
        # Production fail-fast checks
        #
        # SECURITY: In production, we must NOT boot if required secrets are
        # missing. A silently misconfigured payment provider is worse than a
        # loud startup failure — forged webhooks could be accepted.
        #
        # In development (DEBUG=True) we allow a missing webhook secret so
        # local work does not require real credentials. At webhook time,
        # verify_webhook_signature() will still fail-closed if the secret is
        # empty.
        # ------------------------------------------------------------------
        if not self.base_url or not self.api_key:
            raise PaymentProviderError(
                "NuPay is not fully configured: NUPAY_ENDPOINT and "
                "NUPAY_API_KEY are required."
            )

        from django.conf import settings as django_settings
        if not django_settings.DEBUG and not self.webhook_secret:
            raise PaymentProviderError(
                "NUPAY_WEBHOOK_SECRET is required in production. "
                "Refusing to start with an unverifiable webhook endpoint."
            )

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "X-Merchant-Id": self.merchant_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(self, method: str, path: str, json=None, params=None):
        url = f"{self.base_url}{path}"
        last = None
        for attempt in range(1, self.retry_count + 1):
            try:
                resp = requests.request(
                    method, url, headers=self._headers(),
                    json=json, params=params, timeout=self.timeout,
                )
                if resp.status_code >= 500 or resp.status_code == 429:
                    raise PaymentProviderError(
                        f"HTTP {resp.status_code}: {resp.text[:200]}"
                    )
                return resp
            except (requests.Timeout, requests.ConnectionError, PaymentProviderError) as e:
                last = e
                time.sleep(min(2 ** attempt, 8))
        raise PaymentProviderError(f"All retries failed: {last}")

    # ------------------------------------------------------------------
    # Provider interface — debit instructions
    # ------------------------------------------------------------------
    def create_debit_instruction(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a debit-order mandate with NuPay.

        Replace the path and payload keys with the real NuPay spec once you
        have the signed agreement and sandbox documentation.
        """
        payload = {
            "merchantId": self.merchant_id,
            "reference": str(data.get("loan_id")),
            "accountHolder": data.get("account_holder_name"),
            "accountNumber": data.get("account_number"),
            "bankName": data.get("bank_name"),
            "branchCode": data.get("branch_code", ""),
            "accountType": data.get("account_type", "cheque"),
        }
        resp = self._request("POST", "/v1/debit-instructions", json=payload)
        if resp.status_code not in (200, 201):
            raise PaymentProviderError(
                f"create_debit_instruction failed: {resp.text[:300]}"
            )
        body = resp.json()
        return {
            "provider_reference": body.get("reference") or body.get("mandateId"),
            "status": body.get("status", "active"),
            "raw": body,
        }

    def update_debit_instruction(
        self, instruction_id: str, updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        resp = self._request(
            "PATCH", f"/v1/debit-instructions/{instruction_id}", json=updates,
        )
        return resp.json()

    def cancel_debit_instruction(self, instruction_id: str) -> Dict[str, Any]:
        resp = self._request(
            "POST", f"/v1/debit-instructions/{instruction_id}/cancel",
        )
        return resp.json()

    # ------------------------------------------------------------------
    # Provider interface — payments
    # ------------------------------------------------------------------
    def submit_payment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Submit a single collection against an existing instruction."""
        payload = {
            "merchantId": self.merchant_id,
            "reference": data.get("reference"),
            "amount": str(data.get("amount")),
            "currency": "ZAR",
            "instructionReference": data.get("instruction_reference"),
            "idempotencyKey": data.get("idempotency_key"),
        }
        resp = self._request("POST", "/v1/payments/collect", json=payload)
        if resp.status_code not in (200, 201, 202):
            raise PaymentProviderError(
                f"submit_payment failed: {resp.text[:300]}"
            )
        body = resp.json()
        return {
            "provider_transaction_id": body.get("transactionId"),
            "status": self._map_status(body.get("status", "pending")),
            "raw": body,
        }

    def get_payment_status(self, provider_transaction_id: str) -> Dict[str, Any]:
        resp = self._request("GET", f"/v1/payments/{provider_transaction_id}")
        if resp.status_code != 200:
            raise PaymentProviderError(
                f"get_payment_status failed: {resp.text[:200]}"
            )
        body = resp.json()
        return {"status": self._map_status(body.get("status")), "raw": body}

    # ------------------------------------------------------------------
    # Webhook verification
    # ------------------------------------------------------------------
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        HMAC-SHA256 of the raw body using the webhook secret.

        SECURITY: If no webhook secret is configured we MUST reject all
        webhooks — otherwise a forged payload would be accepted.
        """
        if not self.webhook_secret:
            logger.error(
                "NuPay webhook received but NUPAY_WEBHOOK_SECRET is not "
                "configured. Rejecting webhook."
            )
            return False
        if not signature:
            return False
        expected = hmac.new(
            self.webhook_secret.encode('utf-8'), payload, hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def _check_replay(self, payload: Dict[str, Any]) -> bool:
        """
        Reject webhooks whose timestamp is outside the tolerance window.

        Returns True if the payload is acceptable (fresh, or has no
        timestamp). Returns False if the timestamp is too old or too far
        in the future.

        If the provider does not include a timestamp, we cannot enforce
        replay protection and we allow the webhook through — the HMAC
        signature is still the primary defense.
        """
        ts = payload.get('timestamp')
        if ts is None:
            return True

        # Accept both Unix epoch seconds and ISO-8601 strings.
        try:
            if isinstance(ts, (int, float)):
                payload_time = float(ts)
            elif isinstance(ts, str):
                # Try ISO first
                try:
                    dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    payload_time = dt.timestamp()
                except ValueError:
                    # Fall back to epoch seconds
                    payload_time = float(ts)
            else:
                return True  # unknown type, allow
        except (ValueError, TypeError):
            return True  # unparseable, allow (signature is still checked)

        now = time.time()
        age = now - payload_time

        # Reject if too old (positive age > tolerance)
        if age > self.webhook_tolerance_seconds:
            logger.warning(
                "NuPay webhook rejected: timestamp too old (age=%.0fs, "
                "tolerance=%ds)",
                age, self.webhook_tolerance_seconds,
            )
            return False

        # Reject if too far in the future (negative age beyond tolerance)
        if age < -self.webhook_tolerance_seconds:
            logger.warning(
                "NuPay webhook rejected: timestamp too far in future "
                "(age=%.0fs, tolerance=%ds)",
                age, self.webhook_tolerance_seconds,
            )
            return False

        return True

    def handle_webhook(self, payload: Dict[str, Any], signature: str) -> Dict[str, Any]:
        """
        Return normalized event data. Signature already verified upstream
        by verify_webhook_signature().
        """
        return {
            "event_type": payload.get("event") or payload.get("type", "unknown"),
            "provider_event_id": payload.get("eventId") or payload.get("id"),
            "provider_transaction_id": (
                payload.get("transactionId")
                or payload.get("data", {}).get("transactionId")
            ),
            "status": self._map_status(
                payload.get("status")
                or payload.get("data", {}).get("status", "")
            ),
            "amount": (
                payload.get("amount")
                or payload.get("data", {}).get("amount")
            ),
            "raw": payload,
        }

    # ------------------------------------------------------------------
    # Reconciliation
    # ------------------------------------------------------------------
    def reconcile_transactions(
        self,
        expected: List[Dict[str, Any]],
        actual: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Simple matching by provider_transaction_id or amount."""
        actual_copy = list(actual)
        results = []
        for exp in expected:
            match = next(
                (a for a in actual_copy
                 if exp.get("provider_transaction_id")
                 and a.get("provider_transaction_id") == exp["provider_transaction_id"]),
                None,
            )
            if not match:
                match = next(
                    (a for a in actual_copy
                     if str(a.get("amount")) == str(exp.get("amount"))),
                    None,
                )
            if match:
                actual_copy.remove(match)
                results.append({
                    "expected": exp, "actual": match, "status": "matched",
                })
            else:
                results.append({
                    "expected": exp, "actual": None, "status": "missing",
                })
        for a in actual_copy:
            results.append({"expected": None, "actual": a, "status": "unmatched"})
        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
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