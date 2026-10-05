"""API views for support tickets."""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import SupportTicket
from .serializers import (
    SupportTicketSerializer, TicketCreateSerializer,
    TicketMessageSerializer, TicketReplySerializer,
)
from .services import TicketService


def _is_staff(user) -> bool:
    return (
        user.is_superuser
        or user.is_staff
        or user.has_role('Administrator')
        or user.has_role('Support Agent')
        or user.has_role('Credit Officer')
    )


class SupportTicketViewSet(viewsets.ModelViewSet):
    serializer_class = SupportTicketSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        user = self.request.user
        qs = SupportTicket.objects.select_related('client', 'assigned_to')
        if _is_staff(user):
            pass  # see all
        else:
            qs = qs.filter(client=user)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs.order_by('-last_message_at', '-created_at')

    def create(self, request, *args, **kwargs):
        s = TicketCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data

        related_loan = None
        related_app = None
        if d.get('related_loan'):
            from apps.loans.models import Loan
            related_loan = Loan.objects.filter(id=d['related_loan'], client=request.user).first()
        if d.get('related_application'):
            from apps.loans.models import LoanApplication
            related_app = LoanApplication.objects.filter(
                id=d['related_application'], client=request.user,
            ).first()

        ticket = TicketService.create_ticket(
            client=request.user,
            subject=d['subject'], body=d['body'],
            category=d['category'], priority=d['priority'],
            related_loan=related_loan, related_application=related_app,
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        return Response(SupportTicketSerializer(ticket).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        ticket = self.get_object()
        qs = ticket.messages.order_by('created_at')
        if not _is_staff(request.user):
            qs = qs.filter(is_internal_note=False)
        return Response(TicketMessageSerializer(qs, many=True).data)

    @action(detail=True, methods=['post'])
    def reply(self, request, pk=None):
        ticket = self.get_object()
        s = TicketReplySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        role = 'staff' if _is_staff(request.user) else 'client'
        try:
            msg = TicketService.post_message(
                ticket, request.user,
                body=s.validated_data['body'],
                role=role,
                is_internal_note=s.validated_data.get('is_internal_note', False),
                ip_address=request.META.get('REMOTE_ADDR'),
            )
        except ValueError as e:
            return Response({'detail': str(e)}, status=400)
        return Response(TicketMessageSerializer(msg).data, status=201)

    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        if not _is_staff(request.user):
            return Response({'detail': 'Not allowed.'}, status=403)
        ticket = self.get_object()
        TicketService.assign(ticket, request.user, actor=request.user,
                             ip_address=request.META.get('REMOTE_ADDR'))
        return Response(SupportTicketSerializer(ticket).data)

    @action(detail=True, methods=['post'])
    def transition(self, request, pk=None):
        if not _is_staff(request.user):
            return Response({'detail': 'Not allowed.'}, status=403)
        ticket = self.get_object()
        new_status = request.data.get('status')
        try:
            TicketService.transition(
                ticket, new_status, request.user,
                notes=request.data.get('notes', ''),
                ip_address=request.META.get('REMOTE_ADDR'),
            )
        except ValueError as e:
            return Response({'detail': str(e)}, status=400)
        return Response(SupportTicketSerializer(ticket).data)