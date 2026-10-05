"""Admin-assisted MFA reset. Logs the action."""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import MFARecoveryCode
from apps.audit.services import AuditService


class Command(BaseCommand):
    help = 'Reset a user\'s MFA enrollment. Requires superuser context.'

    def add_arguments(self, parser):
        parser.add_argument('email', type=str, help='User email')

    def handle(self, *args, **options):
        User = get_user_model()
        email = options['email'].strip().lower()
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            raise CommandError(f'No user with email {email}.')

        was_enabled = user.mfa_enabled
        user.mfa_enabled = False
        user.mfa_secret = ''
        user.mfa_enrolled_at = None
        user.mfa_last_used_counter = None
        user.save(update_fields=[
            'mfa_enabled', 'mfa_secret', 'mfa_enrolled_at',
            'mfa_last_used_counter', 'updated_at',
        ])
        MFARecoveryCode.objects.filter(user=user).delete()

        AuditService.record(
            actor=None,  # command-line action
            action='mfa_reset_admin',
            object_type='user', object_id=str(user.id),
            after_value={'was_enabled': was_enabled},
        )
        self.stdout.write(self.style.SUCCESS(
            f'MFA reset for {email}. User must re-enroll at /mfa/setup/.'
        ))