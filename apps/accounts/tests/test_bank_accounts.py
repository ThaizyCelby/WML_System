"""BankAccount model + service tests."""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connection

from apps.accounts.bank_account_service import BankAccountService
from apps.accounts.models import BankAccount
from core.crypto import blind_index, decrypt

User = get_user_model()


@pytest.mark.django_db
class TestBankAccountModel:

    def _user(self, suffix=''):
        return User.objects.create_user(
            email=f'bank{suffix}@wethu.test', password='TestPass123!',
        )

    def _raw(self, account_id, column):
        with connection.cursor() as cur:
            cur.execute(
                f"SELECT {column} FROM bank_accounts WHERE id = %s",
                [account_id.hex],
            )
            row = cur.fetchone()
            return row[0] if row else None

    def test_account_number_encrypted_at_rest(self):
        client = self._user('1')
        acc = BankAccount.objects.create(
            client=client,
            bank_name='Capitec',
            account_holder_name='Test User',
            account_number='1234567890',
        )
        raw = self._raw(acc.id, 'account_number')
        assert raw is not None
        assert '1234567890' not in raw
        assert raw.startswith('gAAAAA')

    def test_account_number_round_trip(self):
        client = self._user('2')
        acc = BankAccount.objects.create(
            client=client,
            bank_name='FNB',
            account_holder_name='Jane Doe',
            account_number='9876543210',
        )
        acc.refresh_from_db()
        assert acc.account_number == '9876543210'

    def test_last4_populated_on_save(self):
        client = self._user('3')
        acc = BankAccount.objects.create(
            client=client,
            bank_name='ABSA',
            account_holder_name='X',
            account_number='1234567890',
        )
        assert acc.account_number_last4 == '7890'

    def test_blind_index_populated_on_save(self):
        client = self._user('4')
        acc = BankAccount.objects.create(
            client=client,
            bank_name='Nedbank',
            account_holder_name='X',
            account_number='1234567890',
        )
        assert acc.account_number_index == blind_index('1234567890')

    def test_second_primary_demotes_first(self):
        client = self._user('5')
        a1 = BankAccount.objects.create(
            client=client, bank_name='A', account_holder_name='X',
            account_number='1111111111', is_primary=True,
        )
        a2 = BankAccount.objects.create(
            client=client, bank_name='B', account_holder_name='X',
            account_number='2222222222', is_primary=True,
        )
        a1.refresh_from_db()
        a2.refresh_from_db()
        assert a1.is_primary is False
        assert a2.is_primary is True


@pytest.mark.django_db
class TestBankAccountService:

    def _user(self, suffix=''):
        return User.objects.create_user(
            email=f'banksvc{suffix}@wethu.test', password='TestPass123!',
        )

    def test_add_account_creates(self):
        client = self._user('1')
        acc, created = BankAccountService.add_account(
            client,
            bank_name='Capitec',
            account_holder_name='Test',
            account_number='1234567890',
        )
        assert created is True
        assert acc.is_primary is True  # first account
        assert acc.account_number_last4 == '7890'

    def test_add_account_is_idempotent(self):
        client = self._user('2')
        acc1, _ = BankAccountService.add_account(
            client, bank_name='Capitec', account_holder_name='T',
            account_number='5555555555',
        )
        acc2, created = BankAccountService.add_account(
            client, bank_name='Capitec', account_holder_name='T',
            account_number='5555555555',
        )
        assert created is False
        assert acc1.id == acc2.id

    def test_first_account_is_primary_second_is_not(self):
        client = self._user('3')
        a1, _ = BankAccountService.add_account(
            client, bank_name='A', account_holder_name='X',
            account_number='1111111111',
        )
        a2, _ = BankAccountService.add_account(
            client, bank_name='B', account_holder_name='X',
            account_number='2222222222',
        )
        assert a1.is_primary is True
        assert a2.is_primary is False

    def test_mark_primary(self):
        client = self._user('4')
        a1, _ = BankAccountService.add_account(
            client, bank_name='A', account_holder_name='X',
            account_number='1111111111',
        )
        a2, _ = BankAccountService.add_account(
            client, bank_name='B', account_holder_name='X',
            account_number='2222222222',
        )
        BankAccountService.mark_primary(a2)
        a1.refresh_from_db()
        a2.refresh_from_db()
        assert a1.is_primary is False
        assert a2.is_primary is True

    def test_find_by_number(self):
        client = self._user('5')
        acc, _ = BankAccountService.add_account(
            client, bank_name='A', account_holder_name='X',
            account_number='3333333333',
        )
        found = BankAccountService.find_by_number(client, '3333333333')
        assert found is not None
        assert found.id == acc.id

    def test_find_by_number_not_found(self):
        client = self._user('6')
        assert BankAccountService.find_by_number(client, '9999999999') is None

    def test_add_account_rejects_empty_number(self):
        client = self._user('7')
        with pytest.raises(ValueError, match='Account number'):
            BankAccountService.add_account(
                client, bank_name='A', account_holder_name='X',
                account_number='',
            )

    def test_add_account_rejects_short_number(self):
        client = self._user('8')
        with pytest.raises(ValueError, match='too short'):
            BankAccountService.add_account(
                client, bank_name='A', account_holder_name='X',
                account_number='123',
            )

    def test_accounts_isolated_per_client(self):
        c1 = self._user('9')
        c2 = self._user('10')
        BankAccountService.add_account(
            c1, bank_name='A', account_holder_name='X',
            account_number='1111111111',
        )
        BankAccountService.add_account(
            c2, bank_name='B', account_holder_name='Y',
            account_number='2222222222',
        )
        assert BankAccountService.accounts_for(c1).count() == 1
        assert BankAccountService.accounts_for(c2).count() == 1

    def test_cross_client_lookup_returns_none(self):
        """A client cannot find another client's account by number."""
        c1 = self._user('11')
        c2 = self._user('12')
        BankAccountService.add_account(
            c1, bank_name='A', account_holder_name='X',
            account_number='4444444444',
        )
        assert BankAccountService.find_by_number(c2, '4444444444') is None