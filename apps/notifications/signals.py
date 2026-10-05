"""Invalidate the unread-notification cache when notifications change."""
from django.core.cache import cache
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import Notification


@receiver([post_save, post_delete], sender=Notification)
def invalidate_unread_cache(sender, instance, **kwargs):
    if instance.user_id:
        cache.delete(f"unread_count:{instance.user_id}")