"""Generate a fresh FIELD_ENCRYPTION_KEY for .env."""
from django.core.management.base import BaseCommand

from core.crypto import generate_key


class Command(BaseCommand):
    help = 'Print a new FIELD_ENCRYPTION_KEY. Paste it into .env.'

    def handle(self, *args, **options):
        self.stdout.write(generate_key())
