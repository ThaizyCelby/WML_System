"""Compliance models: policies, data processors, tasks, DSARs, incidents."""
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel, UUIDPrimaryKeyModel


POLICY_CATEGORY_CHOICES = [
    ('popia', 'POPIA'),
    ('paia', 'PAIA'),
    ('nca', 'National Credit Act'),
    ('fica', 'FICA / AML'),
    ('data_retention', 'Data Retention'),
    ('information_security', 'Information Security'),
    ('complaints', 'Complaints Procedure'),
    ('responsible_lending', 'Responsible Lending'),
    ('other', 'Other'),
]


class CompliancePolicy(UUIDPrimaryKeyModel, TimeStampedModel):
    """A versioned compliance policy (Privacy Policy, PAIA Manual, etc.)."""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('superseded', 'Superseded'),
        ('retired', 'Retired'),
    ]

    name = models.CharField(max_length=200, db_index=True)
    category = models.CharField(max_length=40, choices=POLICY_CATEGORY_CHOICES, db_index=True)
    version = models.CharField(max_length=20, default='1.0')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)

    effective_date = models.DateField(null=True, blank=True)
    next_review_date = models.DateField(null=True, blank=True, db_index=True)

    owner = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='owned_policies',
    )
    approved_by = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='approved_policies',
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    document = models.ForeignKey(
        'documents.Document', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='compliance_policies',
    )
    summary = models.TextField(blank=True)

    class Meta:
        db_table = 'compliance_policies'
        ordering = ['category', '-effective_date']
        indexes = [
            models.Index(fields=['category', 'status']),
            models.Index(fields=['next_review_date']),
        ]

    def __str__(self):
        return f"{self.name} v{self.version} [{self.status}]"

    @property
    def is_review_due(self) -> bool:
        if not self.next_review_date:
            return False
        return self.next_review_date <= timezone.now().date()


class DataProcessor(UUIDPrimaryKeyModel, TimeStampedModel):
    """A third-party processor of personal information (POPIA §20–21)."""
    PROCESSOR_TYPE_CHOICES = [
        ('ai', 'AI Provider'),
        ('payment', 'Payment Provider'),
        ('credit_bureau', 'Credit Bureau'),
        ('storage', 'Storage / Cloud'),
        ('email', 'Email'),
        ('sms', 'SMS'),
        ('monitoring', 'Monitoring'),
        ('analytics', 'Analytics'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=200, unique=True)
    processor_type = models.CharField(max_length=30, choices=PROCESSOR_TYPE_CHOICES, db_index=True)
    country = models.CharField(max_length=100, default='South Africa')
    is_cross_border = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, db_index=True)

    contact_name = models.CharField(max_length=200, blank=True)
    contact_email = models.EmailField(blank=True)
    website = models.URLField(blank=True)

    contract_reference = models.CharField(max_length=255, blank=True)
    contract_signed_at = models.DateField(null=True, blank=True)
    contract_expires_at = models.DateField(null=True, blank=True, db_index=True)

    data_categories = models.JSONField(
        default=list, blank=True,
        help_text='List of data categories shared with this processor.',
    )
    cross_border_justification = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'compliance_data_processors'
        ordering = ['processor_type', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_processor_type_display()})"

    @property
    def contract_expired(self) -> bool:
        if not self.contract_expires_at:
            return False
        return self.contract_expires_at < timezone.now().date()


class ComplianceTask(UUIDPrimaryKeyModel, TimeStampedModel):
    """A recurring or one-off compliance obligation."""
    FREQUENCY_CHOICES = [
        ('once', 'One-off'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('semi_annual', 'Semi-annual'),
        ('annual', 'Annual'),
        ('biennial', 'Every two years'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In progress'),
        ('done', 'Done'),
        ('overdue', 'Overdue'),
        ('not_applicable', 'Not applicable'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=40, choices=POLICY_CATEGORY_CHOICES, db_index=True)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='annual')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)

    due_date = models.DateField(db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='completed_compliance_tasks',
    )
    owner = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='owned_compliance_tasks',
    )

    evidence = models.TextField(blank=True)
    evidence_document = models.ForeignKey(
        'documents.Document', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='compliance_tasks',
    )
    related_policy = models.ForeignKey(
        CompliancePolicy, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='review_tasks',
    )

    class Meta:
        db_table = 'compliance_tasks'
        ordering = ['due_date']
        indexes = [
            models.Index(fields=['status', 'due_date']),
            models.Index(fields=['category', 'status']),
        ]

    def __str__(self):
        return f"{self.title} (due {self.due_date})"

    @property
    def is_overdue(self) -> bool:
        return (
            self.status not in ('done', 'not_applicable')
            and self.due_date < timezone.now().date()
        )


