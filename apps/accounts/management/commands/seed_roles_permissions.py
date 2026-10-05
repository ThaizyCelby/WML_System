"""Management command to seed the standard roles and permissions."""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Permission, Role, RolePermission


# The twelve roles from the platform specification
ROLES = [
    {
        'name': 'Super Administrator',
        'description': 'Highest privilege level. Full system access.',
        'is_system_role': True,
    },
    {
        'name': 'Administrator',
        'description': 'Manages users, vendors, and system configuration.',
        'is_system_role': True,
    },
    {
        'name': 'Credit Officer',
        'description': 'Reviews and decisions loan applications.',
        'is_system_role': True,
    },
    {
        'name': 'Compliance Officer',
        'description': 'Ensures regulatory compliance and verifies KYC.',
        'is_system_role': True,
    },
    {
        'name': 'Finance Officer',
        'description': 'Manages financial operations and reconciliation.',
        'is_system_role': True,
    },
    {
        'name': 'Collections Officer',
        'description': 'Manages overdue loans and collections.',
        'is_system_role': True,
    },
    {
        'name': 'Support Agent',
        'description': 'Handles client support tickets.',
        'is_system_role': True,
    },
    {
        'name': 'Auditor',
        'description': 'Read-only access to all records and audit logs.',
        'is_system_role': True,
    },
    {
        'name': 'Vendor Administrator',
        'description': 'Manages vendor staff and loan products (tenant-scoped).',
        'is_system_role': True,
    },
    {
        'name': 'Vendor Staff',
        'description': 'Vendor employee with limited access (tenant-scoped).',
        'is_system_role': True,
    },
    {
        'name': 'Client',
        'description': 'End user who applies for loans.',
        'is_system_role': True,
    },
]


# Custom permissions beyond Django's per-model defaults.
# Format: (codename, name, app_label)
CUSTOM_PERMISSIONS = [
    # Loans
    ('approve_loan_application', 'Can approve loan applications', 'loans'),
    ('reject_loan_application', 'Can reject loan applications', 'loans'),
    ('override_affordability', 'Can override affordability decision', 'loans'),
    ('adjust_repayment_schedule', 'Can adjust loan repayment schedules', 'loans'),
    ('write_off_loan', 'Can write off a loan', 'loans'),

    # KYC / Compliance
    ('verify_kyc', 'Can verify client KYC', 'kyc'),
    ('review_documents', 'Can approve/reject client documents', 'documents'),
    ('approve_document_replacement', 'Can approve document replacement requests', 'documents'),
    ('manage_retention_policies', 'Can manage data retention policies', 'compliance'),

    # Payments / Finance
    ('activate_mandate', 'Can activate a debit mandate', 'payments'),
    ('reject_mandate', 'Can reject a debit mandate', 'payments'),
    ('process_repayment', 'Can manually process repayments', 'repayments'),
    ('run_reconciliation', 'Can trigger reconciliation', 'payments'),
    ('view_financial_reports', 'Can view financial reports', 'reports'),

    # Collections
    ('manage_collections', 'Can manage collections workflows', 'repayments'),
    ('create_payment_plan', 'Can create payment plans', 'repayments'),

    # Security / Fraud
    ('view_fraud_alerts', 'Can view fraud alerts', 'security'),
    ('resolve_fraud_alerts', 'Can resolve fraud alerts', 'security'),
    ('manage_blocked_ips', 'Can manage blocked IP addresses', 'security'),
    ('view_security_events', 'Can view security events', 'security'),
    ('suspend_account', 'Can suspend user accounts', 'security'),

    # Audit
    ('view_audit_logs', 'Can view audit logs', 'audit'),

    # Users / Vendors
    ('manage_users', 'Can create/edit/disable user accounts', 'accounts'),
    ('manage_roles', 'Can assign roles to users', 'accounts'),
    ('manage_vendors', 'Can create/edit vendors', 'vendors'),

    # System
    ('manage_system_settings', 'Can modify system-wide settings', 'accounts'),
    ('manage_ai_providers', 'Can configure AI provider settings', 'ai'),
    ('manage_feature_flags', 'Can toggle feature flags', 'accounts'),
]


