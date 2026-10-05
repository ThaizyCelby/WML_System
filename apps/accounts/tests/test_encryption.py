"""Encryption-at-rest tests for ClientProfile PII."""
import pytest
from django.contrib.auth import get_user_model
from django.db import connection

from apps.accounts.models import ClientProfile
from core.crypto import blind_index, decrypt, encrypt

User = get_user_model()


@pytest.mark.django_db
class TestEncryptionFields:

    def _raw(self, profile_id, column):
        """
        Read the raw, on-disk value of a column, bypassing the model.

        SQLite stores UUIDField values as 32-char hex (no dashes), so the
        WHERE clause must use profile_id.hex, not str(profile_id).
        """
        with connection.cursor() as cur:
            cur.execute(
                f"SELECT {column} FROM client_profiles WHERE id = %s",
                [profile_id.hex],
            )
            row = cur.fetchone()
            return row[0] if row else None

    def _user(self, email):
        return User.objects.create_user(email=email, password='TestPass123!')

    def test_crypto_round_trip(self):
        ct = encrypt('hello-world')
        assert ct.startswith('gAAAAA')
        assert decrypt(ct) == 'hello-world'

    def test_crypto_is_idempotent(self):
        ct = encrypt('hello')
        assert encrypt(ct) == ct  # no double encryption

    def test_crypto_passes_plaintext_through(self):
        assert decrypt('plain-string') == 'plain-string'

    def test_blind_index_is_deterministic(self):
        a = blind_index('9001015800087')
        b = blind_index('9001015800087')
        c = blind_index('9001015800088')
        assert a == b
        assert a != c
        assert len(a) == 64

    def test_id_number_encrypted_at_rest(self):
        profile = ClientProfile.objects.create(
            user=self._user('enc1@test.com'),
            id_number='9001015800087',
        )
        raw = self._raw(profile.id, 'id_number')
        assert raw is not None
        assert '9001015800087' not in raw
        assert raw.startswith('gAAAAA')

    def test_id_number_round_trip(self):
        profile = ClientProfile.objects.create(
            user=self._user('enc2@test.com'),
            id_number='9001015800087',
        )
        profile.refresh_from_db()
        assert profile.id_number == '9001015800087'

    def test_blind_index_populated_on_save(self):
        profile = ClientProfile.objects.create(
            user=self._user('enc3@test.com'),
            id_number='9001015800087',
        )
        assert profile.id_number_index == blind_index('9001015800087')

    def test_blind_index_lookup(self):
        profile = ClientProfile.objects.create(
            user=self._user('enc4@test.com'),
            id_number='9001015800087',
        )
        found = ClientProfile.objects.filter(
            id_number_index=blind_index('9001015800087'),
        ).first()
        assert found is not None
        assert found.id == profile.id
        assert found.id_number == '9001015800087'

    def test_residential_address_encrypted_at_rest(self):
        addr = {'street': '1 Test St', 'city': 'Cape Town', 'postal': '8001'}
        profile = ClientProfile.objects.create(
            user=self._user('enc5@test.com'),
            residential_address=addr,
        )
        raw = self._raw(profile.id, 'residential_address')
        assert raw is not None
        assert 'Cape Town' not in raw
        assert raw.startswith('gAAAAA')

    def test_residential_address_round_trip(self):
        addr = {'street': '1 Test St', 'city': 'Cape Town', 'postal': '8001'}
        profile = ClientProfile.objects.create(
            user=self._user('enc6@test.com'),
            residential_address=addr,
        )
        profile.refresh_from_db()
        assert profile.residential_address == addr

    def test_id_number_change_updates_index(self):
        profile = ClientProfile.objects.create(
            user=self._user('enc7@test.com'),
            id_number='9001015800087',
        )
        old_index = profile.id_number_index
        profile.id_number = '9101015800088'
        profile.save()
        profile.refresh_from_db()
        assert profile.id_number_index != old_index
        assert profile.id_number_index == blind_index('9101015800088')