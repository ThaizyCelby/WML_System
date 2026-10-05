"""Base AI provider with retry, timeout, and circuit breaker support."""
import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

import requests

logger = logging.getLogger('apps.ai')


class AIProviderError(Exception):
    """Raised when an AI provider call fails after retries."""
    pass


class CircuitBreakerOpen(Exception):
    """Raised when the circuit breaker is open."""
    pass


class AIProvider(ABC):
    """Base class for all AI providers."""

    def __init__(self, config: dict):
        self.config = config or {}
        self.api_key = self.config.get('api_key', '')
        self.model = self.config.get('model', '')
        self.timeout = self.config.get('timeout_seconds', 45)
        self.retry_count = self.config.get('retry_count', 3)
        self.circuit_threshold = self.config.get('circuit_breaker_threshold', 5)
        # Simple in-process circuit breaker state
        self._failure_count = 0
        self._circuit_open_until = 0.0
        self._circuit_open_duration = 60  # seconds

    # â”€â”€ Abstract methods each provider must implement â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    @abstractmethod
    def analyze_transactions(self, transactions: List[Dict[str, Any]], prompt_context: str = "") -> Dict[str, Any]:
        pass

    @abstractmethod
    def detect_payday(self, transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def detect_debt_obligations(self, transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def chat_completion(self, messages: List[Dict[str, str]], max_tokens: int = 1000) -> str:
        pass

    # â”€â”€ Shared helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def get_model_name(self) -> str:
        return self.model

    def _check_circuit(self):
        if time.time() < self._circuit_open_until:
            remaining = int(self._circuit_open_until - time.time())
            raise CircuitBreakerOpen(f"Circuit open for {remaining}s")

    def _record_success(self):
        self._failure_count = 0

    def _record_failure(self):
        self._failure_count += 1
        if self._failure_count >= self.circuit_threshold:
            self._circuit_open_until = time.time() + self._circuit_open_duration
            logger.warning(
                "Circuit breaker opened for %s after %d failures",
                self.__class__.__name__, self._failure_count,
            )

    def _request_with_retry(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> requests.Response:
        """Perform HTTP request with exponential backoff and circuit breaker."""
        self._check_circuit()
        last_exc = None
        for attempt in range(1, self.retry_count + 1):
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json,
                    params=params,
                    timeout=self.timeout,
                )
                # Only retry on 5xx or 429 (rate limit)
                if response.status_code >= 500 or response.status_code == 429:
                    raise AIProviderError(
                        f"HTTP {response.status_code}: {response.text[:200]}"
                    )
                self._record_success()
                return response
            except (requests.Timeout, requests.ConnectionError, AIProviderError) as e:
                last_exc = e
                wait = min(2 ** attempt, 10)
                logger.warning(
                    "%s attempt %d/%d failed: %s. Retrying in %ds",
                    self.__class__.__name__, attempt, self.retry_count, e, wait,
                )
                time.sleep(wait)
        self._record_failure()
        raise AIProviderError(f"All retries failed: {last_exc}")

    def is_configured(self) -> bool:
        """Return True if the provider has a usable configuration."""
        return bool(self.api_key and self.model)
