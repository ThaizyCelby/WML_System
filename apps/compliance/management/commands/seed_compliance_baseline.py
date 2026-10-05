"""Seed baseline compliance policies and recurring tasks for a SA micro-lender."""
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.compliance.models import CompliancePolicy, ComplianceTask


POLICIES = [
    {
        'name': 'POPIA Privacy Notice',
        'category': 'popia',
        'version': '1.0',
        'summary': 'Client-facing notice of how personal information is collected, processed, and shared.',
    },
    {
        'name': 'PAIA Manual',
        'category': 'paia',
        'version': '1.0',
        'summary': 'Manual published under the Promotion of Access to Information Act.',
    },
    {
        'name': 'Data Retention Policy',
        'category': 'data_retention',
        'version': '1.0',
        'summary': 'Retention periods for client, transaction, and audit data.',
    },
    {
        'name': 'Information Security Policy',
        'category': 'information_security',
        'version': '1.0',
        'summary': 'Access control, encryption, incident response, and monitoring obligations.',
    },
    {
        'name': 'NCA Credit Provider Disclosure',
        'category': 'nca',
        'version': '1.0',
        'summary': 'National Credit Act disclosure requirements applicable to every loan offer.',
    },
    {
        'name': 'Complaints Procedure',
        'category': 'complaints',
        'version': '1.0',
        'summary': 'How client complaints are logged, escalated, and resolved.',
    },
    {
        'name': 'Responsible Lending Policy',
        'category': 'responsible_lending',
        'version': '1.0',
        'summary': 'Affordability assessment standards and lending limits.',
    },
]


TASKS = [
    # POPIA
    {'title': 'Review POPIA privacy notice', 'category': 'popia', 'frequency': 'annual', 'days_ahead': 90},
    {'title': 'Verify all data processor agreements signed & current', 'category': 'popia', 'frequency': 'semi_annual', 'days_ahead': 60},
    {'title': 'Review consent capture wording on client application', 'category': 'popia', 'frequency': 'annual', 'days_ahead': 120},
    # PAIA
    {'title': 'Submit PAIA annual report to Information Regulator', 'category': 'paia', 'frequency': 'annual', 'days_ahead': 180},
    {'title': 'Update PAIA manual (if any company details changed)', 'category': 'paia', 'frequency': 'annual', 'days_ahead': 150},
    # NCA
    {'title': 'Confirm NCR registration still active', 'category': 'nca', 'frequency': 'annual', 'days_ahead': 60},
    {'title': 'Review loan agreement template for NCA compliance', 'category': 'nca', 'frequency': 'annual', 'days_ahead': 120},
    # InfoSec
    {'title': 'Run quarterly access review for staff accounts', 'category': 'information_security', 'frequency': 'quarterly', 'days_ahead': 30},
    {'title': 'Test backup restore procedure', 'category': 'information_security', 'frequency': 'quarterly', 'days_ahead': 30},
    {'title': 'Review security incidents and lessons learned', 'category': 'information_security', 'frequency': 'quarterly', 'days_ahead': 45},
    # Complaints
    {'title': 'Review complaint resolution times vs SLA', 'category': 'complaints', 'frequency': 'quarterly', 'days_ahead': 45},
    # Data retention
    {'title': 'Review data retention register', 'category': 'data_retention', 'frequency': 'annual', 'days_ahead': 90},
    # Responsible lending
    {'title': 'Audit affordability engine results against policy', 'category': 'responsible_lending', 'frequency': 'semi_annual', 'days_ahead': 60},
]


class Command(BaseCommand):
    help = 'Seed baseline compliance policies and tasks.'

    @transaction.atomic
    def handle(self, *args, **options):
        today = date.today()

        self.stdout.write(self.style.HTTP_INFO('Seeding compliance policies...'))
        for p in POLICIES:
            policy, created = CompliancePolicy.objects.update_or_create(
                name=p['name'],
                defaults={
                    'category': p['category'],
                    'version': p['version'],
                    'summary': p['summary'],
                    'status': 'active',
                    'effective_date': today,
                    'next_review_date': today + timedelta(days=365),
                },
            )
            verb = 'Created' if created else 'Updated'
            self.stdout.write(f'  {verb}: {policy.name}')

        self.stdout.write(self.style.HTTP_INFO('Seeding compliance tasks...'))
        for t in TASKS:
            task, created = ComplianceTask.objects.get_or_create(
                title=t['title'],
                defaults={
                    'category': t['category'],
                    'frequency': t['frequency'],
                    'status': 'pending',
                    'due_date': today + timedelta(days=t['days_ahead']),
                },
            )
            verb = 'Created' if created else 'Exists'
            self.stdout.write(f'  {verb}: {task.title} (due {task.due_date})')

        self.stdout.write(self.style.SUCCESS('Done. Baseline compliance data seeded.'))