"""Verify audit log immutability."""
import pytest
from apps.audit.models import AuditLog


@pytest.mark.django_db
class TestAuditImmutability:

    def test_audit_cannot_be_modified(self):
        entry = AuditLog.objects.create(action='test', object_type='x', object_id='1')
        entry.description = 'hacked'
        with pytest.raises(ValueError):
            entry.save()

    def test_audit_cannot_be_deleted(self):
        entry = AuditLog.objects.create(action='test', object_type='x', object_id='1')
        with pytest.raises(ValueError):
            entry.delete()
