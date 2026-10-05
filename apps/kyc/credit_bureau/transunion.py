"""TransUnion South Africa credit bureau adapter.

This adapter follows the documented TransUnion API pattern for the South
African market. Actual endpoint paths, authentication headers, and payload
keys MUST be taken from the current TransUnion developer documentation and
your merchant agreement. Do NOT invent endpoints.

Configuration via environment:
    TRANSUNION_ENABLED=true
    TRANSUNION_BASE_URL=https://api.transunion.co.za/...
    TRANSUNION_API_KEY=...
    TRANSUNION_API_SECRET=...
    TRANSUNION_MEMBER_CODE=...
    TRANSUNION_PRODUCT_CODE=...          # e.g. credit report product
    TRANSUNION_TIMEOUT=30
"""
import base64
import logging
from typing import Any

import requests

from .base import CreditBureauProvider, CreditBureauError, CreditReport, TradeLine

logger = logging.getLogger('apps.kyc.credit_bureau')


class TransUnionProvider(CreditBureauProvider):
    name = 'transunion'

    def __init__(self, config: dict):
        self.config = config or {}
        self.base_url = (self.config.get('base_url') or '').rstrip('/')
        self.api_key = self.config.get('api_key') or ''
        self.api_secret = self.config.get('api_secret') or ''
        self.member_code = self.config.get('member_code') or ''
        self.product_code = self.config.get('product_code') or ''
        self.timeout = self.config.get('timeout_seconds', 30)

    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.api_secret and self.member_code)

    def _auth_header(self) -> str:
        # Common pattern: HTTP Basic with key/secret; adjust to your agreement.
        raw = f"{self.api_key}:{self.api_secret}".encode()
        return 'Basic ' + base64.b64encode(raw).decode()

    def pull_report(self, *, id_number: str, first_name: str, last_name: str) -> CreditReport:
        if not self.is_configured():
            raise CreditBureauError('TransUnion is not configured.')

        # NOTE: endpoint + payload keys must match your TransUnion agreement.
        url = f"{self.base_url}/consumer/credit-report"
        headers = {
            'Authorization': self._auth_header(),
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-Member-Code': self.member_code,
        }
        payload = {
            'productCode': self.product_code,
            'consumer': {
                'idNumber': id_number,
                'firstName': first_name,
                'lastName': last_name,
            },
            'purpose': 'AFFORDABILITY_ASSESSMENT',   # NCA s.81 permissible purpose
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            resp.raise_for_status()
        except Exception as e:
            logger.exception('TransUnion pull failed: %s', e)
            raise CreditBureauError(str(e)) from e

        return self._normalize(resp.json(), id_number)

    def _normalize(self, raw: dict, id_number: str) -> CreditReport:
        """
        Map the TransUnion response to our normalized model.

        The exact keys depend on the TransUnion product version. Update this
        mapping to match the response you actually receive in sandbox.
        """
        tradelines = raw.get('tradeLines') or raw.get('accounts') or []
        trade_lines: list[TradeLine] = []
        for t in tradelines:
            status = (t.get('status') or '').lower()
            months_arrears = int(t.get('monthsInArrears') or 0)
            trade_lines.append(TradeLine(
                creditor_name=t.get('subscriberName') or t.get('creditorName') or '',
                account_type=(t.get('accountType') or '').lower(),
                account_number_masked=t.get('maskedAccountNumber') or '****',
                monthly_installment=float(t.get('installment') or 0),
                outstanding_balance=float(t.get('balance') or 0),
                original_amount=float(t.get('originalAmount')) if t.get('originalAmount') is not None else None,
                opened_date=t.get('openDate'),
                status='delinquent' if months_arrears > 0 else ('closed' if status == 'closed' else 'current'),
                arrears_amount=float(t.get('arrearsAmount') or 0),
                months_in_arrears=months_arrears,
                is_secured=bool(t.get('secured')),
                raw=t,
            ))

        active = [t for t in trade_lines if t.status != 'closed']
        return CreditReport(
            id_number=id_number,
            bureau='transunion',
            score=raw.get('score') or raw.get('creditScore'),
            risk_band=raw.get('riskBand'),
            trade_lines=trade_lines,
            total_monthly_obligations=sum(t.monthly_installment for t in active),
            total_outstanding_debt=sum(t.outstanding_balance for t in active),
            worst_arrears_months=max((t.months_in_arrears for t in trade_lines), default=0),
            has_defaults=bool(raw.get('hasDefaults')),
            has_judgments=bool(raw.get('hasJudgments')),
            raw_response=raw,
        )