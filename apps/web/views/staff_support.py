"""Staff-facing support views."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.support.models import SupportTicket
from apps.support.services import TicketService


STAFF_ROLES = (
    'Administrator', 'Credit Officer', 'Collections Officer',
    'Support Agent', 'Finance Officer', 'Compliance Officer',
)


def _staff_allowed(user):
    if user.is_superuser or user.is_staff:
        return True
    return any(user.has_role(r) for r in STAFF_ROLES)


@login_required
def ticket_queue(request):
    if not _staff_allowed(request.user):
        messages.error(request, 'You do not have access to the support queue.')
        return redirect('portal_dashboard')

    qs = SupportTicket.objects.select_related('client', 'assigned_to')

    status_filter = request.GET.get('status', 'open')
    if status_filter:
        qs = qs.filter(status=status_filter)

    priority = request.GET.get('priority', '')
    if priority:
        qs = qs.filter(priority=priority)

    assigned = request.GET.get('assigned', '')
    if assigned == 'me':
        qs = qs.filter(assigned_to=request.user)
    elif assigned == 'unassigned':
        qs = qs.filter(assigned_to__isnull=True)

    qs = qs.order_by('-last_message_at', '-created_at')

    # Simple counters for the tab strip
    counters = {
        'open': SupportTicket.objects.filter(status='open').count(),
        'in_progress': SupportTicket.objects.filter(status='in_progress').count(),
        'awaiting_client': SupportTicket.objects.filter(status='awaiting_client').count(),
        'resolved': SupportTicket.objects.filter(status='resolved').count(),
        'closed': SupportTicket.objects.filter(status='closed').count(),
    }

    return render(request, 'staff/support/list.html', {
        'tickets': qs[:200],
        'status_filter': status_filter,
        'priority_filter': priority,
        'assigned_filter': assigned,
        'counters': counters,
        'statuses': SupportTicket.STATUS_CHOICES,
        'priorities': SupportTicket.PRIORITY_CHOICES,
    })


@login_required
def ticket_detail(request, ticket_id):
    if not _staff_allowed(request.user):
        return redirect('portal_dashboard')

    ticket = get_object_or_404(
        SupportTicket.objects.select_related('client', 'assigned_to'),
        id=ticket_id,
    )

    if request.method == 'POST':
        action = request.POST.get('action', 'reply')
        if action == 'reply':
            body = request.POST.get('body', '').strip()
            is_internal = request.POST.get('is_internal_note') == 'on'
            try:
                TicketService.post_message(
                    ticket, request.user, body=body, role='staff',
                    is_internal_note=is_internal,
                    ip_address=request.META.get('REMOTE_ADDR'),
                )
                messages.success(request, 'Reply sent.')
            except ValueError as e:
                messages.error(request, str(e))
        return redirect('staff_support_detail', ticket_id=ticket.id)

    # Staff see all messages including internal notes
    msgs = ticket.messages.select_related('author').order_by('created_at')

    return render(request, 'staff/support/detail.html', {
        'ticket': ticket,
        'messages': msgs,
    })


@require_POST
@login_required
def ticket_assign_me(request, ticket_id):
    if not _staff_allowed(request.user):
        return redirect('portal_dashboard')
    ticket = get_object_or_404(SupportTicket, id=ticket_id)
    TicketService.assign(ticket, request.user, actor=request.user,
                         ip_address=request.META.get('REMOTE_ADDR'))
    messages.success(request, 'Ticket assigned to you.')
    return redirect('staff_support_detail', ticket_id=ticket.id)


@require_POST
@login_required
def ticket_transition(request, ticket_id):
    if not _staff_allowed(request.user):
        return redirect('portal_dashboard')
    ticket = get_object_or_404(SupportTicket, id=ticket_id)
    new_status = request.POST.get('status')
    notes = request.POST.get('notes', '')
    try:
        TicketService.transition(ticket, new_status, request.user, notes=notes,
                                 ip_address=request.META.get('REMOTE_ADDR'))
        messages.success(request, f'Ticket moved to {new_status}.')
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('staff_support_detail', ticket_id=ticket.id)