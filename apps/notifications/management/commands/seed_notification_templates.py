from django.core.management.base import BaseCommand
from apps.notifications.services import NotificationService


class Command(BaseCommand):
    help = 'Seed default notification templates.'

    def handle(self, *args, **opts):
        NotificationService.ensure_default_templates()
        self.stdout.write(self.style.SUCCESS("Notification templates seeded."))
