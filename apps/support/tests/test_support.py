"""Tests for the support ticketing system."""
import pytest
from django.contrib.auth import get_user_model

from apps.support.models import SupportTicket, TicketMessage
from apps.support.services import TicketService

User = get_user_model()


@pytest.mark.django_db
class TestTicketService:

    def _client(self):
        return User.objects.create_user(
            email='supclient@wethu.test', password='TestPass123!',
        )

    def _staff(self):
        return User.objects.create_user(
            email='supstaff@wethu.test', password='TestPass123!',
            is_staff=True, is_superuser=True,
        )

    def test_create_ticket_sets_sla(self):
        c = self._client()
        t = TicketService.create_ticket(
            client=c, subject='Cannot log in',
            body='I forgot my password.', priority='high', category='account',
        )
        assert t.status == 'open'
        assert t.sla_first_response_due is not None
        assert t.resolution_due is not None
        assert t.messages.count() == 1
        assert t.messages.first().role == 'client'

    def test_create_ticket_empty_subject_fails(self):
        c = self._client()
        with pytest.raises(ValueError):
            TicketService.create_ticket(client=c, subject='  ', body='ok')

    def test_first_staff_reply_sets_first_response_at(self):
        c = self._client()
        s = self._staff()
        t = TicketService.create_ticket(client=c, subject='A', body='B')
        assert t.first_response_at is None
        TicketService.post_message(t, s, body='Looking into it', role='staff')
        t.refresh_from_db()
        assert t.first_response_at is not None
        assert t.status == 'in_progress'

    def test_internal_note_hidden_from_client(self):
        c = self._client()
        s = self._staff()
        t = TicketService.create_ticket(client=c, subject='A', body='B')
        TicketService.post_message(t, s, body='Internal note',
                                    role='staff', is_internal_note=True)
        assert t.messages.filter(is_internal_note=True).count() == 1
        # Client posting an internal note should be rejected
        with pytest.raises(ValueError):
            TicketService.post_message(t, c, body='x', role='client',
                                       is_internal_note=True)

    def test_resolve_sets_resolved_at(self):
        c = self._client()
        s = self._staff()
        t = TicketService.create_ticket(client=c, subject='A', body='B')
        TicketService.transition(t, 'resolved', s)
        t.refresh_from_db()
        assert t.status == 'resolved'
        assert t.resolved_at is not None

    def test_assign_moves_to_in_progress(self):
        c = self._client()
        s = self._staff()
        t = TicketService.create_ticket(client=c, subject='A', body='B')
        TicketService.assign(t, s)
        t.refresh_from_db()
        assert t.assigned_to == s
        assert t.status == 'in_progress'


@pytest.mark.django_db
class TestTicketAPI:

    def test_client_can_create(self, client):
        user = User.objects.create_user(
            email='apiclient@wethu.test', password='TestPass123!',
        )
        client.force_login(user)
        r = client.post(
            '/api/v1/support/tickets/',
            data={'subject': 'Test', 'body': 'Help me', 'category': 'other'},
            content_type='application/json',
        )
        assert r.status_code == 201
        assert SupportTicket.objects.count() == 1

    def test_client_sees_only_own_tickets(self, client):
        u1 = User.objects.create_user(email='u1@x.com', password='TestPass123!')
        u2 = User.objects.create_user(email='u2@x.com', password='TestPass123!')
        SupportTicket.objects.create(client=u1, subject='A')
        SupportTicket.objects.create(client=u2, subject='B')
        client.force_login(u1)
        r = client.get('/api/v1/support/tickets/')
        assert r.status_code == 200
        assert r.json()['count'] == 1

    def test_staff_sees_all_tickets(self, client):
        u1 = User.objects.create_user(email='u3@x.com', password='TestPass123!')
        admin = User.objects.create_user(
            email='admin@x.com', password='TestPass123!',
            is_staff=True, is_superuser=True,
        )
        SupportTicket.objects.create(client=u1, subject='A')
        client.force_login(admin)
        r = client.get('/api/v1/support/tickets/')
        assert r.status_code == 200
        assert r.json()['count'] == 1