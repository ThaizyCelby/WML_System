"""Signal handlers for the documents app."""
from django.core.cache import cache
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import Document


@receiver([post_save, post_delete], sender=Document)
def invalidate_missing_docs_cache(sender, instance, **kwargs):
    if instance.client_id:
        cache.delete(f"missing_docs:{instance.client_id}")