import json
import logging
from typing import Dict, Any, List

from .base import AIProvider, AIProviderError

logger = logging.getLogger('apps.ai')


class GeminiProvider(AIProvider):
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def _generate(self, prompt: str, max_tokens: int = 2000) -> str:
        url = f"{self.BASE_URL}/models/{self.model}:generateContent"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": float(self.config.get('temperature', 0.05)),
                "maxOutputTokens": max_tokens,
            },
        }
        response = self._request_with_retry(
            "POST", url, headers=headers, json=payload,
            params={"key": self.api_key},
        )
        if response.status_code != 200:
            raise AIProviderError(f"Gemini error {response.status_code}: {response.text[:200]}")
        data = response.json()
        try:
            return data['candidates'][0]['content']['parts'][0]['text'].strip()
        except (KeyError, IndexError) as e:
            raise AIProviderError(f"Unexpected Gemini response: {e}")

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
        prompt = (
            "Analyze the following bank transactions and return STRICT JSON with keys: "
            "salary_detection, recurring_expenses, unusual_transactions, "
            f"monthly_income_estimate, monthly_expense_estimate.\nTransactions: {tx_json}\n{prompt_context}"
        )
        return self._parse_json(self._generate(prompt, max_tokens=3000))

    def detect_payday(self, transactions):
        tx_json = json.dumps(transactions, default=str)
        prompt = (
            "Detect salary transactions from bank transactions. Return STRICT JSON with keys: "
            "detected_salary, salary_frequency, historical_paydays, confidence, "
            f"predicted_next_payday.\nTransactions: {tx_json}"
        )
        return self._parse_json(self._generate(prompt, max_tokens=1000))

    def detect_debt_obligations(self, transactions):
        tx_json = json.dumps(transactions, default=str)
        prompt = (
            "Detect debt obligations. Return STRICT JSON with 'creditors' list. "
            f"\nTransactions: {tx_json}"
        )
        return self._parse_json(self._generate(prompt, max_tokens=2000))

    def chat_completion(self, messages, max_tokens=1000):
        prompt = "\n".join([m['content'] for m in messages])
        return self._generate(prompt, max_tokens=max_tokens)
