"""Tests for ChatService — including the tuple-vs-string provider bug."""
from unittest.mock import patch, MagicMock

import pytest

from apps.accounts.models import User
from apps.chat.models import ChatConversation, ChatMessage
from apps.chat.services import ChatService


@pytest.fixture
def chat_user(db):
    return User.objects.create_user(
        email='chatuser@wethu.test',
        password='TestPass123!',
        first_name='Chat',
        last_name='User',
    )


# ── Provider preference — the critical bug ──────────────────────────
class TestProviderPreference:
    """
    Regression: the original code had `for candidate in ('glm'):` which
    iterates over the string's characters ('g', 'l', 'm') instead of
    treating the string as a single element.
    """

    def test_default_order_is_grok_then_glm_then_mock(self):
        order = ChatService._provider_preference({'role': 'client'}, None)
        assert order == ['grok', 'glm', 'mock']
        # Explicitly ensure we do NOT get single characters
        assert 'g' not in order
        assert 'l' not in order
        assert 'm' not in order

    def test_requested_provider_takes_precedence(self):
        order = ChatService._provider_preference({'role': 'client'}, 'openai')
        assert order == ['openai', 'mock']

    def test_no_duplicate_when_fallback_equals_default(self):
        with patch('django.conf.settings.AI_DEFAULT_PROVIDER', 'glm'), \
             patch('django.conf.settings.AI_FALLBACK_PROVIDER', 'glm'):
            order = ChatService._provider_preference({'role': 'client'}, None)
            assert order == ['glm', 'mock']

    def test_mock_always_last(self):
        order = ChatService._provider_preference({'role': 'staff'}, None)
        assert order[-1] == 'mock'


# ── Fallback reply ──────────────────────────────────────────────────
class TestFallbackReply:

    def test_balance_with_no_loans(self):
        reply = ChatService._fallback_reply(
            'what is my balance', {'loans': []},
        )
        assert 'active loan' in reply.lower()

    def test_balance_with_loans(self):
        reply = ChatService._fallback_reply(
            'what is my balance',
            {'loans': [
                {'product': 'Personal', 'outstanding': 'R 5000.00', 'status': 'active'},
            ]},
        )
        assert 'R 5000.00' in reply
        assert 'Personal' in reply

    def test_upcoming_payment(self):
        reply = ChatService._fallback_reply(
            'when is my next payment',
            {'upcoming_payments': [{'amount': 'R 541.67', 'due_date': '2026-10-01'}]},
        )
        assert '541.67' in reply
        assert '2026-10-01' in reply

    def test_staff_portfolio_snapshot(self):
        reply = ChatService._fallback_reply(
            'portfolio status',
            {'role': 'staff', 'portfolio': {
                'active_loans': 10, 'overdue_loans': 2,
                'total_outstanding': 'R 50000.00',
            }},
        )
        assert '10' in reply
        assert '2' in reply
        assert '50000' in reply


# ── Scrub ───────────────────────────────────────────────────────────
class TestScrub:

    def test_redacts_openai_key(self):
        assert ChatService._scrub('Key sk-abcdefg') == '[redacted]'

    def test_redacts_google_key(self):
        assert ChatService._scrub('AIzaSyD...') == '[redacted]'

    def test_strips_system_prompt_leak(self):
        leaky = 'Sure. system_prompt: You are the Wethu assistant'
        cleaned = ChatService._scrub(leaky)
        assert 'system_prompt' not in cleaned

    def test_keeps_normal_text(self):
        text = 'Your balance is R 5,000.00.'
        assert ChatService._scrub(text) == text

    def test_empty_input_returns_apology(self):
        assert 'sorry' in ChatService._scrub('').lower()


# ── Full ask pipeline ───────────────────────────────────────────────
@pytest.mark.django_db
class TestAsk:

    def test_creates_user_and_assistant_messages(self, chat_user):
        conv = ChatConversation.objects.create(user=chat_user)
        with patch('apps.ai.services.AIService.chat', return_value='Hello there'):
            ChatService.ask(chat_user, 'Hi', conv)

        assert ChatMessage.objects.filter(conversation=conv, role='user').count() == 1
        assert ChatMessage.objects.filter(conversation=conv, role='assistant').count() == 1

    def test_empty_message_rejected(self, chat_user):
        conv = ChatConversation.objects.create(user=chat_user)
        with pytest.raises(ValueError):
            ChatService.ask(chat_user, '   ', conv)

    def test_overlength_message_rejected(self, chat_user):
        conv = ChatConversation.objects.create(user=chat_user)
        with pytest.raises(ValueError):
            ChatService.ask(chat_user, 'x' * 3000, conv)

    def test_conversation_metadata_updated(self, chat_user):
        conv = ChatConversation.objects.create(user=chat_user)
        with patch('apps.ai.services.AIService.chat', return_value='OK'):
            ChatService.ask(chat_user, 'How much do I owe?', conv)

        conv.refresh_from_db()
        assert conv.message_count == 2
        assert conv.title == 'How much do I owe?'
        assert conv.last_message_at is not None

    def test_falls_back_when_all_providers_fail(self, chat_user):
        conv = ChatConversation.objects.create(user=chat_user)
        with patch('apps.ai.services.AIService.chat', side_effect=Exception('boom')):
            reply = ChatService.ask(chat_user, 'What is my balance?', conv)

        assert reply.role == 'assistant'
        assert reply.ai_provider == 'fallback'
        assert reply.ai_model == 'rule-based'
        assert 'active loan' in reply.content.lower()

    def test_cache_hit_avoids_second_ai_call(self, chat_user):
        conv = ChatConversation.objects.create(user=chat_user)
        with patch('apps.ai.services.AIService.chat', return_value='Cached reply') as mock_ai:
            ChatService.ask(chat_user, 'Hello', conv)
            ChatService.ask(chat_user, 'Hello', conv)

        # Second identical question should hit cache, not the AI
        assert mock_ai.call_count == 1