class DataSubjectRequest(UUIDPrimaryKeyModel, TimeStampedModel):
    """A data subject request under POPIA §23–24."""
    REQUEST_TYPE_CHOICES = [
        ('access', 'Access to data'),
        ('correction', 'Correction of data'),
        ('deletion', 'Deletion of data'),
        ('objection', 'Objection to processing'),
        ('portability', 'Portability'),
        ('withdraw_consent', 'Withdraw consent'),
    ]
    STATUS_CHOICES = [
        ('received', 'Received'),
        ('in_progress', 'In progress'),
        ('awaiting_verification', 'Awaiting verification'),
        ('completed', 'Completed'),
        ('refused', 'Refused'),
        ('withdrawn', 'Withdrawn'),
    ]

    client = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='data_subject_requests',
    )
    requestor_name = models.CharField(max_length=200)
    requestor_email = models.EmailField()
    requestor_phone = models.CharField(max_length=20, blank=True)

    request_type = models.CharField(max_length=30, choices=REQUEST_TYPE_CHOICES, db_index=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='received', db_index=True)

    received_at = models.DateTimeField(default=timezone.now)
    sla_due_at = models.DateTimeField(db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    assigned_to = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='assigned_dsars',
    )
    request_details = models.TextField()
    response_notes = models.TextField(blank=True)
    refusal_reason = models.TextField(blank=True)

    class Meta:
        db_table = 'compliance_data_subject_requests'
        ordering = ['-received_at']
        indexes = [
            models.Index(fields=['status', 'sla_due_at']),
        ]

    def __str__(self):
        return f"{self.get_request_type_display()} — {self.requestor_email}"

    @property
    def is_overdue(self) -> bool:
        if self.status in ('completed', 'refused', 'withdrawn'):
            return False
        return self.sla_due_at < timezone.now()


class SecurityIncident(UUIDPrimaryKeyModel, TimeStampedModel):
    """A security incident with POPIA §22 breach-notification tracking."""
    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('investigating', 'Investigating'),
        ('contained', 'Contained'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]
    INCIDENT_TYPE_CHOICES = [
        ('data_breach', 'Data breach'),
        ('unauthorised_access', 'Unauthorised access'),
        ('system_compromise', 'System compromise'),
        ('malware', 'Malware / ransomware'),
        ('phishing', 'Phishing / social engineering'),
        ('insider_threat', 'Insider threat'),
        ('denial_of_service', 'Denial of service'),
        ('physical', 'Physical security'),
        ('other', 'Other'),
    ]

    title = models.CharField(max_length=200)
    incident_type = models.CharField(max_length=30, choices=INCIDENT_TYPE_CHOICES, db_index=True)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open', db_index=True)

    detected_at = models.DateTimeField(default=timezone.now)
    reported_by = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='reported_incidents',
    )
    assigned_to = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='assigned_incidents',
    )

    description = models.TextField()
    affected_systems = models.JSONField(default=list, blank=True)
    affected_records_count = models.PositiveIntegerField(default=0)
    affected_data_categories = models.JSONField(default=list, blank=True)

    requires_notification = models.BooleanField(default=False)
    regulator_notified_at = models.DateTimeField(null=True, blank=True)
    subjects_notified_at = models.DateTimeField(null=True, blank=True)

    contained_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    root_cause = models.TextField(blank=True)
    remediation = models.TextField(blank=True)
    prevention_notes = models.TextField(blank=True)

    class Meta:
        db_table = 'compliance_security_incidents'
        ordering = ['-detected_at']
        indexes = [
            models.Index(fields=['status', 'severity']),
            models.Index(fields=['requires_notification', 'regulator_notified_at']),
        ]

    def __str__(self):
        return f"[{self.severity.upper()}] {self.title}"