"""Tests for BankAccount — encryption, last-4, primary demotion."""
import pytest

from apps.accounts.models import BankAccount, Organisation, User


@pytest.fixture
def org(db):
    return Organisation.objects.create(name='Test Org', slug='test-org')


@pytest.fixture
def bank_client(db, org):
    return User.objects.create_user(
        email='bankclient@wethu.test',
        password='TestPass123!',
        organisation=org,
    )


@pytest.mark.django_db
class TestBankAccount:

    def test_last4_extracted_on_save(self, bank_client):
        acc = BankAccount.objects.create(
            client=bank_client,
            bank_name='Capitec',
            account_holder_name='John Doe',
            account_number='1234567890',
        )
        assert acc.account_number_last4 == '7890'

    def test_blind_index_set_on_save(self, bank_client):
        acc = BankAccount.objects.create(
            client=bank_client,
            bank_name='Capitec',
            account_holder_name='John Doe',
            account_number='1234567890',
        )
        assert acc.account_number_index != ''
        assert len(acc.account_number_index) == 64  # SHA-256 hex

    def test_same_digits_produce_same_index(self, bank_client):
        a = BankAccount.objects.create(
            client=bank_client, bank_name='A', account_holder_name='X',
            account_number='1234567890',
        )
        b = BankAccount.objects.create(
            client=bank_client, bank_name='B', account_holder_name='X',
            account_number='1234-567-890',  # formatting variations
        )
        assert a.account_number_index == b.account_number_index

    def test_masked_number_property(self, bank_client):
        acc = BankAccount.objects.create(
            client=bank_client, bank_name='Capitec', account_holder_name='J',
            account_number='1234567890',
        )
        assert acc.masked_number == '****7890'

    def test_only_one_primary_per_client(self, bank_client):
        a = BankAccount.objects.create(
            client=bank_client, bank_name='A', account_holder_name='X',
            account_number='1111111111', is_primary=True,
        )
        b = BankAccount.objects.create(
            client=bank_client, bank_name='B', account_holder_name='X',
            account_number='2222222222', is_primary=True,
        )
        a.refresh_from_db()
        b.refresh_from_db()
        assert a.is_primary is False
        assert b.is_primary is True

    def test_blank_account_number_does_not_crash(self, bank_client):
        acc = BankAccount.objects.create(
            client=bank_client, bank_name='Capitec', account_holder_name='J',
        )
        assert acc.account_number_last4 == ''
        assert acc.account_number_index == ''
        assert acc.masked_number == '—'

    def test_short_account_number(self, bank_client):
        acc = BankAccount.objects.create(
            client=bank_client, bank_name='Capitec', account_holder_name='J',
            account_number='123',
        )
        assert acc.account_number_last4 == '123'