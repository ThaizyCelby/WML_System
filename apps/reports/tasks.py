"""Weekly AI-generated portfolio summary."""
import logging

from celery import shared_task

logger = logging.getLogger('apps.reports')


@shared_task(name='apps.reports.tasks.weekly_portfolio_summary')
def weekly_portfolio_summary():
    """
    Generate a narrative portfolio summary via the configured AI provider
    and dispatch it to admins as an email + in-app notification.
    """
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from apps.ai.services import AIService
    from apps.notifications.services import NotificationService
    from .services import ReportsService

    metrics = ReportsService.portfolio_health_metrics()

    provider = getattr(settings, 'AI_DEFAULT_PROVIDER', 'glm')

    # Compose an advisory run. If AI fails, we still email the raw metrics.
    narrative = None
    try:
        record = AIService.run_analysis(
            provider,
            [{'kind': 'portfolio_snapshot', 'metrics': metrics}],
            'general',
            input_ref=f'portfolio-summary-{metrics["as_of"][:10]}',
        )
        if record and record.output_data:
            narrative = record.output_data
    except Exception as e:
        logger.warning("Portfolio AI narrative failed: %s", e)

    subject = "Weekly portfolio summary — Wethu Micro Lenders"

    if narrative:
        body_lines = [
            f"Weekly portfolio summary ({metrics['as_of'][:10]})",
            "",
            "AI narrative:",
            str(narrative)[:4000],
            "",
            "Raw metrics:",
            f"- Loans: {metrics['loans']}",
            f"- Risk: {metrics['risk']}",
            f"- Applications (30d): {metrics['applications_last_30d']}",
            f"- Repayments (30d): {metrics['repayments_last_30d']}",
            f"- Reconciliation (7d): {metrics['reconciliation_last_7d']}",
            f"- Security (7d): {metrics['security_last_7d']}",
        ]
    else:
        body_lines = [
            f"Weekly portfolio summary ({metrics['as_of'][:10]})",
            "(AI narrative unavailable — showing raw metrics)",
            "",
            f"{metrics}",
        ]

    body = "\n".join(body_lines)

    # Email every configured recipient
    recipients = getattr(settings, 'SECURITY_ALERT_RECIPIENTS', [])
    User = get_user_model()
    sent = 0
    for email in recipients:
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if not user:
            continue
        try:
            NotificationService.dispatch(
                user,
                'portfolio_summary',
                context={
                    'name': user.full_name or user.email,
                    'week_of': metrics['as_of'][:10],
                    'body': body,
                },
                channels=['email', 'in_app'],
            )
            sent += 1
        except Exception as e:
            logger.exception("Portfolio summary dispatch failed for %s: %s", email, e)

    return {'metrics': metrics, 'narrative': bool(narrative), 'sent': sent}