"""Compliance service layer."""
import logging
from datetime import timedelta

from django.utils import timezone

from apps.audit.services import AuditService

from .models import (
    ComplianceTask, DataSubjectRequest, SecurityIncident,
)

logger = logging.getLogger('apps.compliance')


# POPIA §23 — response window for data subject requests
DSAR_SLA_DAYS = 30


class ComplianceService:

    @staticmethod
    def mark_overdue_tasks() -> int:
        """Daily job — flip pending/in-progress tasks past due to 'overdue'."""
        today = timezone.now().date()
        count = (
            ComplianceTask.objects
            .filter(status__in=['pending', 'in_progress'], due_date__lt=today)
            .update(status='overdue')
        )
        return count

    @staticmethod
    def task_stats() -> dict:
        today = timezone.now().date()
        qs = ComplianceTask.objects.all()
        return {
            'pending': qs.filter(status='pending').count(),
            'in_progress': qs.filter(status='in_progress').count(),
            'overdue': qs.filter(status='overdue').count(),
            'done': qs.filter(status='done').count(),
            'due_soon': qs.filter(
                status__in=['pending', 'in_progress'],
                due_date__gte=today,
                due_date__lte=today + timedelta(days=30),
            ).count(),
        }


class DataSubjectRequestService:

    @staticmethod
    def create_request(
        *,
        client=None,
        requestor_name: str,
        requestor_email: str,
        requestor_phone: str = '',
        request_type: str,
        request_details: str,
        actor=None,
        ip_address=None,
    ) -> DataSubjectRequest:
        if not requestor_name or not requestor_email:
            raise ValueError('Requestor name and email are required.')
        if not request_details.strip():
            raise ValueError('Request details are required.')

        now = timezone.now()
        req = DataSubjectRequest.objects.create(
            client=client,
            requestor_name=requestor_name.strip()[:200],
            requestor_email=requestor_email.strip()[:254],
            requestor_phone=(requestor_phone or '').strip()[:20],
            request_type=request_type,
            request_details=request_details.strip(),
            received_at=now,
            sla_due_at=now + timedelta(days=DSAR_SLA_DAYS),
        )

        AuditService.record(
            actor=actor, action='dsar_received',
            object_type='data_subject_request', object_id=str(req.id),
            ip_address=ip_address,
            after_value={'type': request_type, 'requestor': requestor_email},
        )
        return req

    @staticmethod
    def complete_request(req: DataSubjectRequest, actor, *, response_notes: str = '',
                         ip_address=None) -> DataSubjectRequest:
        req.status = 'completed'
        req.completed_at = timezone.now()
        req.response_notes = response_notes
        req.save(update_fields=['status', 'completed_at', 'response_notes', 'updated_at'])

        AuditService.record(
            actor=actor, action='dsar_completed',
            object_type='data_subject_request', object_id=str(req.id),
            ip_address=ip_address,
        )
        return req

    @staticmethod
    def refuse_request(req: DataSubjectRequest, actor, *, reason: str, ip_address=None):
        if not reason:
            raise ValueError('A refusal reason is required.')
        req.status = 'refused'
        req.completed_at = timezone.now()
        req.refusal_reason = reason
        req.save(update_fields=['status', 'completed_at', 'refusal_reason', 'updated_at'])

        AuditService.record(
            actor=actor, action='dsar_refused',
            object_type='data_subject_request', object_id=str(req.id),
            ip_address=ip_address, after_value={'reason': reason},
        )
        return req


class SecurityIncidentService:

    @staticmethod
    def create_incident(
        *,
        title: str,
        incident_type: str,
        severity: str,
        description: str,
        affected_records_count: int = 0,
        affected_data_categories=None,
        affected_systems=None,
        reported_by=None,
        ip_address=None,
    ) -> SecurityIncident:
        if not title or not description:
            raise ValueError('Title and description are required.')

        # POPIA §22 — notification triggered for medium+ severity with affected records
        requires_notification = (
            severity in ('medium', 'high', 'critical')
            and affected_records_count > 0
        )

        incident = SecurityIncident.objects.create(
            title=title.strip()[:200],
            incident_type=incident_type,
            severity=severity,
            description=description.strip(),
            affected_records_count=affected_records_count,
            affected_data_categories=list(affected_data_categories or []),
            affected_systems=list(affected_systems or []),
            requires_notification=requires_notification,
            reported_by=reported_by,
            detected_at=timezone.now(),
        )

        AuditService.record(
            actor=reported_by, action='security_incident_reported',
            object_type='security_incident', object_id=str(incident.id),
            ip_address=ip_address,
            after_value={'severity': severity, 'type': incident_type,
                         'requires_notification': requires_notification},
        )
        return incident

    @staticmethod
    def mark_regulator_notified(incident: SecurityIncident, actor=None, ip_address=None):
        incident.regulator_notified_at = timezone.now()
        incident.save(update_fields=['regulator_notified_at', 'updated_at'])
        AuditService.record(
            actor=actor, action='incident_regulator_notified',
            object_type='security_incident', object_id=str(incident.id),
            ip_address=ip_address,
        )
        return incident

    @staticmethod
    def mark_subjects_notified(incident: SecurityIncident, actor=None, ip_address=None):
        incident.subjects_notified_at = timezone.now()
        incident.save(update_fields=['subjects_notified_at', 'updated_at'])
        AuditService.record(
            actor=actor, action='incident_subjects_notified',
            object_type='security_incident', object_id=str(incident.id),
            ip_address=ip_address,
        )
        return incident

    @staticmethod
    def resolve_incident(incident: SecurityIncident, actor, *, root_cause: str = '',
                         remediation: str = '', ip_address=None):
        incident.status = 'resolved'
        incident.resolved_at = timezone.now()
        incident.root_cause = root_cause
        incident.remediation = remediation
        incident.save(update_fields=[
            'status', 'resolved_at', 'root_cause', 'remediation', 'updated_at',
        ])
        AuditService.record(
            actor=actor, action='security_incident_resolved',
            object_type='security_incident', object_id=str(incident.id),
            ip_address=ip_address,
        )
        return incident