# Role -> permission mapping. Roles not listed get no extra permissions.
ROLE_PERMISSIONS = {
    'Credit Officer': [
        'approve_loan_application', 'reject_loan_application',
        'override_affordability', 'review_documents', 'view_fraud_alerts',
    ],
    'Compliance Officer': [
        'verify_kyc', 'review_documents', 'manage_retention_policies',
        'approve_document_replacement', 'view_audit_logs',
        'view_security_events', 'view_fraud_alerts', 'resolve_fraud_alerts',
    ],
    'Finance Officer': [
        'activate_mandate', 'reject_mandate', 'process_repayment',
        'run_reconciliation', 'view_financial_reports',
        'adjust_repayment_schedule',
    ],
    'Collections Officer': [
        'manage_collections', 'create_payment_plan',
        'view_financial_reports', 'adjust_repayment_schedule',
    ],
    'Support Agent': [
        'view_fraud_alerts',
    ],
    'Auditor': [
        'view_audit_logs', 'view_financial_reports',
        'view_security_events', 'view_fraud_alerts',
    ],
    'Administrator': [
        # Users / config
        'manage_users', 'manage_roles', 'manage_vendors',
        'manage_system_settings', 'manage_ai_providers', 'manage_feature_flags',
        # Security
        'manage_blocked_ips', 'suspend_account',
        'view_security_events', 'view_fraud_alerts', 'resolve_fraud_alerts',
        # Operations
        'review_documents', 'verify_kyc',
        'activate_mandate', 'reject_mandate',
        'approve_loan_application', 'reject_loan_application',
        'override_affordability',
        # Reporting
        'view_audit_logs', 'view_financial_reports',
    ],
    # Super Administrator bypasses all permission checks via is_superuser
    # Vendor Administrator, Vendor Staff, Client get no global permissions
    # (their access is object-scoped at runtime)
}


class Command(BaseCommand):
    help = 'Seed default roles, permissions, and role-permission mappings.'

    @transaction.atomic
    def handle(self, *args, **options):
        # 1. Roles
        self.stdout.write(self.style.HTTP_INFO('Seeding roles...'))
        for role_data in ROLES:
            role, created = Role.objects.update_or_create(
                name=role_data['name'],
                defaults={
                    'description': role_data['description'],
                    'is_system_role': role_data['is_system_role'],
                    'is_active': True,
                },
            )
            verb = 'Created' if created else 'Updated'
            self.stdout.write(f'  {verb} role: {role.name}')

        # 2. Custom permissions
        self.stdout.write(self.style.HTTP_INFO('Seeding permissions...'))
        for codename, name, app_label in CUSTOM_PERMISSIONS:
            perm, created = Permission.objects.update_or_create(
                codename=codename,
                defaults={
                    'name': name,
                    'app_label': app_label,
                    'is_active': True,
                },
            )
            verb = 'Created' if created else 'Updated'
            self.stdout.write(f'  {verb} permission: {app_label}.{codename}')

        # 3. Role -> Permission mappings
        self.stdout.write(self.style.HTTP_INFO('Linking roles to permissions...'))
        for role_name, codenames in ROLE_PERMISSIONS.items():
            try:
                role = Role.objects.get(name=role_name)
            except Role.DoesNotExist:
                self.stdout.write(self.style.WARNING(
                    f'  Skipping {role_name}: role not found'
                ))
                continue

            # Remove stale permissions for this role
            RolePermission.objects.filter(role=role).exclude(
                permission__codename__in=codenames,
            ).delete()

            for codename in codenames:
                try:
                    perm = Permission.objects.get(codename=codename)
                except Permission.DoesNotExist:
                    self.stdout.write(self.style.WARNING(
                        f'  Skipping {role_name}/{codename}: permission not found'
                    ))
                    continue
                RolePermission.objects.get_or_create(role=role, permission=perm)

            self.stdout.write(
                f'  Linked {len(codenames)} permissions to {role_name}'
            )

        self.stdout.write(self.style.SUCCESS(
            'Done. Roles, permissions, and mappings seeded.'
        ))