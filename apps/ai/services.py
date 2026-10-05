"""AI service layer: provider selection, fallback, and orchestration."""
import logging
from typing import Optional, List, Dict, Any

from django.conf import settings

from .models import AIAnalysis
from .providers.base import AIProvider, AIProviderError, CircuitBreakerOpen
from .providers.grok import GrokProvider
from .providers.glm_provider import GLMProvider
from .providers.gemini_provider import GeminiProvider
from .providers.openai_provider import OpenAIProvider
from .providers.mock_provider import MockAIProvider

logger = logging.getLogger('apps.ai')


class AIService:
    """Central AI orchestration service."""

    PROVIDER_CLASSES = {
        'grok': GrokProvider,
        'glm': GLMProvider,
        'gemini': GeminiProvider,
        'openai': OpenAIProvider,
        'mock': MockAIProvider,
    }

    # ── Provider registry ─────────────────────────────────────────
    @staticmethod
    def get_provider(provider_name: str) -> Optional[AIProvider]:
        """Return a configured+enabled provider instance, or None."""
        if provider_name == 'mock':
            return MockAIProvider(config={})

        provider_cls = AIService.PROVIDER_CLASSES.get(provider_name)
        if not provider_cls:
            logger.warning("Unknown AI provider: %s", provider_name)
            return None

        config = settings.AI_PROVIDERS.get(provider_name, {})
        if not config.get('enabled'):
            logger.debug("Provider %s is disabled.", provider_name)
            return None
        if not config.get('api_key'):
            logger.debug("Provider %s has no API key configured.", provider_name)
            return None

        return provider_cls(config)

    # ── Analysis orchestration ────────────────────────────────────
    @staticmethod
    def run_analysis(
        provider_name: str,
        transactions: List[Dict[str, Any]],
        analysis_type: str,
        input_ref: str = '',
        fallback_to_mock: bool = True,
    ) -> Optional[AIAnalysis]:
        """
        Try the requested provider. On failure, try the configured
        AI_FALLBACK_PROVIDER. If that fails too, use the mock provider
        (if fallback_to_mock is True).

        Returns the persisted AIAnalysis record, or None if every
        provider failed.
        """
        provider_order = [provider_name]

        fallback = getattr(settings, 'AI_FALLBACK_PROVIDER', 'glm')
        if fallback and fallback != provider_name:
            provider_order.append(fallback)

        if fallback_to_mock and 'mock' not in provider_order:
            provider_order.append('mock')

        for name in provider_order:
            analysis = AIService._attempt(
                name, transactions, analysis_type, input_ref,
            )
            if analysis is not None:
                if name != provider_name:
                    logger.info(
                        "AI analysis fell back: requested=%s used=%s",
                        provider_name, name,
                    )
                return analysis

        logger.warning(
            "All AI providers failed for analysis_type=%s input_ref=%s",
            analysis_type, input_ref,
        )
        return None

    @staticmethod
    def _attempt(
        provider_name: str,
        transactions: List[Dict[str, Any]],
        analysis_type: str,
        input_ref: str,
    ) -> Optional[AIAnalysis]:
        """Run one analysis with a single provider. Returns None on failure."""
        provider = AIService.get_provider(provider_name)
        if not provider:
            return None

        try:
            if analysis_type == 'payday':
                result = provider.detect_payday(transactions)
            elif analysis_type == 'debt':
                result = provider.detect_debt_obligations(transactions)
            elif analysis_type == 'general':
                result = provider.analyze_transactions(transactions)
            else:
                raise ValueError(f"Unknown analysis type: {analysis_type}")
        except (AIProviderError, CircuitBreakerOpen) as e:
            logger.error("AI provider %s failed: %s", provider_name, e)
            return None
        except Exception as e:
            logger.exception("Unexpected AI error (%s): %s", provider_name, e)
            return None

        # Normalise confidence + explanation for storage
        confidence = None
        explanation = ''
        if isinstance(result, dict):
            conf_val = result.get('confidence')
            try:
                if conf_val is not None:
                    confidence = float(conf_val)
            except (TypeError, ValueError):
                confidence = None
            explanation = result.get('explanation', '') or ''

        return AIAnalysis.objects.create(
            provider=provider_name,
            model_name=provider.get_model_name() or provider_name,
            input_reference=input_ref,
            output_data=result,
            confidence=confidence,
            explanation=explanation,
        )

    # ── Chat orchestration ────────────────────────────────────────
    @staticmethod
    def chat(
        provider_name: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 1000,
    ) -> str:
        """
        Chat completion used by the chatbot. Falls back to the configured
        fallback provider, then to mock, then to a static apology.
        """
        provider_order = [provider_name]

        fallback = getattr(settings, 'AI_FALLBACK_PROVIDER', 'glm')
        if fallback and fallback != provider_name:
            provider_order.append(fallback)

        if 'mock' not in provider_order:
            provider_order.append('mock')

        for name in provider_order:
            provider = AIService.get_provider(name)
            if not provider:
                continue
            try:
                reply = provider.chat_completion(messages, max_tokens=max_tokens)
                if reply and reply.strip():
                    if name != provider_name:
                        logger.info(
                            "Chat fell back: requested=%s used=%s",
                            provider_name, name,
                        )
                    return reply.strip()
            except Exception as e:
                logger.warning("Chat provider %s failed: %s", name, e)
                continue

        return "I'm sorry, I couldn't process that request right now."