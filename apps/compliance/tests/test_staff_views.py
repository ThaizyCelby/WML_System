"""Staff compliance view smoke tests."""
import pytest
from django.contrib.auth import get_user_model

from apps.compliance.models import (
    CompliancePolicy, ComplianceTask, SecurityIncident,
)

User = get_user_model()


@pytest.mark.django_db
class TestStaffComplianceViews:

    def _compliance_user(self, suffix=''):
        return User.objects.create_user(
            email=f'compliance{suffix}@test.com', password='TestPass123!',
            is_staff=True, is_superuser=True,
        )

    def test_dashboard_loads(self, client):
        staff = self._compliance_user('1')
        client.force_login(staff)
        resp = client.get('/staff/compliance/')
        assert resp.status_code == 200

    def test_policy_list_loads(self, client):
        staff = self._compliance_user('2')
        client.force_login(staff)
        resp = client.get('/staff/compliance/policies/')
        assert resp.status_code == 200

    def test_task_list_loads(self, client):
        staff = self._compliance_user('3')
        client.force_login(staff)
        resp = client.get('/staff/compliance/tasks/')
        assert resp.status_code == 200

    def test_task_update_marks_done(self, client):
        staff = self._compliance_user('4')
        client.force_login(staff)
        from datetime import date
        task = ComplianceTask.objects.create(
            title='X', category='popia', due_date=date.today(),
        )
        resp = client.post(
            f'/staff/compliance/tasks/{task.id}/update/',
            {'status': 'done', 'evidence': 'All good'},
        )
        assert resp.status_code == 302
        task.refresh_from_db()
        assert task.status == 'done'
        assert task.completed_by == staff

    def test_dsar_list_loads(self, client):
        staff = self._compliance_user('5')
        client.force_login(staff)
        resp = client.get('/staff/compliance/dsars/')
        assert resp.status_code == 200

    def test_incident_list_loads(self, client):
        staff = self._compliance_user('6')
        client.force_login(staff)
        resp = client.get('/staff/compliance/incidents/')
        assert resp.status_code == 200

    def test_incident_detail_loads(self, client):
        from apps.compliance.services import SecurityIncidentService
        staff = self._compliance_user('7')
        client.force_login(staff)
        incident = SecurityIncidentService.create_incident(
            title='Test', incident_type='other', severity='low',
            description='Y',
        )
        resp = client.get(f'/staff/compliance/incidents/{incident.id}/')
        assert resp.status_code == 200

    def test_processor_list_loads(self, client):
        staff = self._compliance_user('8')
        client.force_login(staff)
        resp = client.get('/staff/compliance/processors/')
        assert resp.status_code == 200
