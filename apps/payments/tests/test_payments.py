"""NuPay webhook security tests."""
import hashlib
import hmac
import time
from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.payments.providers.base import PaymentProviderError
from apps.payments.providers.nupay import NuPayProvider


def _make_provider(secret='test-secret'):
    return NuPayProvider({
        'endpoint': 'https://sandbox.nupay.test',
        'api_key': 'test-key',
        'api_secret': 'test-secret',
        'merchant_id': 'MID123',
        'webhook_secret': secret,
        'webhook_tolerance_seconds': 300,
    })


def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode('utf-8'), body, hashlib.sha256).hexdigest()


class TestSignatureVerification:

    def test_valid_signature(self):
        p = _make_provider()
        body = b'{"event":"payment.successful"}'
        sig = _sign(body, 'test-secret')
        assert p.verify_webhook_signature(body, sig) is True

    def test_invalid_signature(self):
        p = _make_provider()
        body = b'{"event":"payment.successful"}'
        assert p.verify_webhook_signature(body, 'deadbeef') is False

    def test_missing_signature_header(self):
        p = _make_provider()
        assert p.verify_webhook_signature(b'{}', '') is False

    def test_tampered_body_fails(self):
        p = _make_provider()
        body = b'{"event":"payment.successful"}'
        sig = _sign(body, 'test-secret')
        tampered = b'{"event":"payment.successful","amount":99999}'
        assert p.verify_webhook_signature(tampered, sig) is False

    @override_settings(DEBUG=True)
    def test_missing_secret_rejects(self):
        """
        Dev/test path: provider constructs with empty secret, but the
        webhook verifier must still fail-closed.
        """
        p = NuPayProvider({
            'endpoint': 'https://sandbox.nupay.test',
            'api_key': 'test-key',
            'merchant_id': 'MID123',
            'webhook_secret': '',
        })
        assert p.verify_webhook_signature(b'{}', 'anything') is False

class TestProductionFailFast:

    @override_settings(DEBUG=False)
    def test_missing_secret_in_production_raises(self):
        with pytest.raises(PaymentProviderError, match='NUPAY_WEBHOOK_SECRET'):
            NuPayProvider({
                'endpoint': 'https://sandbox.nupay.test',
                'api_key': 'test-key',
                'merchant_id': 'MID123',
                'webhook_secret': '',
            })

    @override_settings(DEBUG=True)
    def test_missing_secret_in_dev_allowed(self):
        p = NuPayProvider({
            'endpoint': 'https://sandbox.nupay.test',
            'api_key': 'test-key',
            'merchant_id': 'MID123',
            'webhook_secret': '',
        })
        assert p.webhook_secret == ''


class TestReplayProtection:

    def test_recent_timestamp_passes(self):
        p = _make_provider()
        now = int(time.time())
        payload = {'event': 'x', 'timestamp': now}
        assert p._check_replay(payload) is True

    def test_old_timestamp_rejected(self):
        p = _make_provider()
        old = int(time.time()) - 3600  # 1 hour ago, outside 5-min window
        payload = {'event': 'x', 'timestamp': old}
        assert p._check_replay(payload) is False

    def test_future_timestamp_rejected(self):
        p = _make_provider()
        future = int(time.time()) + 3600
        payload = {'event': 'x', 'timestamp': future}
        assert p._check_replay(payload) is False

    def test_no_timestamp_allows_through(self):
        """If the provider doesn't send a timestamp, we can't enforce replay."""
        p = _make_provider()
        assert p._check_replay({'event': 'x'}) is True

    def test_iso_timestamp_parsed(self):
        p = _make_provider()
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        assert p._check_replay({'timestamp': now_iso}) is True