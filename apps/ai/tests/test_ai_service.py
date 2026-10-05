"""Tests for the AI service layer."""
from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.ai.services import AIService


@pytest.mark.django_db
class TestAIService:

    def test_mock_provider_available(self):
        provider = AIService.get_provider('mock')
        assert provider is not None

    def test_mock_payday_analysis(self, db):
        """
        Offline mock never invents data — it returns a well-formed
        structure with detected_salary=False and confidence 0.0 so
        downstream code can distinguish "not determined" from
        "determined to be false".
        """
        provider = AIService.get_provider('mock')
        result = provider.detect_payday([{'date': '2026-08-25', 'amount': '15000'}])
        assert result['detected_salary'] is False
        assert result['salary_amount'] is None
        assert result['confidence'] == 0.0
        assert 'mock' in result['explanation'].lower()

    def test_run_analysis_stores_record(self, db):
        analysis = AIService.run_analysis(
            'mock',
            [{'date': '2026-08-25', 'amount': '15000'}],
            'payday',
            input_ref='store-test',
        )
        assert analysis is not None
        assert analysis.provider == 'mock'
        assert analysis.input_reference == 'store-test'

    def test_fallback_to_mock_when_real_provider_fails(self, db):
        original_get = AIService.get_provider

        def fake_get(name):
            if name == 'openai':
                return None
            return original_get(name)

        with patch.object(AIService, 'get_provider', side_effect=fake_get):
            analysis = AIService.run_analysis(
                'openai', [{'date': '2026-08-25', 'amount': '15000'}],
                'payday', input_ref='fallback-test',
            )
        assert analysis is not None
        # In testing settings, only mock is enabled — everything falls to mock.
        assert analysis.provider == 'mock'

    def test_unknown_provider_returns_none(self, db):
        analysis = AIService.run_analysis('unknown', [], 'payday')
        # Falls back to mock, so result exists with provider=mock
        assert analysis is not None
        assert analysis.provider == 'mock'

    def test_testing_settings_disable_real_providers(self):
        """
        Guard: tests must never hit a real AI provider. If someone re-enables
        grok/glm/gemini/openai in testing.py, this test catches it.
        """
        from django.conf import settings
        for name in ('grok', 'glm', 'gemini', 'openai'):
            cfg = settings.AI_PROVIDERS.get(name, {})
            assert cfg.get('enabled') is False, (
                f"Provider '{name}' is enabled in test settings — tests would "
                f"hit the real API. Disable it in config/settings/testing.py."
            )
            assert not cfg.get('api_key'), (
                f"Provider '{name}' has an API key set in test settings."
            )