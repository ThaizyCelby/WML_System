"""Support ticket models."""
from django.db import models

from core.models import TimeStampedModel, UUIDPrimaryKeyModel


class SupportTicket(UUIDPrimaryKeyModel, TimeStampedModel):
    """
    A single support ticket raised by a client.

    SLA fields are computed at creation from the ticket's priority:
    - sla_first_response_due  → first_response_at must be <= this
    - resolution_due          → resolved_at must be <= this
    """
    CATEGORY_CHOICES = [
        ('loan_application', 'Loan application'),
        ('repayment', 'Repayment / debit order'),
        ('account', 'Account / login'),
        ('kyc', 'KYC / documents'),
        ('statement', 'Bank statement'),
        ('technical', 'Technical issue'),
        ('complaint', 'Complaint'),
        ('other', 'Other'),
    ]
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In progress'),
        ('awaiting_client', 'Awaiting client'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]

    organisation = models.ForeignKey(
        'accounts.Organisation', null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='support_tickets',
        db_index=True,
    )

    client = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE,
        related_name='support_tickets',
    )
    subject = models.CharField(max_length=200)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default='other')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='normal', db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open', db_index=True)

    assigned_to = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='assigned_tickets',
    )

    related_loan = models.ForeignKey(
        'loans.Loan', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='support_tickets',
    )
    related_application = models.ForeignKey(
        'loans.LoanApplication', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='support_tickets',
    )

    sla_first_response_due = models.DateTimeField(null=True, blank=True)
    first_response_at = models.DateTimeField(null=True, blank=True)
    resolution_due = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'support_tickets'
        ordering = ['-last_message_at', '-created_at']
        indexes = [
            models.Index(fields=['status', 'priority']),
            models.Index(fields=['client', 'status']),
            models.Index(fields=['assigned_to', 'status']),
            models.Index(fields=['organisation', 'status']),
        ]

    def __str__(self):
        return f"#{str(self.id)[:8]} {self.subject}"

    @property
    def is_open(self) -> bool:
        return self.status in ('open', 'in_progress', 'awaiting_client')

    @property
    def first_response_sla_breached(self) -> bool:
        if not self.sla_first_response_due or not self.first_response_at:
            return False
        return self.first_response_at > self.sla_first_response_due

    @property
    def resolution_sla_breached(self) -> bool:
        if not self.resolution_due:
            return False
        if self.resolved_at:
            return self.resolved_at > self.resolution_due
        from django.utils import timezone
        return timezone.now() > self.resolution_due


class TicketMessage(UUIDPrimaryKeyModel, TimeStampedModel):
    """A message on a ticket — either public or an internal staff note."""
    ROLE_CHOICES = [
        ('client', 'Client'),
        ('staff', 'Staff'),
        ('system', 'System'),
    ]

    ticket = models.ForeignKey(
        SupportTicket, on_delete=models.CASCADE, related_name='messages',
    )
    author = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='ticket_messages',
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    body = models.TextField()
    is_internal_note = models.BooleanField(
        default=False,
        help_text='Internal staff notes are hidden from the client.',
    )

    class Meta:
        db_table = 'support_ticket_messages'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['ticket', 'created_at']),
        ]

    def __str__(self):
        kind = 'NOTE' if self.is_internal_note else self.role
        return f"[{kind}] {self.body[:60]}"