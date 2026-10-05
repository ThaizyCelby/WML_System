"""
Phase 2 sanity tests: FKs exist, backfill populated them, cross-tenant
data is distinguishable.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.accounts.models import BankAccount, Organisation
from apps.loans.models import Loan, LoanApplication, LoanProduct
from apps.support.models import SupportTicket

User = get_user_model()


@pytest.mark.django_db
class TestOrgFKsExist:

    def test_loan_product_has_organisation_field(self):
        org = Organisation.objects.create(name='A', slug='a')
        product = LoanProduct.objects.create(
            name='X', organisation=org,
        )
        assert product.organisation == org

    def test_loan_has_organisation_field(self):
        org = Organisation.objects.create(name='A', slug='a')
        loan = Loan(organisation=org)
        assert loan.organisation == org

    def test_bank_account_has_organisation_field(self):
        org = Organisation.objects.create(name='A', slug='a')
        user = User.objects.create_user(
            email='ba@x.com', password='TestPass123!', organisation=org,
        )
        acc = BankAccount.objects.create(
            client=user, organisation=org,
            bank_name='X', account_holder_name='Y', account_number='1234567890',
        )
        assert acc.organisation == org

    def test_support_ticket_has_organisation_field(self):
        org = Organisation.objects.create(name='A', slug='a')
        user = User.objects.create_user(
            email='st@x.com', password='TestPass123!', organisation=org,
        )
        ticket = SupportTicket.objects.create(
            client=user, subject='X', organisation=org,
        )
        assert ticket.organisation == org


@pytest.mark.django_db
class TestCrossTenantFiltering:

    def test_filtering_by_org_isolates_products(self):
        org_a = Organisation.objects.create(name='A', slug='a')
        org_b = Organisation.objects.create(name='B', slug='b')

        LoanProduct.objects.create(name='A Product', organisation=org_a)
        LoanProduct.objects.create(name='B Product', organisation=org_b)
        LoanProduct.objects.create(name='Unassigned Product')  # no org

        assert LoanProduct.objects.filter(organisation=org_a).count() == 1
        assert LoanProduct.objects.filter(organisation=org_b).count() == 1
        assert LoanProduct.objects.filter(organisation__isnull=True).count() == 1

    def test_filtering_by_org_isolates_support_tickets(self):
        org_a = Organisation.objects.create(name='A', slug='a')
        org_b = Organisation.objects.create(name='B', slug='b')

        user_a = User.objects.create_user(email='u-a@x.com', password='P!', organisation=org_a)
        user_b = User.objects.create_user(email='u-b@x.com', password='P!', organisation=org_b)

        SupportTicket.objects.create(client=user_a, subject='T-A', organisation=org_a)
        SupportTicket.objects.create(client=user_b, subject='T-B', organisation=org_b)

        assert SupportTicket.objects.filter(organisation=org_a).count() == 1
        assert SupportTicket.objects.filter(organisation=org_b).count() == 1

    def test_related_name_from_org(self):
        org = Organisation.objects.create(name='A', slug='a')
        LoanProduct.objects.create(name='X', organisation=org)
        LoanProduct.objects.create(name='Y', organisation=org)
        assert org.loan_products.count() == 2