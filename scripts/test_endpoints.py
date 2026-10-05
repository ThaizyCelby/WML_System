"""
Exercise every endpoint flagged as untested in the handover report.

Usage (three equivalent ways):

    # 1. Standalone — bootstraps Django automatically:
    python scripts/test_endpoints.py

    # 2. Via manage.py shell (Django already configured):
    python manage.py shell < scripts/test_endpoints.py

    # 3. Explicit settings module:
    DJANGO_SETTINGS_MODULE=config.settings python scripts/test_endpoints.py

This module is safe to import — it does NOT execute any DB queries at
import time. Pytest can therefore collect it without a `db` fixture.
"""
import os
import sys

# ── Django bootstrap ────────────────────────────────────────────────
# Set the settings module before importing anything that touches models.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402

try:
    django.setup()
except RuntimeError:
    # Already configured — e.g. running inside `manage.py shell`.
    pass

# Now safe to import Django-dependent modules.
from django.contrib.auth import get_user_model  # noqa: E402
from django.test import Client  # noqa: E402

User = get_user_model()

PASS = '\033[92mPASS\033[0m'
FAIL = '\033[91mFAIL\033[0m'
INFO = '\033[94mINFO\033[0m'

results = {'pass': 0, 'fail': 0, 'info': 0}


def check(label, condition, extra=''):
    if condition:
        print(f'  [{PASS}] {label} {extra}')
        results['pass'] += 1
    else:
        print(f'  [{FAIL}] {label} {extra}')
        results['fail'] += 1


def info(msg):
    print(f'  [{INFO}] {msg}')
    results['info'] += 1


def run():
    client = Client()

    # ── Setup ───────────────────────────────────────────────
    print('\n=== Setup ===')
    staff = User.objects.filter(email='credit@wethu.test').first()
    client_user = User.objects.filter(email='thandi@wethu.test').first()
    if not staff or not client_user:
        print('Demo users not found. Run: python manage.py seed_demo_data')
        sys.exit(1)

    # ── 1. Client endpoints ─────────────────────────────────
    print('\n=== Client: profile completeness ===')
    client.force_login(client_user)
    r = client.get('/api/v1/kyc/profile-completeness/')
    check('GET profile-completeness', r.status_code == 200, f'({r.status_code})')
    if r.status_code == 200:
        info(f"complete={r.json().get('complete')} "
             f"gaps={len(r.json().get('gaps', []))}")

    print('\n=== Client: credit report ===')
    r = client.get('/api/v1/kyc/credit-report/latest/')
    check('GET credit-report/latest', r.status_code in (200, 404),
          f'({r.status_code})')

    r = client.post('/api/v1/kyc/credit-report/pull/')
    check('POST credit-report/pull', r.status_code in (200, 400, 503),
          f'({r.status_code})')

    print('\n=== Client: document replacement ===')
    doc = client_user.documents.filter(status='approved').first()
    if doc:
        r = client.get(f'/portal/documents/{doc.id}/request-replacement/')
        check('GET request-replacement form', r.status_code == 200,
              f'({r.status_code})')
    else:
        info('No approved doc found; skipping replacement test')

    print('\n=== Client: mandate flow ===')
    loan = client_user.loans.first()
    if loan:
        r = client.get(f'/portal/loans/{loan.id}/mandate/new/')
        check('GET mandate create form', r.status_code in (200, 302),
              f'({r.status_code})')
        r = client.get('/portal/mandates/')
        check('GET mandate list', r.status_code == 200, f'({r.status_code})')
    else:
        info('No loan for client; skipping mandate test')

    print('\n=== Client: notifications ===')
    r = client.get('/api/v1/notifications/list/unread_count/')
    check('GET unread_count', r.status_code == 200, f'({r.status_code})')
    r = client.post('/api/v1/notifications/list/mark_all_read/')
    check('POST mark_all_read', r.status_code == 200, f'({r.status_code})')
    r = client.get('/api/v1/notifications/preferences/')
    check('GET preferences', r.status_code == 200, f'({r.status_code})')

    # ── 2. Staff endpoints ──────────────────────────────────
    print('\n=== Staff: dashboard + queues ===')
    client.force_login(staff)
    for url in ['/staff/', '/staff/applications/', '/staff/kyc/',
                '/staff/documents/', '/staff/mandates/', '/staff/loans/',
                '/staff/collections/', '/staff/reconciliation/',
                '/staff/fraud/', '/staff/audit/']:
        r = client.get(url)
        check(f'GET {url}', r.status_code == 200, f'({r.status_code})')

    print('\n=== Staff: application review ===')
    app = client_user.loan_applications.first()
    if app:
        r = client.get(f'/staff/applications/{app.id}/')
        check('GET application detail', r.status_code == 200, f'({r.status_code})')

    print('\n=== Staff: reports ===')
    for url in ['/api/v1/reports/portfolio/',
                '/api/v1/reports/applications/?days=30',
                '/api/v1/reports/repayments/?days=30',
                '/api/v1/reports/delinquency/',
                '/api/v1/reports/reconciliation/',
                '/api/v1/reports/export_loans_csv/',
                '/api/v1/reports/export_repayments_csv/']:
        r = client.get(url)
        check(f'GET {url}', r.status_code in (200, 403), f'({r.status_code})')

    # ── 3. Summary ──────────────────────────────────────────
    print('\n=== Summary ===')
    print(f'  Pass: {results["pass"]}')
    print(f'  Fail: {results["fail"]}')
    print(f'  Info: {results["info"]}')
    if results['fail']:
        print('\nSome endpoints returned unexpected status codes.')
        print('Check the runserver terminal for the actual exceptions.')
    else:
        print('\nAll endpoints responded as expected.')


if __name__ == '__main__':
    run()