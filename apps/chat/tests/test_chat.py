"""Tests for the AI chatbot service and API."""
import pytest
from decimal import Decimal
from datetime import date

from apps.accounts.models import User
from apps.chat.models import ChatConversation, ChatMessage
from apps.chat.services import ChatService
from apps.loans.models import Loan, LoanApplication, LoanProduct


@pytest.fixture
def client_user(db):
    return User.objects.create_user(
        email='client@example.com', password='TestPass123!',
    )


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        email='staff@example.com', password='TestPass123!',
        is_staff=True, is_superuser=True,
    )


@pytest.fixture
def loan_for(client_user):
    product = LoanProduct.objects.create(
        name='Test Loan', interest_rate=Decimal('30.00'),
        repayment_frequency='monthly',
    )
    application = LoanApplication.objects.create(
        client=client_user, product=product,
        requested_amount=Decimal('5000.00'), requested_term=12,
        status='active',
    )
    return Loan.objects.create(
        application=application, client=client_user, product=product,
        principal_amount=Decimal('5000.00'), interest_rate=Decimal('30.00'),
        total_interest=Decimal('1500.00'), fees_total=Decimal('125.00'),
        term_periods=12, repayment_frequency='monthly',
        start_date=date.today(), end_date=date.today(),
        outstanding_balance=Decimal('5000.00'), status='active',
    )


@pytest.mark.django_db
class TestChatService:

    def test_ask_creates_user_and_assistant_messages(self, client_user):
        conv = ChatConversation.objects.create(user=client_user)
        reply = ChatService.ask(client_user, "What is my balance?", conv)
        assert reply.role == 'assistant'
        assert ChatMessage.objects.filter(conversation=conv, role='user').count() == 1
        assert ChatMessage.objects.filter(conversation=conv, role='assistant').count() == 1

    def test_empty_message_rejected(self, client_user):
        conv = ChatConversation.objects.create(user=client_user)
        with pytest.raises(ValueError):
            ChatService.ask(client_user, " ", conv)

    def test_message_too_long_rejected(self, client_user):
        conv = ChatConversation.objects.create(user=client_user)
        with pytest.raises(ValueError):
            ChatService.ask(client_user, "x" * 3000, conv)

    def test_context_excludes_other_users_data(self, client_user, loan_for, db):
        other = User.objects.create_user(
            email='other@example.com', password='TestPass123!',
        )
        from apps.chat.context import build_client_context
        ctx = build_client_context(other)
        assert ctx['loans'] == []

        ctx_client = build_client_context(client_user)
        assert len(ctx_client['loans']) == 1
        assert ctx_client['loans'][0]['principal'] == 'R 5,000.00'

    def test_staff_context_is_aggregate_only(self, staff_user, loan_for):
        from apps.chat.context import build_staff_context
        ctx = build_staff_context(staff_user)
        assert ctx['role'] == 'staff'
        assert 'portfolio' in ctx

    def test_scrub_removes_prompt_leaks(self):
        text = "Here is my answer. system_prompt: You are the Wethu Micro Lenders Assistant ..."
        cleaned = ChatService._scrub(text)
        assert 'system_prompt' not in cleaned
        assert 'You are the Wethu Micro Lenders Assistant' not in cleaned

    def test_scrub_redacts_keys(self):
        assert ChatService._scrub("Key sk-abcdef") == "[redacted]"


@pytest.mark.django_db
class TestChatAPI:

    def test_new_conversation_endpoint(self, client, client_user):
        client.force_login(client_user)
        resp = client.post(
            '/api/v1/chat/conversations/new/',
            data={'message': 'What is my balance?', 'provider': 'mock'},
            content_type='application/json',
        )
        assert resp.status_code == 201
        body = resp.json()
        assert 'conversation' in body
        assert 'reply' in body
        assert body['reply']['role'] == 'assistant'

    def test_conversation_isolation(self, client, client_user, db):
        other = User.objects.create_user(
            email='other2@example.com', password='TestPass123!',
        )
        conv = ChatConversation.objects.create(user=other)
        client.force_login(client_user)
        resp = client.get(f'/api/v1/chat/conversations/{conv.id}/')
        assert resp.status_code == 404

    def test_ask_endpoint(self, client, client_user):
        conv = ChatConversation.objects.create(user=client_user)
        client.force_login(client_user)
        resp = client.post(
            f'/api/v1/chat/conversations/{conv.id}/ask/',
            data={'message': 'Hello', 'provider': 'mock'},
            content_type='application/json',
        )
        assert resp.status_code == 201
        assert resp.json()['role'] == 'assistant'