from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.security.models import LoginAttempt


class Command(BaseCommand):
    help = 'Delete login attempts older than N days (default 30).'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=30)

    def handle(self, *args, **options):
        days = options['days']
        cutoff = timezone.now() - timezone.timedelta(days=days)
        deleted, _ = LoginAttempt.objects.filter(created_at__lt=cutoff).delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} login attempts older than {days} days."))
