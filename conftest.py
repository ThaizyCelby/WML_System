"""Pytest fixtures shared across the entire test suite."""
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

User = get_user_model()


# ── HTTP clients ──────────────────────────────────────────────────
@pytest.fixture
def api_client():
    """Unauthenticated API client."""
    return APIClient()


@pytest.fixture
def authenticated_client(db, regular_user):
    """Authenticated API client (regular user)."""
    client = APIClient()
    client.force_authenticate(user=regular_user)
    return client


@pytest.fixture
def superuser_client(db, superuser):
    """API client authenticated as a superuser."""
    client = APIClient()
    client.force_authenticate(user=superuser)
    return client


# ── Users ─────────────────────────────────────────────────────────
@pytest.fixture
def superuser(db):
    return User.objects.create_superuser(
        email='admin@wethu.test',
        password='SuperSecurePass123!',
        first_name='Admin',
        last_name='User',
    )


@pytest.fixture
def regular_user(db):
    return User.objects.create_user(
        email='client@wethu.test',
        password='ClientPass123!',
        first_name='Client',
        last_name='User',
        phone_number='+27123456789',
    )


@pytest.fixture
def complete_client(db):
    """
    A client whose profile is complete, consents given, and required
    documents approved. Ready to submit a loan application.
    """
    from apps.accounts.models import ClientProfile
    from apps.documents.models import Document

    user = User.objects.create_user(
        email='complete@wethu.test',
        password='ClientPass123!',
        first_name='Complete',
        last_name='Client',
        phone_number='+27123456780',
    )

    now = timezone.now().isoformat()
    ClientProfile.objects.create(
        user=user,
        id_number='9001015800087',
        date_of_birth=date(1990, 1, 1),
        employment_type='full_time',
        employer_name='Acme Corp',
        monthly_income=Decimal('20000.00'),
        monthly_expenses=Decimal('7000.00'),
        existing_debt_obligations=Decimal('5000.00'),
        residential_address={'street': '1 Test St', 'city': 'Pretoria'},
        consent_records={
            'credit_check_consent': {'granted': True, 'timestamp': now, 'version': '1.0'},
            'affordability_consent': {'granted': True, 'timestamp': now, 'version': '1.0'},
            'terms_accepted': {'granted': True, 'timestamp': now, 'version': '1.0'},
            'privacy_accepted': {'granted': True, 'timestamp': now, 'version': '1.0'},
        },
    )

    for dtype in ('identity_document', 'proof_of_address', 'payslip', 'bank_statement'):
        Document.objects.create(
            client=user,
            document_type=dtype,
            original_filename=f'{dtype}.pdf',
            mime_type='application/pdf',
            file_size=100,
            storage_key=f'test/{dtype}-{user.id}.pdf',
            status='approved',
            virus_scan_status='clean',
        )

    return user