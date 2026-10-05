"""Settings smoke tests.

These are deliberately shallow — they check that key settings are present
and well-formed, without asserting specific values. Catches indentation
and structure regressions.
"""
from django.conf import settings


class TestAIProviderSettings:

    def test_grok_provider_configured(self):
        grok = settings.AI_PROVIDERS.get('grok')
        assert grok is not None, "grok provider missing from AI_PROVIDERS"
        assert isinstance(grok, dict)
        for key in ('enabled', 'api_key', 'model', 'base_url',
                    'max_tokens', 'temperature', 'timeout_seconds',
                    'retry_count', 'circuit_breaker_threshold'):
            assert key in grok, f"grok config missing key: {key}"

    def test_glm_provider_configured(self):
        glm = settings.AI_PROVIDERS.get('glm')
        assert glm is not None
        assert isinstance(glm, dict)
        for key in ('enabled', 'api_key', 'model', 'base_url'):
            assert key in glm, f"glm config missing key: {key}"

    def test_default_and_fallback_providers_set(self):
        assert settings.AI_DEFAULT_PROVIDER, "AI_DEFAULT_PROVIDER not set"
        assert settings.AI_FALLBACK_PROVIDER, "AI_FALLBACK_PROVIDER not set"

    def test_default_provider_exists_in_registry(self):
        assert settings.AI_DEFAULT_PROVIDER in settings.AI_PROVIDERS

    def test_fallback_provider_exists_in_registry(self):
        assert settings.AI_FALLBACK_PROVIDER in settings.AI_PROVIDERS


class TestCelerySchedule:

    def test_every_entry_has_task_and_schedule(self):
        for name, entry in settings.CELERY_BEAT_SCHEDULE.items():
            assert isinstance(entry, dict), f"{name} entry is not a dict"
            assert 'task' in entry, f"{name} missing 'task'"
            assert 'schedule' in entry, f"{name} missing 'schedule'"
            assert isinstance(entry['task'], str)
            assert entry['task'], f"{name} has empty task"

    def test_expected_jobs_registered(self):
        expected = {
            'submit-due-debits',
            'retry-failed-debits',
            'poll-pending-transactions',
            'run-reconciliation',
            'security-sweep',
        }
        assert expected.issubset(settings.CELERY_BEAT_SCHEDULE.keys())


class TestFinancialConfig:

    def test_all_money_fields_are_decimal(self):
        from decimal import Decimal
        for key in ('DEFAULT_INTEREST_RATE', 'INTEREST_RATE_MIN',
                    'INTEREST_RATE_MAX', 'LATE_PAYMENT_FEE',
                    'ORIGINATION_FEE_PERCENT'):
            value = settings.FINANCIAL_CONFIG[key]
            assert isinstance(value, Decimal), f"{key} is {type(value)}, not Decimal"

    def test_interest_rate_default_is_30(self):
        from decimal import Decimal
        assert settings.FINANCIAL_CONFIG['DEFAULT_INTEREST_RATE'] == Decimal('30.00')


class TestBrandingSettings:

    def test_site_name_is_wethu(self):
        assert 'Wethu' in settings.SITE_NAME

    def test_support_email_present(self):
        assert '@' in settings.SITE_SUPPORT_EMAIL