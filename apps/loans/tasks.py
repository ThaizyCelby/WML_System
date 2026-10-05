"""Celery tasks for the loans app."""
import logging

from celery import shared_task

logger = logging.getLogger('apps.loans')


@shared_task(name='apps.loans.tasks.recompute_default_risk')
def recompute_default_risk():
    """Nightly job — refresh default-risk scores for all open loans."""
    from .services import LoanService
    summary = LoanService.recompute_all_active_risks()
    logger.info("Default-risk recompute: %s", summary)
    return summary