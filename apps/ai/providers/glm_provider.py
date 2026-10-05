"""
GLM provider for Wethu Lenders.

Supports Z.AI / BigModel OpenAI-compatible chat-completions APIs.

The endpoint and model are intentionally configurable so the same provider
can be used with either:

    https://api.z.ai/api/paas/v4
or:
    https://open.bigmodel.cn/api/paas/v4

Do not hard-code API keys, model names, quotas, or production credentials.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from .base import AIProvider, AIProviderError

logger = logging.getLogger("apps.ai")


class GLMProvider(AIProvider):
    """
    GLM provider used by the Wethu Lenders AI abstraction layer.

    The provider intentionally uses the OpenAI-compatible chat-completions
    interface so it remains compatible with the existing AIProvider design.
    """

    # Default Z.AI international endpoint.
    # Override with GLM_BASE_URL in .env for BigModel China.
    DEFAULT_BASE_URL = "https://api.z.ai/api/paas/v4"

    # Current configurable default.
    # Set GLM_MODEL in .env to the exact model available to your account.
    DEFAULT_MODEL = "glm-4.6"

    CHAT_COMPLETIONS_PATH = "/chat/completions"

    # Prevent accidentally sending enormous transaction payloads to an
    # external AI provider.
    DEFAULT_MAX_INPUT_CHARS = 50000

    # Hard upper bounds. These protect the application even if .env contains
    # unreasonable values.
    HARD_MAX_INPUT_CHARS = 200000
    HARD_MAX_OUTPUT_TOKENS = 8000

    # Retryable provider responses. The base provider may also apply its own
    # retry/circuit-breaker handling.
    RETRYABLE_STATUS_CODES = {
        408,
        409,
        425,
        429,
        500,
        502,
        503,
        504,
    }

    # Error messages that commonly indicate authentication/configuration
    # failures. These should not be retried aggressively.
    NON_RETRYABLE_STATUS_CODES = {
        400,
        401,
        403,
        404,
        405,
        422,
    }

    def __init__(self, config: dict):
        super().__init__(config)

        self.base_url = (
            self.config.get("base_url")
            or self.DEFAULT_BASE_URL
        ).strip().rstrip("/")

        self.model = (
            self.config.get("model")
            or self.DEFAULT_MODEL
        ).strip()

        self.max_input_chars = self._safe_int(
            self.config.get(
                "max_input_chars",
                self.DEFAULT_MAX_INPUT_CHARS,
            ),
            default=self.DEFAULT_MAX_INPUT_CHARS,
            minimum=5000,
            maximum=self.HARD_MAX_INPUT_CHARS,
        )

        self.max_output_tokens = self._safe_int(
            self.config.get("max_tokens", 2000),
            default=2000,
            minimum=128,
            maximum=self.HARD_MAX_OUTPUT_TOKENS,
        )

        self.temperature = self._safe_float(
            self.config.get("temperature", 0.05),
            default=0.05,
            minimum=0.0,
            maximum=2.0,
        )

        self.top_p = self._safe_float(
            self.config.get("top_p", 0.8),
            default=0.8,
            minimum=0.0,
            maximum=1.0,
        )

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_int(
        value: Any,
        *,
        default: int,
        minimum: int,
        maximum: int,
    ) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default

        return max(minimum, min(parsed, maximum))

    @staticmethod
    def _safe_float(
        value: Any,
        *,
        default: float,
        minimum: float,
        maximum: float,
    ) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default

        return max(minimum, min(parsed, maximum))

    # ------------------------------------------------------------------
    # Endpoint helpers
    # ------------------------------------------------------------------

    def _chat_endpoint(self) -> str:
        """
        Return the final chat-completions endpoint.

        Supports:
            GLM_BASE_URL=https://api.z.ai/api/paas/v4
        or:
            GLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4

        Also safely handles a base URL that accidentally contains a trailing
        slash.
        """
        if self.base_url.endswith(self.CHAT_COMPLETIONS_PATH):
            return self.base_url

        return f"{self.base_url}{self.CHAT_COMPLETIONS_PATH}"

    # ------------------------------------------------------------------
    # Logging / error sanitisation
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_provider_text(text: str, limit: int = 500) -> str:
        """
        Prevent sensitive values or excessively large provider responses
        from being written to application logs.
        """
        if not text:
            return ""

        cleaned = str(text)

        # Redact common secret/token formats if they somehow appear in an
        # upstream response.
        cleaned = re.sub(
            r"(?i)(bearer\s+)[A-Za-z0-9._\-]+",
            r"\1[REDACTED]",
            cleaned,
        )

        cleaned = re.sub(
            r"(?i)(api[_-]?key\s*[=:]\s*)[^\s,;]+",
            r"\1[REDACTED]",
            cleaned,
        )

        return cleaned[:limit]

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        return status_code in GLMProvider.RETRYABLE_STATUS_CODES

    # ------------------------------------------------------------------
    # HTTP / Chat
    # ------------------------------------------------------------------

    def _chat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Send a chat-completions request to GLM.

        The actual HTTP retry/circuit-breaker mechanics remain delegated to
        AIProvider._request_with_retry so the existing platform architecture
        remains intact.
        """
        if not self.api_key:
            raise AIProviderError(
                "GLM API key is not configured."
            )

        if not self.model:
            raise AIProviderError(
                "GLM model is not configured."
            )

        if not messages:
            raise AIProviderError(
                "GLM request contains no messages."
            )

        output_tokens = self._safe_int(
            max_tokens if max_tokens is not None else self.max_output_tokens,
            default=self.max_output_tokens,
            minimum=128,
            maximum=self.HARD_MAX_OUTPUT_TOKENS,
        )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": output_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "stream": False,
        }

        endpoint = self._chat_endpoint()

        try:
            response = self._request_with_retry(
                "POST",
                endpoint,
                headers=headers,
                json=payload,
            )
        except Exception as exc:
            logger.error(
                "GLM request failed before response: %s",
                self._sanitize_provider_text(str(exc)),
            )
            raise AIProviderError(
                "GLM request failed."
            ) from exc

        status_code = getattr(response, "status_code", None)

        if status_code != 200:
            response_text = self._sanitize_provider_text(
                getattr(response, "text", ""),
                limit=500,
            )

            if status_code == 401:
                raise AIProviderError(
                    "GLM authentication failed. Check GLM_API_KEY."
                )

            if status_code == 403:
                raise AIProviderError(
                    f"GLM access denied: {response_text}"
                )

            if status_code == 404:
                raise AIProviderError(
                    f"GLM endpoint or model not found: {response_text}"
                )

            if status_code == 429:
                raise AIProviderError(
                    f"GLM rate limit reached: {response_text}"
                )

            raise AIProviderError(
                f"GLM error {status_code}: {response_text}"
            )

        # --------------------------------------------------------------
        # Decode response
        # --------------------------------------------------------------

        try:
            data = response.json()
        except Exception as exc:
            raw_text = self._sanitize_provider_text(
                getattr(response, "text", ""),
                limit=300,
            )

            raise AIProviderError(
                f"GLM returned invalid JSON: {raw_text}"
            ) from exc

        if not isinstance(data, dict):
            raise AIProviderError(
                "GLM returned an unexpected response structure."
            )

        # Provider-level error response.
        if data.get("error"):
            error_data = data.get("error")

            if isinstance(error_data, dict):
                code = error_data.get("code", "unknown")
                message = error_data.get("message", "unknown error")
            else:
                code = "unknown"
                message = str(error_data)

            raise AIProviderError(
                "GLM provider error "
                f"{self._sanitize_provider_text(str(code), 100)}: "
                f"{self._sanitize_provider_text(str(message), 400)}"
            )

        # --------------------------------------------------------------
        # Extract assistant content safely
        # --------------------------------------------------------------

        choices = data.get("choices")

        if not isinstance(choices, list) or not choices:
            raise AIProviderError(
                f"Unexpected GLM response shape: "
                f"keys={list(data.keys())}"
            )

        first_choice = choices[0]

        if not isinstance(first_choice, dict):
            raise AIProviderError(
                "GLM returned an invalid choice object."
            )

        message = first_choice.get("message")

        if not isinstance(message, dict):
            raise AIProviderError(
                "GLM response does not contain an assistant message."
            )

        content = message.get("content")

        # Some providers may return null content for tool calls.
        if content is None:
            tool_calls = message.get("tool_calls")

            if tool_calls:
                return json.dumps(
                    {
                        "tool_calls": tool_calls,
                    },
                    ensure_ascii=False,
                )

            # Some GLM responses can expose reasoning separately.
            reasoning_content = message.get("reasoning_content")

            if reasoning_content:
                return str(reasoning_content).strip()

            raise AIProviderError(
                "GLM returned an empty assistant message."
            )

        # Normal text response.
        if isinstance(content, str):
            result = content.strip()
        else:
            # Defensive handling for structured/multimodal content.
            try:
                result = json.dumps(
                    content,
                    ensure_ascii=False,
                )
            except (TypeError, ValueError):
                result = str(content).strip()

        if not result:
            raise AIProviderError(
                "GLM returned an empty response."
            )

        return result

    # ------------------------------------------------------------------
    # JSON helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_thinking_blocks(content: str) -> str:
        """
        Remove common visible reasoning markers if a provider/model emits
        them in the normal content channel.

        This does NOT attempt to access hidden reasoning; it only removes
        literal tags from returned text.
        """
        if not content:
            return ""

        cleaned = content

        cleaned = re.sub(
            r"<think>.*?</think>",
            "",
            cleaned,
            flags=re.IGNORECASE | re.DOTALL,
        )

        cleaned = re.sub(
            r"<thinking>.*?</thinking>",
            "",
            cleaned,
            flags=re.IGNORECASE | re.DOTALL,
        )

        return cleaned.strip()

    @staticmethod
    def _strip_markdown_fences(content: str) -> str:
        """
        Remove common Markdown code fences surrounding JSON.
        """
        if not content:
            return ""

        cleaned = content.strip()

        # ```json ... ```
        cleaned = re.sub(
            r"^\s*```(?:json|JSON)?\s*",
            "",
            cleaned,
            flags=re.MULTILINE,
        )

        cleaned = re.sub(
            r"\s*```\s*$",
            "",
            cleaned,
            flags=re.MULTILINE,
        )

        return cleaned.strip()

    @staticmethod
    def _extract_json_value(content: str) -> Optional[Any]:
        """
        Find and decode the first valid JSON object or array embedded in a
        larger model response.

        This is safer than simply using find('{') / rfind('}') because
        nested braces or extra text can otherwise produce invalid JSON.
        """
        if not content:
            return None

        cleaned = GLMProvider._strip_markdown_fences(
            GLMProvider._strip_thinking_blocks(content)
        )

        # Direct JSON first.
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        decoder = json.JSONDecoder()

        # Search for an object or array that can be decoded.
        candidate_positions = [
            index
            for index, char in enumerate(cleaned)
            if char in "{["
        ]

        for start in candidate_positions:
            try:
                value, _ = decoder.raw_decode(
                    cleaned[start:]
                )
                return value
            except json.JSONDecodeError:
                continue

        return None

    def _parse_json(self, content: str) -> Dict[str, Any]:
        """
        Parse model output into a dictionary.

        Accepted model behaviour:

        1. Pure JSON object.
        2. JSON object in Markdown fences.
        3. JSON embedded inside explanatory text.
        4. JSON list.
        5. Unparseable content.

        Never invent missing financial data.
        """
        if not content:
            return {
                "raw_analysis": "",
            }

        parsed = self._extract_json_value(content)

        if isinstance(parsed, dict):
            return parsed

        if isinstance(parsed, list):
            return {
                "items": parsed,
            }

        logger.warning(
            "GLM returned non-parseable JSON; preserving raw response."
        )

        return {
            "raw_analysis": content,
        }

    # ------------------------------------------------------------------
    # Transaction serialisation
    # ------------------------------------------------------------------

    def _serialise_transactions(
        self,
        transactions: Any,
    ) -> str:
        """
        Serialise transaction input while preventing an accidentally huge
        AI request.

        This keeps the AI provider protected from oversized prompts.
        """
        if transactions is None:
            return "[]"

        try:
            serialised = json.dumps(
                transactions,
                default=str,
                ensure_ascii=False,
            )
        except (TypeError, ValueError) as exc:
            logger.error(
                "Failed to serialise transactions: %s",
                self._sanitize_provider_text(str(exc)),
            )
            raise AIProviderError(
                "Transaction data could not be serialised."
            ) from exc

        if len(serialised) <= self.max_input_chars:
            return serialised

        logger.warning(
            "GLM transaction input exceeded %s characters; truncating.",
            self.max_input_chars,
        )

        truncated = serialised[:self.max_input_chars]

        # Make the truncation explicit to the model.
        return (
            truncated
            + '\n\n'
            + '[DATA_TRUNCATED_BY_APPLICATION]'
        )

    # ------------------------------------------------------------------
    # Generic structured analysis
    # ------------------------------------------------------------------

    def _run_transaction_analysis(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
    ) -> Dict[str, Any]:
        messages = [
            {
                "role": "system",
                "content": system_prompt.strip(),
            },
            {
                "role": "user",
                "content": user_prompt.strip(),
            },
        ]

        response = self._chat(
            messages,
            max_tokens=max_tokens,
        )

        return self._parse_json(response)

    # ------------------------------------------------------------------
    # Transaction analysis
    # ------------------------------------------------------------------

    def analyze_transactions(
        self,
        transactions,
        prompt_context: str = "",
    ):
        """
        Analyse bank transactions.

        The model must only use data supplied in transactions and context.
        Unknown information must be returned as null/unknown rather than
        fabricated.
        """
        tx_json = self._serialise_transactions(
            transactions
        )

        context = str(prompt_context or "").strip()

        system_prompt = """
You are a financial transaction analysis engine for a lending platform.

Your task is to analyse ONLY the financial transaction data supplied by
the application.

STRICT RULES:
- Never invent transactions.
- Never invent an employer.
- Never invent income.
- Never invent creditors.
- Never invent dates.
- Never infer a fact as confirmed if the data does not support it.
- Use null when information cannot be determined.
- Use numeric values for monetary amounts.
- Return ONLY one valid JSON object.
- Do not use Markdown.
- Do not add commentary before or after the JSON.
""".strip()

        user_prompt = f"""
Analyse the following bank transactions.

Return exactly this JSON structure:

{{
  "salary_detection": {{
    "detected": true,
    "amount": 0,
    "frequency": "monthly",
    "employer": null
  }},
  "recurring_expenses": [
    {{
      "merchant": "string",
      "amount": 0,
      "frequency": "monthly"
    }}
  ],
  "unusual_transactions": [
    {{
      "description": "string",
      "amount": 0,
      "reason": "string"
    }}
  ],
  "monthly_income_estimate": 0,
  "monthly_expense_estimate": 0
}}

Rules:

1. "salary_detection.detected" must only be true where salary evidence
   exists.
2. "employer" must be null if the employer cannot be identified.
3. Do not classify an ordinary purchase as unusual without evidence.
4. "monthly_income_estimate" must be based only on supplied transactions.
5. "monthly_expense_estimate" must be based only on supplied transactions.
6. Use empty arrays when nothing can be identified.
7. Use null where appropriate.

Transactions:
{tx_json}

Additional trusted application context:
{context if context else "None supplied."}
""".strip()

        return self._run_transaction_analysis(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=min(3000, self.HARD_MAX_OUTPUT_TOKENS),
        )

    # ------------------------------------------------------------------
    # Payday detection
    # ------------------------------------------------------------------

    def detect_payday(
        self,
        transactions,
    ):
        """
        Detect salary timing and predicted payday using transaction evidence.
        """
        tx_json = self._serialise_transactions(
            transactions
        )

        system_prompt = """
You are a salary and payday detection engine.

Use ONLY the transaction data supplied by the application.

STRICT RULES:
- Never invent salary transactions.
- Never invent an employer.
- Never invent a payday.
- If evidence is insufficient, use null.
- Confidence must be between 0 and 1.
- Return ONLY valid JSON.
- No Markdown.
- No explanations outside the JSON object.
""".strip()

        user_prompt = f"""
Analyse these bank transactions.

Return exactly:

{{
  "detected_salary": false,
  "salary_amount": null,
  "salary_frequency": null,
  "employer": null,
  "historical_paydays": [],
  "confidence": 0,
  "predicted_next_payday": null,
  "explanation": ""
}}

Allowed salary_frequency values:

"monthly"
"weekly"
"fortnightly"
"irregular"
null

Requirements:

- historical_paydays should contain actual observed dates when available.
- predicted_next_payday must be null if confidence is insufficient.
- Do not treat a one-off credit as recurring salary without evidence.
- The explanation must state the evidence used.
- Confidence must reflect the strength of the transaction evidence.

Transactions:
{tx_json}
""".strip()

        result = self._run_transaction_analysis(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=1500,
        )

        # Defensive confidence normalisation.
        confidence = result.get("confidence")

        if confidence is not None:
            try:
                result["confidence"] = max(
                    0.0,
                    min(float(confidence), 1.0),
                )
            except (TypeError, ValueError):
                result["confidence"] = None

        return result

    # ------------------------------------------------------------------
    # Debt obligations
    # ------------------------------------------------------------------

    def detect_debt_obligations(
        self,
        transactions,
    ):
        """
        Identify recurring debt obligations visible in transaction data.
        """
        tx_json = self._serialise_transactions(
            transactions
        )

        system_prompt = """
You are a debt-obligation analysis engine for a South African lending
platform.

Analyse ONLY the supplied transaction data.

STRICT RULES:
- Never invent creditors.
- Never invent repayments.
- Never infer a creditor from weak evidence.
- Only include recurring obligations actually supported by transactions.
- Confidence must be between 0 and 1.
- Return ONLY valid JSON.
- No Markdown.
- No commentary outside JSON.
""".strip()

        user_prompt = f"""
Identify recurring debt obligations in the transactions.

Possible examples include:
- loan repayments
- recurring debit orders
- credit-account repayments
- instalment payments

Return exactly:

{{
  "creditors": [
    {{
      "creditor_name": "string",
      "monthly_payment": 0,
      "frequency": "monthly",
      "last_payment_date": null,
      "confidence": 0
    }}
  ],
  "total_monthly_obligations": 0,
  "explanation": ""
}}

Rules:

1. Include only obligations supported by transaction evidence.
2. Do not classify groceries, fuel, subscriptions or normal purchases as
   debt without evidence.
3. creditor_name must be null/unknown if it cannot be determined safely.
4. monthly_payment must reflect observed recurring payments.
5. total_monthly_obligations must be based on the identified obligations.
6. Confidence must be between 0 and 1.

Transactions:
{tx_json}
""".strip()

        result = self._run_transaction_analysis(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=2500,
        )

        # Defensive normalisation for creditor confidence values.
        creditors = result.get("creditors")

        if isinstance(creditors, list):
            for creditor in creditors:
                if not isinstance(creditor, dict):
                    continue

                confidence = creditor.get("confidence")

                if confidence is None:
                    continue

                try:
                    creditor["confidence"] = max(
                        0.0,
                        min(float(confidence), 1.0),
                    )
                except (TypeError, ValueError):
                    creditor["confidence"] = None

        return result

    # ------------------------------------------------------------------
    # Chat completion
    # ------------------------------------------------------------------

    def chat_completion(
        self,
        messages,
        max_tokens: int = 1000,
    ) -> str:
        """
        General-purpose chat completion.

        Used by the staff/client AI assistants.
        """
        if not isinstance(messages, list):
            raise AIProviderError(
                "GLM messages must be a list."
            )

        cleaned_messages: List[Dict[str, str]] = []

        for message in messages:
            if not isinstance(message, dict):
                continue

            role = str(
                message.get("role", "")
            ).strip()

            content = message.get("content")

            if not role or content is None:
                continue

            cleaned_messages.append(
                {
                    "role": role,
                    "content": str(content),
                }
            )

        if not cleaned_messages:
            raise AIProviderError(
                "GLM chat request contains no valid messages."
            )

        return self._chat(
            cleaned_messages,
            max_tokens=max_tokens,
        )

    # ------------------------------------------------------------------
    # Provider health check
    # ------------------------------------------------------------------

    def health_check(self) -> Dict[str, Any]:
        """
        Perform a minimal live provider health check.

        This deliberately uses a very small response to minimise API
        consumption.

        Returns diagnostic information without exposing the API key.
        """
        try:
            response = self._chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "Return only the JSON object "
                            '{"ok":true}.'
                        ),
                    },
                    {
                        "role": "user",
                        "content": "Health check.",
                    },
                ],
                max_tokens=32,
            )

            parsed = self._extract_json_value(
                response
            )

            return {
                "provider": "glm",
                "status": "healthy",
                "model": self.model,
                "base_url": self.base_url,
                "response_valid": bool(parsed),
            }

        except AIProviderError as exc:
            return {
                "provider": "glm",
                "status": "unhealthy",
                "model": self.model,
                "base_url": self.base_url,
                "response_valid": False,
                "error": self._sanitize_provider_text(
                    str(exc),
                    limit=300,
                ),
            }
        except Exception as exc:
            logger.exception(
                "Unexpected GLM health-check failure."
            )

            return {
                "provider": "glm",
                "status": "unhealthy",
                "model": self.model,
                "base_url": self.base_url,
                "response_valid": False,
                "error": "Unexpected provider failure.",
            }