from celery import shared_task
from django.core.management import call_command


@shared_task(name='apps.security.tasks.run_security_sweep')
def run_security_sweep():
    """Nightly security housekeeping."""
    call_command('purge_login_attempts', '--days', '30')
    return {'status': 'ok'}


@shared_task(name='apps.security.tasks.purge_login_attempts')
def purge_login_attempts():
    call_command('purge_login_attempts', '--days', '30')
