"""Idempotent superuser bootstrap.

Reads SUPERUSER_EMAIL and SUPERUSER_INITIAL_PASSWORD from environment
variables. Never hard-codes credentials. Never logs the password.
Safe to run repeatedly.
"""
import logging
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = (
        'Create or update the platform superuser from environment '
        'variables. Idempotent — safe to run repeatedly.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--email', type=str, default=None,
                            help='Override SUPERUSER_EMAIL env var.')
        parser.add_argument('--password', type=str, default=None,
                            help='Override SUPERUSER_INITIAL_PASSWORD env var.')
        parser.add_argument('--force-password-reset', action='store_true',
                            help='Reset the password even if the user exists.')

    @transaction.atomic
    def handle(self, *args, **options):
        email = (options.get('email')
                 or os.environ.get('SUPERUSER_EMAIL') or '').strip().lower()
        password = (options.get('password')
                    or os.environ.get('SUPERUSER_INITIAL_PASSWORD') or '').strip()

        if not email:
            raise CommandError(
                'No email supplied. Set SUPERUSER_EMAIL in the environment '
                'or pass --email=user@example.com'
            )

        existing = User.objects.filter(email=email).first()
        if not existing and not password:
            raise CommandError(
                'No password supplied and the user does not exist. Set '
                'SUPERUSER_INITIAL_PASSWORD in the environment.'
            )

        if password and len(password) < 12:
            raise CommandError('Password must be at least 12 characters.')

        if existing:
            changed = False
            if not existing.is_superuser:
                existing.is_superuser = True
                changed = True
            if not existing.is_staff:
                existing.is_staff = True
                changed = True
            if not existing.is_active:
                existing.is_active = True
                changed = True
            if not existing.email_verified:
                existing.email_verified = True
                changed = True
            if options.get('force_password_reset') and password:
                existing.set_password(password)
                changed = True
            if changed:
                existing.save()
                self.stdout.write(self.style.SUCCESS(
                    f'Updated existing user {email} → superuser.'
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f'Superuser {email} already exists and is correctly configured.'
                ))
            return

        user = User.objects.create_superuser(
            email=email,
            password=password,
            first_name=os.environ.get('SUPERUSER_FIRST_NAME', 'Platform'),
            last_name=os.environ.get('SUPERUSER_LAST_NAME', 'Administrator'),
        )
        user.email_verified = True
        user.is_active = True
        user.save(update_fields=['email_verified', 'is_active', 'updated_at'])

        self.stdout.write(self.style.SUCCESS(f'Created superuser {email}'))
        self.stdout.write(self.style.WARNING(
            'The password was NOT logged. Change it after first login.'
        ))