"""Tests for the compliance module."""
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.compliance.models import (
    ComplianceTask, DataSubjectRequest, SecurityIncident,
)
from apps.compliance.services import (
    ComplianceService, DataSubjectRequestService, SecurityIncidentService,
)

User = get_user_model()


@pytest.mark.django_db
class TestComplianceTask:

    def test_is_overdue_property(self):
        today = timezone.now().date()
        task = ComplianceTask.objects.create(
            title='Test', category='popia', due_date=today - timedelta(days=1),
            status='pending',
        )
        assert task.is_overdue is True

        task.status = 'done'
        assert task.is_overdue is False

    def test_mark_overdue_tasks_flips_status(self):
        today = timezone.now().date()
        t1 = ComplianceTask.objects.create(
            title='Old', category='popia', due_date=today - timedelta(days=5),
            status='pending',
        )
        t2 = ComplianceTask.objects.create(
            title='Future', category='popia', due_date=today + timedelta(days=5),
            status='pending',
        )
        count = ComplianceService.mark_overdue_tasks()
        t1.refresh_from_db()
        t2.refresh_from_db()
        assert count >= 1
        assert t1.status == 'overdue'
        assert t2.status == 'pending'

    def test_task_stats(self):
        today = timezone.now().date()
        ComplianceTask.objects.create(
            title='A', category='popia', due_date=today, status='pending',
        )
        ComplianceTask.objects.create(
            title='B', category='popia', due_date=today, status='done',
        )
        stats = ComplianceService.task_stats()
        assert stats['pending'] >= 1
        assert stats['done'] >= 1


@pytest.mark.django_db
class TestDataSubjectRequest:

    def test_create_sets_sla(self):
        req = DataSubjectRequestService.create_request(
            requestor_name='Jane',
            requestor_email='jane@test.com',
            request_type='access',
            request_details='I want my data.',
        )
        assert req.sla_due_at > timezone.now()
        delta = req.sla_due_at - req.received_at
        assert 29 <= delta.days <= 30

    def test_create_rejects_missing_details(self):
        with pytest.raises(ValueError, match='details'):
            DataSubjectRequestService.create_request(
                requestor_name='Jane',
                requestor_email='jane@test.com',
                request_type='access',
                request_details='   ',
            )

    def test_complete_request(self):
        staff = User.objects.create_user(email='s@x.com', password='TestPass123!')
        req = DataSubjectRequestService.create_request(
            requestor_name='Jane', requestor_email='jane@test.com',
            request_type='access', request_details='data please',
        )
        DataSubjectRequestService.complete_request(
            req, staff, response_notes='Sent via email.',
        )
        req.refresh_from_db()
        assert req.status == 'completed'
        assert req.completed_at is not None

    def test_refuse_requires_reason(self):
        staff = User.objects.create_user(email='s@x.com', password='TestPass123!')
        req = DataSubjectRequestService.create_request(
            requestor_name='Jane', requestor_email='jane@test.com',
            request_type='deletion', request_details='delete me',
        )
        with pytest.raises(ValueError, match='reason'):
            DataSubjectRequestService.refuse_request(req, staff, reason='')


@pytest.mark.django_db
class TestSecurityIncident:

    def test_create_medium_severity_with_records_flags_notification(self):
        incident = SecurityIncidentService.create_incident(
            title='API key leak',
            incident_type='data_breach',
            severity='medium',
            description='Key leaked in logs.',
            affected_records_count=10,
        )
        assert incident.requires_notification is True

    def test_create_low_severity_no_notification(self):
        incident = SecurityIncidentService.create_incident(
            title='Port scan',
            incident_type='unauthorised_access',
            severity='low',
            description='Scanner detected.',
        )
        assert incident.requires_notification is False

    def test_create_high_severity_no_records_no_notification(self):
        incident = SecurityIncidentService.create_incident(
            title='Locked out admin',
            incident_type='insider_threat',
            severity='high',
            description='Admin was locked out.',
            affected_records_count=0,
        )
        assert incident.requires_notification is False

    def test_resolve_incident(self):
        actor = User.objects.create_user(email='r@x.com', password='TestPass123!')
        incident = SecurityIncidentService.create_incident(
            title='X', incident_type='other', severity='low',
            description='Y',
        )
        SecurityIncidentService.resolve_incident(
            incident, actor, root_cause='Config error', remediation='Fixed.',
        )
        incident.refresh_from_db()
        assert incident.status == 'resolved'
        assert incident.resolved_at is not None