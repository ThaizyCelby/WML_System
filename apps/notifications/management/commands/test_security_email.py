"""Send a test security alert to the configured recipients."""
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Send a test security alert email to SECURITY_ALERT_RECIPIENTS.'

    def handle(self, *args, **options):
        recipients = getattr(settings, 'SECURITY_ALERT_RECIPIENTS', []) or []
        if not recipients:
            self.stdout.write(self.style.WARNING(
                'No recipients configured. Set SECURITY_ALERT_RECIPIENTS in .env.'
            ))
            return

        from django.contrib.auth import get_user_model
        from apps.notifications.services import NotificationService
        User = get_user_model()

        sent = 0
        for email in recipients:
            user = User.objects.filter(email__iexact=email, is_active=True).first()
            if not user:
                self.stdout.write(self.style.WARNING(f'No user with email {email}, skipping.'))
                continue
            try:
                NotificationService.dispatch(
                    user, 'security_alert',
                    context={
                        'event_type': 'test_alert',
                        'severity': 'critical',
                        'risk_score': 95,
                        'ip_address': '127.0.0.1',
                    },
                    channels=['email'],
                )
                sent += 1
                self.stdout.write(self.style.SUCCESS(f'Sent test alert to {email}.'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Failed for {email}: {e}'))

        self.stdout.write(self.style.SUCCESS(f'Done. {sent} sent.'))