"""Client-facing support views."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.loans.models import Loan, LoanApplication
from apps.support.models import SupportTicket
from apps.support.services import TicketService


@login_required
def ticket_list(request):
    tickets = (
        SupportTicket.objects
        .filter(client=request.user)
        .order_by('-last_message_at', '-created_at')
    )
    return render(request, 'client/support/list.html', {'tickets': tickets})


@login_required
def ticket_create(request):
    # Allow pre-linking a ticket to a loan or application
    loan = None
    application = None
    if request.GET.get('loan'):
        loan = Loan.objects.filter(id=request.GET['loan'], client=request.user).first()
    if request.GET.get('application'):
        application = LoanApplication.objects.filter(
            id=request.GET['application'], client=request.user,
        ).first()

    if request.method == 'POST':
        try:
            ticket = TicketService.create_ticket(
                client=request.user,
                subject=request.POST.get('subject', ''),
                body=request.POST.get('body', ''),
                category=request.POST.get('category', 'other'),
                priority=request.POST.get('priority', 'normal'),
                related_loan=loan,
                related_application=application,
                ip_address=request.META.get('REMOTE_ADDR'),
            )
            messages.success(request, 'Ticket created. We will respond shortly.')
            return redirect('client_support_detail', ticket_id=ticket.id)
        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f'Could not create ticket: {e}')

    return render(request, 'client/support/create.html', {
        'categories': SupportTicket.CATEGORY_CHOICES,
        'priorities': SupportTicket.PRIORITY_CHOICES,
        'loan': loan,
        'application': application,
    })


@login_required
def ticket_detail(request, ticket_id):
    ticket = get_object_or_404(
        SupportTicket, id=ticket_id, client=request.user,
    )

    if request.method == 'POST':
        try:
            TicketService.post_message(
                ticket, request.user,
                body=request.POST.get('body', ''),
                role='client',
                ip_address=request.META.get('REMOTE_ADDR'),
            )
            messages.success(request, 'Reply sent.')
            return redirect('client_support_detail', ticket_id=ticket.id)
        except ValueError as e:
            messages.error(request, str(e))

    # Client never sees internal notes
    msgs = ticket.messages.filter(is_internal_note=False).order_by('created_at')
    return render(request, 'client/support/detail.html', {
        'ticket': ticket,
        'messages': msgs,
    })