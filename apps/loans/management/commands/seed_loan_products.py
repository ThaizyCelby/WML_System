"""Seed realistic South African micro-lending products."""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.loans.models import LoanProduct


PRODUCTS = [
    {
        'name': 'Starter Loan',
        'description': 'A small, short-term loan for first-time clients. Fast approval.',
        'min_amount': Decimal('500.00'),
        'max_amount': Decimal('5000.00'),
        'min_term': 1,
        'max_term': 6,
        'interest_type': 'flat',
        'interest_rate': Decimal('28.00'),
        'origination_fee_percent': Decimal('2.50'),
        'late_payment_fee': Decimal('50.00'),
        'repayment_frequency': 'monthly',
        'max_exposure': Decimal('250000.00'),
        'is_active': True,
        'eligibility_rules': {
            'min_monthly_income': 3000,
            'min_age': 18,
            'requires_bank_statement': True,
        },
    },
    {
        'name': 'Standard Personal Loan',
        'description': 'Our most popular product. Flexible amounts and terms.',
        'min_amount': Decimal('5000.00'),
        'max_amount': Decimal('30000.00'),
        'min_term': 6,
        'max_term': 24,
        'interest_type': 'flat',
        'interest_rate': Decimal('26.00'),
        'origination_fee_percent': Decimal('2.00'),
        'late_payment_fee': Decimal('75.00'),
        'repayment_frequency': 'monthly',
        'max_exposure': Decimal('1000000.00'),
        'is_active': True,
        'eligibility_rules': {
            'min_monthly_income': 5000,
            'min_age': 18,
            'requires_bank_statement': True,
        },
    },
    {
        'name': 'Premium Loan',
        'description': 'Larger amounts for established clients with good repayment history.',
        'min_amount': Decimal('30000.00'),
        'max_amount': Decimal('100000.00'),
        'min_term': 12,
        'max_term': 48,
        'interest_type': 'amortized',
        'interest_rate': Decimal('22.00'),
        'origination_fee_percent': Decimal('1.50'),
        'late_payment_fee': Decimal('100.00'),
        'repayment_frequency': 'monthly',
        'max_exposure': Decimal('2500000.00'),
        'is_active': True,
        'eligibility_rules': {
            'min_monthly_income': 15000,
            'min_age': 21,
            'requires_bank_statement': True,
        },
    },
    {
        'name': 'Payday Bridge Loan',
        'description': 'A short-term bridge to your next payday. Repayable in one instalment.',
        'min_amount': Decimal('500.00'),
        'max_amount': Decimal('3000.00'),
        'min_term': 1,
        'max_term': 1,
        'interest_type': 'flat',
        'interest_rate': Decimal('15.00'),
        'origination_fee_percent': Decimal('5.00'),
        'late_payment_fee': Decimal('50.00'),
        'repayment_frequency': 'monthly',
        'max_exposure': Decimal('150000.00'),
        'is_active': True,
        'eligibility_rules': {
            'min_monthly_income': 2500,
            'min_age': 18,
            'requires_bank_statement': True,
        },
    },
]


class Command(BaseCommand):
    help = 'Seed default loan products.'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.HTTP_INFO('Seeding loan products...'))

        for data in PRODUCTS:
            product, created = LoanProduct.objects.update_or_create(
                name=data['name'],
                defaults=data,
            )
            verb = 'Created' if created else 'Updated'
            self.stdout.write(
                f'  {verb}: {product.name} '
                f'(R{product.min_amount}–R{product.max_amount}, '
                f'{product.interest_rate}%)'
            )

        total = LoanProduct.objects.count()
        active = LoanProduct.objects.filter(is_active=True).count()
        self.stdout.write(self.style.SUCCESS(
            f'Done. {total} products ({active} active).'
        ))