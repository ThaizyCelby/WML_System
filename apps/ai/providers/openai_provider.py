import json
import logging
from typing import Dict, Any, List

from .base import AIProvider, AIProviderError

logger = logging.getLogger('apps.ai')


class OpenAIProvider(AIProvider):
    BASE_URL = "https://api.openai.com/v1"

    def _chat(self, messages: list, max_tokens: int = 2000) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": float(self.config.get('temperature', 0.1)),
        }
        response = self._request_with_retry(
            "POST", f"{self.BASE_URL}/chat/completions",
            headers=headers, json=payload,
        )
        if response.status_code != 200:
            raise AIProviderError(f"OpenAI error {response.status_code}: {response.text[:200]}")
        data = response.json()
        return data['choices'][0]['message']['content'].strip()

    def _parse_json(self, content: str) -> Dict[str, Any]:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            start = content.find('{')
            end = content.rfind('}') + 1
            if start != -1 and end > start:
                try:
                    return json.loads(content[start:end])
                except json.JSONDecodeError:
                    pass
            return {"raw_analysis": content}

    def analyze_transactions(self, transactions, prompt_context=""):
        tx_json = json.dumps(transactions, default=str)
        messages = [
            {"role": "system", "content": (
                "You are a financial analyst. Analyze the following bank transactions "
                "and return STRICT JSON with keys: 'salary_detection', 'recurring_expenses', "
                "'unusual_transactions', 'monthly_income_estimate', 'monthly_expense_estimate'."
            )},
            {"role": "user", "content": f"Transactions: {tx_json}\n{prompt_context}"},
        ]
        return self._parse_json(self._chat(messages, max_tokens=3000))

    def detect_payday(self, transactions):
        tx_json = json.dumps(transactions, default=str)
        messages = [
            {"role": "system", "content": (
                "Detect salary transactions. Return STRICT JSON with keys: "
                "'detected_salary', 'salary_frequency', 'historical_paydays', "
                "'confidence', 'predicted_next_payday'."
            )},
            {"role": "user", "content": tx_json},
        ]
        return self._parse_json(self._chat(messages, max_tokens=1000))

    def detect_debt_obligations(self, transactions):
        tx_json = json.dumps(transactions, default=str)
        messages = [
            {"role": "system", "content": (
                "Detect debt obligations. Return STRICT JSON with 'creditors': list of "
                "{creditor_name, monthly_payment, frequency, last_payment_date, confidence}."
            )},
            {"role": "user", "content": tx_json},
        ]
        return self._parse_json(self._chat(messages, max_tokens=2000))

    def chat_completion(self, messages, max_tokens=1000):
        return self._chat(messages, max_tokens=max_tokens)
