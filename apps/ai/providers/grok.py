"""xAI Grok provider — OpenAI-compatible chat completions interface.

Endpoint: https://api.x.ai/v1/chat/completions
Model: read from GROK_MODEL (env-driven).

Used as the platform's primary AI provider. GLM remains the fallback.
"""
import json
import logging
import re
from typing import Any, Dict, List

from .base import AIProvider, AIProviderError

logger = logging.getLogger('apps.ai')


class GrokProvider(AIProvider):
    DEFAULT_BASE_URL = 'https://api.x.ai/v1'

    def __init__(self, config: dict):
        super().__init__(config)
        self.BASE_URL = (
            self.config.get('base_url') or self.DEFAULT_BASE_URL
        ).rstrip('/')

    # ── HTTP layer ────────────────────────────────────────────────
    def _chat(self, messages: List[dict], max_tokens: int = 2000) -> str:
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        payload = {
            'model': self.model,
            'messages': messages,
            'max_tokens': max_tokens,
            'temperature': float(self.config.get('temperature', 0.1)),
        }

        response = self._request_with_retry(
            'POST', f'{self.BASE_URL}/chat/completions',
            headers=headers, json=payload,
        )

        if response.status_code != 200:
            raise AIProviderError(
                f'Grok error {response.status_code}: {response.text[:400]}'
            )

        try:
            data = response.json()
        except Exception as e:
            raise AIProviderError(
                f'Grok returned non-JSON: {response.text[:200]}'
            ) from e

        if 'error' in data:
            err = data['error']
            raise AIProviderError(
                f"Grok provider error: {str(err.get('message', err))[:300]}"
            )

        try:
            return data['choices'][0]['message']['content'].strip()
        except (KeyError, IndexError) as e:
            raise AIProviderError(
                f'Unexpected Grok response shape: keys={list(data.keys())}'
            ) from e

    def _parse_json(self, content: str) -> Dict[str, Any]:
        """Extract JSON from a Grok reply. Handles fenced markdown + prose."""
        if not content:
            return {'raw_analysis': ''}

        cleaned = re.sub(r'^```(?:json)?\s*', '', content.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r'\s*```$', '', cleaned, flags=re.MULTILINE)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        for opener, closer in (('{', '}'), ('[', ']')):
            start, end = cleaned.find(opener), cleaned.rfind(closer)
            if start != -1 and end > start:
                try:
                    parsed = json.loads(cleaned[start:end + 1])
                    return parsed if opener == '{' else {'items': parsed}
                except json.JSONDecodeError:
                    pass

        logger.warning('Grok did not return parseable JSON; raw kept.')
        return {'raw_analysis': content}

    # ── AIProvider interface ──────────────────────────────────────
    def analyze_transactions(self, transactions, prompt_context=""):
        tx_json = json.dumps(transactions, default=str)
        messages = [
            {'role': 'system', 'content': (
                'You are a financial analyst for a South African micro-lender. '
                'Analyse the provided bank transactions and return ONLY a single '
                'JSON object with these keys: salary_detection, '
                'recurring_expenses, unusual_transactions, '
                'monthly_income_estimate, monthly_expense_estimate. '
                'No markdown, no commentary. Use null for unknown fields.'
            )},
            {'role': 'user', 'content': f'Transactions: {tx_json}\n{prompt_context}'},
        ]
        return self._parse_json(self._chat(messages, max_tokens=3000))

    def detect_payday(self, transactions):
        tx_json = json.dumps(transactions, default=str)
        messages = [
            {'role': 'system', 'content': (
                'Detect salary transactions. Return ONLY a single JSON object '
                'with keys: detected_salary (bool), salary_frequency (string), '
                'historical_paydays (list of YYYY-MM-DD), confidence (0-1 float), '
                'predicted_next_payday (YYYY-MM-DD). No markdown.'
            )},
            {'role': 'user', 'content': tx_json},
        ]
        return self._parse_json(self._chat(messages, max_tokens=1000))

    def detect_debt_obligations(self, transactions):
        tx_json = json.dumps(transactions, default=str)
        messages = [
            {'role': 'system', 'content': (
                'Detect debt obligations. Return ONLY a single JSON object with '
                'key "creditors" (list of objects with creditor_name, '
                'monthly_payment, frequency, last_payment_date, confidence). '
                'No markdown.'
            )},
            {'role': 'user', 'content': tx_json},
        ]
        return self._parse_json(self._chat(messages, max_tokens=2000))

    def chat_completion(self, messages, max_tokens=1000):
        return self._chat(messages, max_tokens=max_tokens)