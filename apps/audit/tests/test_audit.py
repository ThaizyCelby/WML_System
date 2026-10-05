"""Tests for audit logging."""
import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestAuditLogging:

    def test_audit_log_created(self, regular_user):
        """Test that audit logs are created correctly."""
        from apps.audit.services import AuditService
        from apps.audit.models import AuditLog

        entry = AuditService.record(
            actor=regular_user,
            action='test_action',
            object_type='test_object',
            object_id='test-id',
            ip_address='127.0.0.1',
            description='Test audit entry',
        )

        assert entry is not None
        assert AuditLog.objects.count() == 1
        assert entry.actor_email == regular_user.email
        assert entry.action == 'test_action'

    def test_audit_log_immutable(self, db):
        """Test that audit logs cannot be modified."""
        from apps.audit.models import AuditLog

        entry = AuditLog.objects.create(
            action='test',
            object_type='test',
            object_id='test',
        )

        # Attempt to modify
        entry.description = 'modified'
        with pytest.raises(ValueError):
            entry.save()

    def test_audit_log_cannot_be_deleted(self, db):
        """Test that audit logs cannot be deleted."""
        from apps.audit.models import AuditLog

        entry = AuditLog.objects.create(
            action='test',
            object_type='test',
            object_id='test',
        )

        with pytest.raises(ValueError):
            entry.delete()
