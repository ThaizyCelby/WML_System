from celery import shared_task
from django.contrib.auth import get_user_model

from apps.ai.services import AIService


@shared_task
def snapshot_all_clients():
    """Nightly: snapshot every active client."""
    User = get_user_model()
    count = 0
    for user in User.objects.filter(is_active=True, is_staff=False).iterator():
        try:
            AIService.snapshot_client_trends(user)
            count += 1
        except Exception:
            pass
    return f"Snapshotted {count} clients"


@shared_task
def analyze_trends_for_all():
    User = get_user_model()
    count = 0
    for user in User.objects.filter(is_active=True, is_staff=False).iterator():
        try:
            AIService.analyze_trend(user)
            count += 1
        except Exception:
            pass
    return f"Analyzed {count} trends"


@shared_task
def refresh_client_insights(client_id):
    User = get_user_model()
    user = User.objects.filter(id=client_id).first()
    if user:
        AIService.generate_client_insights(user)