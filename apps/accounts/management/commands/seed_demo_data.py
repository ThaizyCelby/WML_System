"""
Seed realistic demo data for QA and screenshots.

Creates:
  - 1 superuser, 1 credit officer, 1 compliance officer, 1 finance officer
  - 3 clients with complete profiles, consents, and documents
  - 4 loan products (already seeded by earlier migration)
  - Applications in various stages
  - An active loan with a repayment schedule
  - A completed bank statement with transactions
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import ClientProfile, Role, UserRole
from apps.documents.models import Document
from apps.loans.models import Loan, LoanApplication, LoanProduct
from apps.loans.services import LoanApplicationService
from apps.repayments.services import RepaymentScheduleService

User = get_user_model()


DEMO_PASSWORD = 'DemoPass2026!'


DEMO_USERS = [
    ('super@wethu.test',  'Super',  'Admin',  'Superuser'),
    ('credit@wethu.test', 'Credit', 'Officer', 'Credit Officer'),
    ('comp@wethu.test',   'Comp',   'Officer', 'Compliance Officer'),
    ('fin@wethu.test',    'Fin',    'Officer', 'Finance Officer'),
]


DEMO_CLIENTS = [
    {
        'email': 'thandi@wethu.test',
        'first_name': 'Thandi',
        'last_name': 'Mokoena',
        'phone_number': '+27123456001',
        'id_number': '9001015800087',
        'income': Decimal('25000.00'),
        'expenses': Decimal('8000.00'),
        'debt': Decimal('3000.00'),
        'employer': 'Acme Corp',
    },
    {
        'email': 'sipho@wethu.test',
        'first_name': 'Sipho',
        'last_name': 'Ndlovu',
        'phone_number': '+27123456002',
        'id_number': '8805055800081',
        'income': Decimal('18000.00'),
        'expenses': Decimal('6000.00'),
        'debt': Decimal('4500.00'),
        'employer': 'Beta Solutions',
    },
    {
        'email': 'naledi@wethu.test',
        'first_name': 'Naledi',
        'last_name': 'Dlamini',
        'phone_number': '+27123456003',
        'id_number': '9503035800085',
        'income': Decimal('32000.00'),
        'expenses': Decimal('9500.00'),
        'debt': Decimal('2000.00'),
        'employer': 'Gamma Industries',
    },
]


class Command(BaseCommand):
    help = 'Seed demo data for QA.'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true',
                            help='Overwrite existing demo users.')

    @transaction.atomic
    def handle(self, *args, **options):
        force = options['force']
        now = timezone.now().isoformat()

        # ── 1. Staff users + roles ─────────────────────────────
        for email, first, last, role_name in DEMO_USERS:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'first_name': first, 'last_name': last,
                    'is_active': True, 'is_staff': True,
                    'email_verified': True,
                },
            )
            if created or force:
                user.set_password(DEMO_PASSWORD)
                user.save()
            role, _ = Role.objects.get_or_create(
                name=role_name,
                defaults={'is_system_role': True, 'is_active': True},
            )
            UserRole.objects.get_or_create(user=user, role=role)
            self.stdout.write(self.style.SUCCESS(
                f"{'Created' if created else 'Existing'} staff: {email} ({role_name})"
            ))

        # ── 2. Clients ─────────────────────────────────────────
        client_users = []
        for c in DEMO_CLIENTS:
            user, created = User.objects.get_or_create(
                email=c['email'],
                defaults={
                    'first_name': c['first_name'],
                    'last_name': c['last_name'],
                    'phone_number': c['phone_number'],
                    'is_active': True,
                    'email_verified': True,
                },
            )
            if created or force:
                user.set_password(DEMO_PASSWORD)
                user.save()
            client_users.append(user)

            profile, _ = ClientProfile.objects.get_or_create(
                user=user,
                defaults={
                    'id_number': c['id_number'],
                    'date_of_birth': date(1990, 1, 1),
                    'employment_type': 'full_time',
                    'employer_name': c['employer'],
                    'monthly_income': c['income'],
                    'monthly_expenses': c['expenses'],
                    'existing_debt_obligations': c['debt'],
                    'residential_address': {
                        'street': '1 Demo Street',
                        'city': 'Pretoria',
                        'province': 'Gauteng',
                        'postal_code': '0001',
                    },
                    'consent_records': {
                        'credit_check_consent': {'granted': True, 'timestamp': now, 'version': '1.0'},
                        'affordability_consent': {'granted': True, 'timestamp': now, 'version': '1.0'},
                        'terms_accepted': {'granted': True, 'timestamp': now, 'version': '1.0'},
                        'privacy_accepted': {'granted': True, 'timestamp': now, 'version': '1.0'},
                    },
                    'kyc_status': 'verified',
                },
            )

            # Documents
            for dtype in ('identity_document', 'proof_of_address', 'payslip', 'bank_statement'):
                Document.objects.get_or_create(
                    client=user, document_type=dtype,
                    defaults={
                        'original_filename': f'{dtype}.pdf',
                        'mime_type': 'application/pdf',
                        'file_size': 1024,
                        'storage_key': f'demo/{dtype}-{user.id}.pdf',
                        'status': 'approved',
                        'virus_scan_status': 'clean',
                    },
                )
            self.stdout.write(self.style.SUCCESS(
                f"{'Created' if created else 'Existing'} client: {c['email']}"
            ))

        # ── 3. Applications + loans in various states ──────────
        products = list(LoanProduct.objects.filter(is_active=True))
        if not products:
            self.stdout.write(self.style.WARNING(
                'No loan products found. Run migrations or seed products first.'
            ))
            return

        staff = User.objects.get(email='credit@wethu.test')

        # Draft application
        LoanApplicationService.create_application(
            client_users[0], products[0].id, Decimal('5000.00'), 12,
        )

        # Approved + active loan with repayment schedule
        app = LoanApplicationService.create_application(
            client_users[1], products[0].id, Decimal('8000.00'), 6,
        )
        LoanApplicationService.submit_application(app, client_users[1])
        for status in ('document_review', 'kyc_review', 'affordability_review',
                       'credit_review', 'approved', 'contract_pending'):
            LoanApplicationService.transition(app, status, staff)
        app.refresh_from_db()
        if hasattr(app, 'loan'):
            loan = app.loan
            RepaymentScheduleService.generate_schedule(loan)
            loan.status = 'active'
            loan.save(update_fields=['status', 'updated_at'])

        self.stdout.write(self.style.SUCCESS('Demo data seeded.'))
        self.stdout.write('')
        self.stdout.write(f'Password for all demo accounts: {DEMO_PASSWORD}')
        self.stdout.write('')
        self.stdout.write('Demo accounts:')
        for email, _, _, role in DEMO_USERS:
            self.stdout.write(f'  {email:30s} → {role}')
        for c in DEMO_CLIENTS:
            self.stdout.write(f'  {c["email"]:30s} → Client')