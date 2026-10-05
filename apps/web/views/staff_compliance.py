"""Staff compliance views: dashboard, policies, tasks, DSARs, incidents, processors."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.audit.services import AuditService
from apps.compliance.models import (
    CompliancePolicy, ComplianceTask, DataProcessor,
    DataSubjectRequest, SecurityIncident,
)
from apps.compliance.services import (
    ComplianceService, DataSubjectRequestService, SecurityIncidentService,
)


COMPLIANCE_ROLES = ('Administrator', 'Compliance Officer', 'Auditor')


def _has_any(user, roles):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return any(user.has_role(r) for r in roles)


def _guard(request, roles=COMPLIANCE_ROLES):
    if _has_any(request.user, roles):
        return None
    messages.error(request, 'You do not have permission to access compliance.')
    return redirect('portal_dashboard')


# ──────────────────────────────────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────────────────────────────────
@login_required
def compliance_dashboard(request):
    g = _guard(request)
    if g:
        return g

    today = timezone.now().date()

    policy_stats = {
        'active': CompliancePolicy.objects.filter(status='active').count(),
        'review_due': CompliancePolicy.objects.filter(
            status='active', next_review_date__lte=today,
        ).count(),
    }

    task_stats = ComplianceService.task_stats()

    dsar_stats = {
        'open': DataSubjectRequest.objects.exclude(
            status__in=['completed', 'refused', 'withdrawn'],
        ).count(),
        'overdue': DataSubjectRequest.objects.filter(
            sla_due_at__lt=timezone.now(),
        ).exclude(status__in=['completed', 'refused', 'withdrawn']).count(),
    }

    incident_stats = {
        'open': SecurityIncident.objects.exclude(
            status__in=['resolved', 'closed'],
        ).count(),
        'notification_pending': SecurityIncident.objects.filter(
            requires_notification=True,
            regulator_notified_at__isnull=True,
        ).exclude(status__in=['resolved', 'closed']).count(),
    }

    recent_tasks = ComplianceTask.objects.filter(
        status__in=['pending', 'in_progress', 'overdue'],
    ).order_by('due_date')[:5]

    recent_dsars = DataSubjectRequest.objects.exclude(
        status__in=['completed', 'refused', 'withdrawn'],
    ).order_by('sla_due_at')[:5]

    recent_incidents = SecurityIncident.objects.exclude(
        status__in=['resolved', 'closed'],
    ).order_by('-detected_at')[:5]

    return render(request, 'staff/compliance/dashboard.html', {
        'policy_stats': policy_stats,
        'task_stats': task_stats,
        'dsar_stats': dsar_stats,
        'incident_stats': incident_stats,
        'recent_tasks': recent_tasks,
        'recent_dsars': recent_dsars,
        'recent_incidents': recent_incidents,
    })


# ──────────────────────────────────────────────────────────────────────
# Policies
# ──────────────────────────────────────────────────────────────────────
@login_required
def policy_list(request):
    g = _guard(request, COMPLIANCE_ROLES + ('Administrator',))
    if g:
        return g

    qs = CompliancePolicy.objects.all().order_by('category', '-effective_date')

    category = request.GET.get('category', '')
    if category:
        qs = qs.filter(category=category)

    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)

    page = Paginator(qs, 25).get_page(request.GET.get('page'))

    return render(request, 'staff/compliance/policy_list.html', {
        'page': page,
        'category_filter': category,
        'status_filter': status,
        'categories': CompliancePolicy._meta.get_field('category').choices,
        'statuses': CompliancePolicy._meta.get_field('status').choices,
    })


# ──────────────────────────────────────────────────────────────────────
# Tasks
# ──────────────────────────────────────────────────────────────────────
@login_required
def task_list(request):
    g = _guard(request)
    if g:
        return g

    qs = ComplianceTask.objects.select_related('owner', 'completed_by').order_by('due_date')

    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)

    category = request.GET.get('category', '')
    if category:
        qs = qs.filter(category=category)

    page = Paginator(qs, 25).get_page(request.GET.get('page'))
    stats = ComplianceService.task_stats()

    return render(request, 'staff/compliance/task_list.html', {
        'page': page,
        'stats': stats,
        'status_filter': status,
        'category_filter': category,
        'categories': ComplianceTask._meta.get_field('category').choices,
        'statuses': ComplianceTask._meta.get_field('status').choices,
    })


@require_POST
@login_required
def task_update(request, task_id):
    g = _guard(request)
    if g:
        return g

    task = get_object_or_404(ComplianceTask, id=task_id)
    new_status = (request.POST.get('status') or '').strip()
    evidence = (request.POST.get('evidence') or '').strip()

    valid_statuses = dict(ComplianceTask.STATUS_CHOICES)
    if new_status not in valid_statuses:
        messages.error(request, 'Invalid status.')
        return redirect('staff_compliance_tasks')

    old = task.status
    task.status = new_status
    updates = ['status', 'updated_at']

    if new_status == 'done':
        task.completed_at = timezone.now()
        task.completed_by = request.user
        updates += ['completed_at', 'completed_by']

    if evidence:
        task.evidence = evidence
        updates.append('evidence')

    task.save(update_fields=updates)

    AuditService.record(
        actor=request.user, action='compliance_task_updated',
        object_type='compliance_task', object_id=str(task.id),
        ip_address=request.META.get('REMOTE_ADDR'),
        before_value={'status': old}, after_value={'status': new_status},
    )
    messages.success(request, f'Task marked as {new_status}.')
    return redirect('staff_compliance_tasks')


# ──────────────────────────────────────────────────────────────────────
# Data Subject Requests (DSARs)
# ──────────────────────────────────────────────────────────────────────
@login_required
def dsar_list(request):
    g = _guard(request)
    if g:
        return g

    qs = DataSubjectRequest.objects.select_related('client', 'assigned_to').order_by('-received_at')

    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)

    page = Paginator(qs, 25).get_page(request.GET.get('page'))

    return render(request, 'staff/compliance/dsar_list.html', {
        'page': page,
        'status_filter': status,
        'statuses': DataSubjectRequest._meta.get_field('status').choices,
    })


@login_required
def dsar_detail(request, dsar_id):
    g = _guard(request)
    if g:
        return g

    req = get_object_or_404(
        DataSubjectRequest.objects.select_related('client', 'assigned_to'),
        id=dsar_id,
    )
    return render(request, 'staff/compliance/dsar_detail.html', {'dsar': req})


@require_POST
@login_required
def dsar_complete(request, dsar_id):
    g = _guard(request)
    if g:
        return g

    req = get_object_or_404(DataSubjectRequest, id=dsar_id)
    notes = (request.POST.get('response_notes') or '').strip()

    DataSubjectRequestService.complete_request(
        req, request.user, response_notes=notes,
        ip_address=request.META.get('REMOTE_ADDR'),
    )
    messages.success(request, 'DSAR marked complete.')
    return redirect('staff_compliance_dsar_detail', dsar_id=req.id)


@require_POST
@login_required
def dsar_refuse(request, dsar_id):
    g = _guard(request)
    if g:
        return g

    req = get_object_or_404(DataSubjectRequest, id=dsar_id)
    reason = (request.POST.get('reason') or '').strip()

    try:
        DataSubjectRequestService.refuse_request(
            req, request.user, reason=reason,
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        messages.success(request, 'DSAR refused.')
    except ValueError as e:
        messages.error(request, str(e))

    return redirect('staff_compliance_dsar_detail', dsar_id=req.id)


# ──────────────────────────────────────────────────────────────────────
# Security Incidents
# ──────────────────────────────────────────────────────────────────────
@login_required
def incident_list(request):
    g = _guard(request)
    if g:
        return g

    qs = SecurityIncident.objects.select_related('assigned_to', 'reported_by').order_by('-detected_at')

    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)

    severity = request.GET.get('severity', '')
    if severity:
        qs = qs.filter(severity=severity)

    page = Paginator(qs, 25).get_page(request.GET.get('page'))

    return render(request, 'staff/compliance/incident_list.html', {
        'page': page,
        'status_filter': status,
        'severity_filter': severity,
        'statuses': SecurityIncident._meta.get_field('status').choices,
        'severities': SecurityIncident._meta.get_field('severity').choices,
    })


@login_required
def incident_detail(request, incident_id):
    g = _guard(request)
    if g:
        return g

    incident = get_object_or_404(
        SecurityIncident.objects.select_related('assigned_to', 'reported_by'),
        id=incident_id,
    )
    return render(request, 'staff/compliance/incident_detail.html', {'incident': incident})


@require_POST
@login_required
def incident_action(request, incident_id):
    g = _guard(request)
    if g:
        return g

    incident = get_object_or_404(SecurityIncident, id=incident_id)
    action = request.POST.get('action', '')

    try:
        if action == 'assign':
            incident.assigned_to = request.user
            incident.status = 'investigating'
            incident.save(update_fields=['assigned_to', 'status', 'updated_at'])
            messages.success(request, 'Incident assigned to you.')

        elif action == 'notify_regulator':
            SecurityIncidentService.mark_regulator_notified(
                incident, request.user, ip_address=request.META.get('REMOTE_ADDR'),
            )
            messages.success(request, 'Regulator notification recorded.')

        elif action == 'notify_subjects':
            SecurityIncidentService.mark_subjects_notified(
                incident, request.user, ip_address=request.META.get('REMOTE_ADDR'),
            )
            messages.success(request, 'Subject notification recorded.')

        elif action == 'resolve':
            SecurityIncidentService.resolve_incident(
                incident, request.user,
                root_cause=(request.POST.get('root_cause') or '').strip(),
                remediation=(request.POST.get('remediation') or '').strip(),
                ip_address=request.META.get('REMOTE_ADDR'),
            )
            messages.success(request, 'Incident resolved.')

        else:
            messages.error(request, f'Unknown action: {action}')
    except ValueError as e:
        messages.error(request, str(e))

    return redirect('staff_compliance_incident_detail', incident_id=incident.id)


# ──────────────────────────────────────────────────────────────────────
# Data Processors
# ──────────────────────────────────────────────────────────────────────
@login_required
def processor_list(request):
    g = _guard(request)
    if g:
        return g

    qs = DataProcessor.objects.order_by('processor_type', 'name')

    processor_type = request.GET.get('type', '')
    if processor_type:
        qs = qs.filter(processor_type=processor_type)

    page = Paginator(qs, 25).get_page(request.GET.get('page'))

    return render(request, 'staff/compliance/processor_list.html', {
        'page': page,
        'type_filter': processor_type,
        'types': DataProcessor._meta.get_field('processor_type').choices,
    })