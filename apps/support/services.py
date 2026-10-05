"""Support ticket lifecycle services."""
import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.audit.services import AuditService

from .models import SupportTicket, TicketMessage

logger = logging.getLogger('apps.support')


SLA_HOURS = {
    'urgent': {'first_response': 2, 'resolution': 24},
    'high':   {'first_response': 8, 'resolution': 72},
    'normal': {'first_response': 24, 'resolution': 168},   # 7 days
    'low':    {'first_response': 48, 'resolution': 336},   # 14 days
}


def _sla_due(priority: str, kind: str):
    """Return the SLA deadline for a given priority + metric."""
    hours = SLA_HOURS.get(priority, SLA_HOURS['normal'])[kind]
    return timezone.now() + timedelta(hours=hours)


class TicketService:

    @staticmethod
    @transaction.atomic
    def create_ticket(*, client, subject: str, body: str, category: str = 'other',
                      priority: str = 'normal', related_loan=None,
                      related_application=None, ip_address=None) -> SupportTicket:
        subject = (subject or '').strip()[:200]
        body = (body or '').strip()
        if not subject:
            raise ValueError('Subject is required.')
        if not body:
            raise ValueError('Message body is required.')
        if len(body) > 5000:
            raise ValueError('Message body is too long (max 5000 chars).')

        ticket = SupportTicket.objects.create(
            client=client,
            subject=subject,
            category=category,
            priority=priority,
            status='open',
            related_loan=related_loan,
            related_application=related_application,
            sla_first_response_due=_sla_due(priority, 'first_response'),
            resolution_due=_sla_due(priority, 'resolution'),
            last_message_at=timezone.now(),
        )

        TicketMessage.objects.create(
            ticket=ticket, author=client, role='client', body=body,
        )

        AuditService.record(
            actor=client, action='support_ticket_created',
            object_type='support_ticket', object_id=str(ticket.id),
            ip_address=ip_address,
            after_value={'subject': subject, 'priority': priority, 'category': category},
        )

        TicketService._notify_staff(ticket, 'ticket_created')
        return ticket

    @staticmethod
    @transaction.atomic
    def post_message(ticket: SupportTicket, author, body: str, role: str,
                     is_internal_note: bool = False, ip_address=None) -> TicketMessage:
        body = (body or '').strip()
        if not body:
            raise ValueError('Message body cannot be empty.')
        if len(body) > 5000:
            raise ValueError('Message body is too long (max 5000 chars).')

        # Internal notes are staff-only
        if is_internal_note and role != 'staff':
            raise ValueError('Only staff can post internal notes.')

        msg = TicketMessage.objects.create(
            ticket=ticket, author=author, role=role,
            body=body, is_internal_note=is_internal_note,
        )

        # Move status if this is the first staff reply
        updates = {'last_message_at': timezone.now()}
        if role == 'staff' and not is_internal_note and not ticket.first_response_at:
            updates['first_response_at'] = timezone.now()
        if role == 'staff' and not is_internal_note and ticket.status == 'open':
            updates['status'] = 'in_progress'
        if role == 'client' and ticket.status == 'awaiting_client':
            updates['status'] = 'in_progress'

        for k, v in updates.items():
            setattr(ticket, k, v)
        ticket.save(update_fields=list(updates.keys()) + ['updated_at'])

        # Notify the opposite party (never for internal notes)
        if not is_internal_note:
            if role == 'staff':
                TicketService._notify_client(ticket, 'ticket_replied', msg)
            else:
                TicketService._notify_staff(ticket, 'ticket_replied')

        AuditService.record(
            actor=author, action='support_ticket_message',
            object_type='support_ticket', object_id=str(ticket.id),
            ip_address=ip_address,
            after_value={'role': role, 'internal': is_internal_note},
        )
        return msg

    @staticmethod
    @transaction.atomic
    def assign(ticket: SupportTicket, staff, actor=None, ip_address=None) -> SupportTicket:
        ticket.assigned_to = staff
        if ticket.status == 'open':
            ticket.status = 'in_progress'
        ticket.save(update_fields=['assigned_to', 'status', 'updated_at'])
        AuditService.record(
            actor=actor or staff, action='support_ticket_assigned',
            object_type='support_ticket', object_id=str(ticket.id),
            ip_address=ip_address,
            after_value={'assigned_to': staff.email},
        )
        return ticket

    @staticmethod
    @transaction.atomic
    def transition(ticket: SupportTicket, new_status: str, actor, notes: str = '',
                   ip_address=None) -> SupportTicket:
        valid = {c[0] for c in SupportTicket.STATUS_CHOICES}
        if new_status not in valid:
            raise ValueError(f'Invalid status: {new_status}')

        old = ticket.status
        ticket.status = new_status
        updates = ['status', 'updated_at']

        if new_status == 'resolved' and not ticket.resolved_at:
            ticket.resolved_at = timezone.now()
            updates.append('resolved_at')
        if new_status == 'closed' and not ticket.closed_at:
            ticket.closed_at = timezone.now()
            updates.append('closed_at')

        ticket.save(update_fields=updates)

        if notes:
            TicketMessage.objects.create(
                ticket=ticket, author=actor, role='staff',
                body=notes, is_internal_note=True,
            )

        AuditService.record(
            actor=actor, action=f'support_ticket_{new_status}',
            object_type='support_ticket', object_id=str(ticket.id),
            ip_address=ip_address,
            before_value={'status': old}, after_value={'status': new_status},
        )

        if new_status in ('resolved', 'closed'):
            TicketService._notify_client(ticket, f'ticket_{new_status}', None)

        return ticket

    # ── Notification helpers ─────────────────────────────────────
    @staticmethod
    def _notify_staff(ticket: SupportTicket, event: str):
        try:
            from django.conf import settings
            from django.contrib.auth import get_user_model
            from apps.notifications.services import NotificationService
            User = get_user_model()
            recipients = getattr(settings, 'SECURITY_ALERT_RECIPIENTS', []) or []
            for email in recipients:
                user = User.objects.filter(email__iexact=email, is_active=True).first()
                if not user:
                    continue
                NotificationService.dispatch(
                    user, event,
                    context={
                        'name': user.full_name or user.email,
                        'ticket_id': str(ticket.id),
                        'subject': ticket.subject,
                        'priority': ticket.priority,
                        'client_email': ticket.client.email,
                    },
                    channels=['email'],
                )
        except Exception as e:
            logger.warning("Ticket staff notification failed: %s", e)

    @staticmethod
    def _notify_client(ticket: SupportTicket, event: str, message):
        try:
            from apps.notifications.services import NotificationService
            NotificationService.dispatch(
                ticket.client, event,
                context={
                    'name': ticket.client.full_name or ticket.client.email,
                    'ticket_id': str(ticket.id),
                    'subject': ticket.subject,
                    'preview': (message.body[:200] if message else ''),
                },
                channels=['email', 'in_app'],
            )
        except Exception as e:
            logger.warning("Ticket client notification failed: %s", e)