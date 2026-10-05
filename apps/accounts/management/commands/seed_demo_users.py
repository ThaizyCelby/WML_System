"""
Seed the Wethu Micro Lenders system with 25 synthetic users covering every
workflow state, plus supporting documents, applications, loans, and mandates.

Usage:
    python manage.py seed_demo_users
    python manage.py seed_demo_users --reset
    python manage.py seed_demo_users --password "CustomPass123!"

All demo users share the same password (default: DemoPass2026!).

The command is idempotent — safe to re-run. It uses update_or_create
everywhere, so re-running only updates.
"""
import io
import random
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

User = get_user_model()

# ──────────────────────────────────────────────────────────────
# Deterministic RNG so re-runs produce the same data
# ──────────────────────────────────────────────────────────────
SEED = 42


# ──────────────────────────────────────────────────────────────
# Name pools (mix of South African names)
# ──────────────────────────────────────────────────────────────
FIRST_MALE = [
    'Sipho', 'Thabo', 'Kagiso', 'Bongani', 'Themba', 'Lucky', 'Given',
    'Moses', 'Andile', 'Mandla', 'Pieter', 'Johan', 'Riaan', 'Ahmed',
    'Farhan', 'Deepak', 'Rajesh', 'Lwazi', 'Sizwe', 'Tshepo',
]
FIRST_FEMALE = [
    'Thandi', 'Nandi', 'Zanele', 'Nomvula', 'Lerato', 'Precious', 'Nomsa',
    'Palesa', 'Kgomotso', 'Boitumelo', 'Anke', 'Elsa', 'Fatima', 'Aisha',
    'Priya', 'Ayanda', 'Bongiwe', 'Palesa', 'Refilwe', 'Neo',
]
SURNAMES = [
    'Mokoena', 'Dlamini', 'Nkosi', 'Khumalo', 'Sithole', 'Zulu', 'Ndlovu',
    'Mahlangu', 'Botha', 'van der Merwe', 'Naidoo', 'Patel', 'Jacobs',
    'Adams', 'Mabaso', 'Mthembu', 'Radebe', 'Mahlaba', 'Nkomo', 'Tshabalala',
    'Pretorius', 'du Plessis', 'Coetzee', 'Fourie', 'Reddy',
]


def rng_for(tag: str) -> random.Random:
    """Return a deterministic RNG based on a stable tag string."""
    return random.Random(f"{SEED}:{tag}")


def make_sa_id(rng: random.Random) -> str:
    """
    Generate a plausible 13-digit South African ID.
    Format: YYMMDD SSSS C A  (SSSS = gender+seq, C = citizenship, A = check)
    Not Luhn-valid, but structure is correct — adequate for demo.
    """
    yy = rng.randint(70, 99)
    mm = rng.randint(1, 12)
    dd = rng.randint(1, 28)
    gender = rng.choice(['0', '1', '2', '3', '4', '5', '6', '7', '8', '9'])
    seq = f"{rng.randint(0, 999):03d}"
    citizenship = '0'
    check = str(rng.randint(0, 9))
    return f"{yy:02d}{mm:02d}{dd:02d}{gender}{seq}{citizenship}{check}"


def make_phone(rng: random.Random) -> str:
    """+27 8X XXX XXXX — South African mobile format."""
    prefix = rng.choice(['60', '71', '72', '73', '74', '76', '78', '79',
                         '81', '82', '83', '84'])
    suffix = rng.randint(1_000_000, 9_999_999)
    return f"+27{prefix}{suffix}"


def make_pdf_bytes(title: str, body_lines: list[str]) -> bytes:
    """Generate a minimal single-page PDF using reportlab."""
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.setFont('Helvetica-Bold', 14)
    c.drawString(72, 780, title)
    c.setFont('Helvetica', 10)
    y = 750
    for line in body_lines:
        c.drawString(72, y, line)
        y -= 16
        if y < 60:
            c.showPage()
            y = 780
    c.save()
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────
# Command
# ──────────────────────────────────────────────────────────────
class Command(BaseCommand):
    help = 'Seed the system with 25 demo users across every workflow state.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset', action='store_true',
            help='Delete all demo users (by email domain) before seeding.',
        )
        parser.add_argument(
            '--password', default='DemoPass2026!',
            help='Shared password for all demo users.',
        )

    # ──────────────────────────────────────────────
    # Entry point
    # ──────────────────────────────────────────────
    def handle(self, *args, **options):
        self.password = options['password']
        self.created = 0
        self.updated = 0

        if options['reset']:
            self._reset()

        self.stdout.write(self.style.MIGRATE_HEADING(
            '\n=== Wethu Micro Lenders — Demo Seed ===\n'
        ))

        with transaction.atomic():
            self._seed_roles()
            self._seed_products()
            self._seed_staff()
            self._seed_clients()

        self._print_summary()

    # ──────────────────────────────────────────────
    # Reset
    # ──────────────────────────────────────────────
    def _reset(self):
        self.stdout.write('Resetting demo users…')
        demo = User.objects.filter(email__endswith='@demo.wethu.test')
        count = demo.count()
        demo.delete()
        self.stdout.write(self.style.WARNING(f'  Deleted {count} demo users.'))

    # ──────────────────────────────────────────────
    # Roles
    # ──────────────────────────────────────────────
    def _seed_roles(self):
        from apps.accounts.models import Role

        role_names = [
            'Administrator', 'Credit Officer', 'Finance Officer',
            'Collections Officer', 'Compliance Officer', 'Auditor',
            'Client',
        ]
        for name in role_names:
            Role.objects.update_or_create(
                name=name,
                defaults={'is_system_role': True, 'is_active': True},
            )
        self.stdout.write(self.style.SUCCESS(f'Roles: {len(role_names)} ready.'))

    # ──────────────────────────────────────────────
    # Loan products
    # ──────────────────────────────────────────────
    def _seed_products(self):
        from apps.loans.models import LoanProduct

        products = [
            {
                'name': 'Quick Cash Loan',
                'description': 'Short-term loan for immediate cash-flow needs. 1–3 months.',
                'min_amount': Decimal('500.00'),
                'max_amount': Decimal('5000.00'),
                'min_term': 1, 'max_term': 3,
                'interest_type': 'flat',
                'interest_rate': Decimal('30.00'),
                'origination_fee_percent': Decimal('2.50'),
                'late_payment_fee': Decimal('50.00'),
                'repayment_frequency': 'monthly',
                'is_active': True,
            },
            {
                'name': 'Standard Personal Loan',
                'description': 'General purpose loan with balanced terms. 6–12 months.',
                'min_amount': Decimal('1000.00'),
                'max_amount': Decimal('50000.00'),
                'min_term': 6, 'max_term': 12,
                'interest_type': 'flat',
                'interest_rate': Decimal('30.00'),
                'origination_fee_percent': Decimal('2.50'),
                'late_payment_fee': Decimal('50.00'),
                'repayment_frequency': 'monthly',
                'is_active': True,
            },
            {
                'name': 'Extended Loan',
                'description': 'Larger amounts over 12–24 months.',
                'min_amount': Decimal('20000.00'),
                'max_amount': Decimal('150000.00'),
                'min_term': 12, 'max_term': 24,
                'interest_type': 'flat',
                'interest_rate': Decimal('28.00'),
                'origination_fee_percent': Decimal('2.00'),
                'late_payment_fee': Decimal('75.00'),
                'repayment_frequency': 'monthly',
                'is_active': True,
            },
            {
                'name': 'Fortnightly Cashflow Loan',
                'description': 'Repay every two weeks — matched to your pay cycle.',
                'min_amount': Decimal('500.00'),
                'max_amount': Decimal('20000.00'),
                'min_term': 6, 'max_term': 18,
                'interest_type': 'simple',
                'interest_rate': Decimal('32.00'),
                'origination_fee_percent': Decimal('2.50'),
                'late_payment_fee': Decimal('50.00'),
                'repayment_frequency': 'fortnightly',
                'is_active': True,
            },
        ]
        for p in products:
            LoanProduct.objects.update_or_create(name=p['name'], defaults=p)
        self.stdout.write(self.style.SUCCESS(f'Loan products: {len(products)} ready.'))

    # ──────────────────────────────────────────────
    # Staff
    # ──────────────────────────────────────────────
    def _seed_staff(self):
        from apps.accounts.models import UserRole, Role

        staff_specs = [
            ('superadmin', 'Demo', 'Superadmin', ['Administrator'], True),
            ('credit.officer', 'Given', 'Credit', ['Credit Officer'], False),
            ('finance.officer', 'Lerato', 'Finance', ['Finance Officer'], False),
            ('collections.officer', 'Bongani', 'Collections', ['Collections Officer'], False),
            ('compliance.officer', 'Nomsa', 'Compliance', ['Compliance Officer'], False),
            ('auditor', 'Pieter', 'Auditor', ['Auditor'], False),
            ('credit.officer2', 'Zanele', 'Credit2', ['Credit Officer'], False),
        ]

        for local, first, last, roles, is_super in staff_specs:
            email = f'{local}@demo.wethu.test'
            user, created = User.objects.update_or_create(
                email=email,
                defaults={
                    'first_name': first,
                    'last_name': last,
                    'is_active': True,
                    'is_staff': True,
                    'email_verified': True,
                    'phone_number': make_phone(rng_for(email)),
                },
            )
            if is_super:
                user.is_superuser = True
            user.set_password(self.password)
            user.save()

            # Attach roles
            for role_name in roles:
                role = Role.objects.get(name=role_name)
                UserRole.objects.get_or_create(user=user, role=role)

            if created:
                self.created += 1
            else:
                self.updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'Staff users: {len(staff_specs)} ready.'
        ))

    # ──────────────────────────────────────────────
    # Clients
    # ──────────────────────────────────────────────
    def _seed_clients(self):
        # 18 clients, spread across distinct workflow states
        specs = [
            # state, count
            ('new', 3),           # account only, no profile
            ('incomplete', 3),    # partial profile
            ('complete_no_docs', 3),
            ('docs_submitted', 3),
            ('application_submitted', 2),
            ('contract_pending', 2),   # loan created, waiting on client acceptance
            ('contract_accepted', 2),  # mandate pending
        ]
        total_clients = sum(c for _, c in specs)

        client_index = 0
        for state, count in specs:
            for _ in range(count):
                client_index += 1
                self._create_client(state, client_index)

        self.stdout.write(self.style.SUCCESS(
            f'Clients: {total_clients} ready (across {len(specs)} workflow states).'
        ))

    def _create_client(self, state, index):
        from apps.accounts.models import ClientProfile, Role, UserRole

        tag = f'client.{state}.{index:02d}'
        email = f'{tag}@demo.wethu.test'
        rng = rng_for(email)

        gender = rng.choice(['M', 'F'])
        first = rng.choice(FIRST_MALE if gender == 'M' else FIRST_FEMALE)
        last = rng.choice(SURNAMES)

        user, created = User.objects.update_or_create(
            email=email,
            defaults={
                'first_name': first,
                'last_name': last,
                'is_active': True,
                'email_verified': True,
                'phone_number': make_phone(rng),
            },
        )
        user.set_password(self.password)
        user.save()

        # Every demo client gets the Client role
        role = Role.objects.get(name='Client')
        UserRole.objects.get_or_create(user=user, role=role)

        if state == 'new':
            if created:
                self.created += 1
            else:
                self.updated += 1
            return

        # Build profile
        now_iso = timezone.now().isoformat()
        income = Decimal(rng.randint(8000, 45000))
        expenses = (income * Decimal(str(rng.uniform(0.25, 0.55)))).quantize(Decimal('0.01'))
        debts = (income * Decimal(str(rng.uniform(0.05, 0.30)))).quantize(Decimal('0.01'))

        profile_defaults = {
            'id_number': make_sa_id(rng),
            'date_of_birth': date(rng.randint(1970, 2000), rng.randint(1, 12), rng.randint(1, 28)),
            'employment_type': rng.choice(['full_time', 'part_time', 'self_employed', 'contract']),
            'employer_name': rng.choice([
                'Acme Corp', 'Standard Bank', 'Shoprite', 'Pick n Pay',
                'Sasol', 'MTN', 'Vodacom', 'Eskom', 'Transnet',
                'Self-employed',
            ]),
            'monthly_income': income,
            'monthly_expenses': expenses,
            'existing_debt_obligations': debts,
            'residential_address': {
                'street': f'{rng.randint(1, 999)} {rng.choice(["Main", "Church", "Voortrekker", "Nelson Mandela", "Rissik"])} Street',
                'city': rng.choice(['Johannesburg', 'Pretoria', 'Cape Town', 'Durban', 'Bloemfontein', 'Polokwane']),
                'province': rng.choice(['Gauteng', 'Western Cape', 'KwaZulu-Natal', 'Free State', 'Limpopo']),
                'postal_code': f'{rng.randint(1000, 9999)}',
            },
            'consent_records': {
                'credit_check_consent': {'granted': True, 'timestamp': now_iso, 'version': '1.0'},
                'affordability_consent': {'granted': True, 'timestamp': now_iso, 'version': '1.0'},
                'terms_accepted': {'granted': True, 'timestamp': now_iso, 'version': '1.0'},
                'privacy_accepted': {'granted': True, 'timestamp': now_iso, 'version': '1.0'},
            },
        }

        if state == 'incomplete':
            # Strip some fields to make it incomplete
            profile_defaults['id_number'] = ''
            profile_defaults['monthly_income'] = Decimal('0.00')
            profile_defaults['residential_address'] = {}

        profile, _ = ClientProfile.objects.update_or_create(
            user=user, defaults=profile_defaults,
        )

        # Attach documents where required
        if state in ('docs_submitted', 'application_submitted', 'contract_pending', 'contract_accepted'):
            self._attach_documents(user, approved=(state in ('application_submitted', 'contract_pending', 'contract_accepted')))

        # Attach a bank statement where required
        if state in ('application_submitted', 'contract_pending', 'contract_accepted'):
            self._attach_bank_statement(user, rng)

        # Push the client further through the workflow
        if state in ('application_submitted', 'contract_pending', 'contract_accepted'):
            self._create_application(user, state, rng)

        if created:
            self.created += 1
        else:
            self.updated += 1

    # ──────────────────────────────────────────────
    # Documents
    # ──────────────────────────────────────────────
    def _attach_documents(self, user, approved=False):
        from apps.documents.models import Document, DocumentVersion
        import hashlib

        doc_types = [
            ('identity_document', 'ID document'),
            ('proof_of_address', 'Proof of address'),
            ('payslip', 'Payslip'),
            ('bank_statement', 'Bank statement'),
        ]

        for doc_type, label in doc_types:
            # Skip if document already exists for this user+type
            if Document.objects.filter(client=user, document_type=doc_type).exists():
                continue

            pdf = make_pdf_bytes(
                f'{label} — {user.full_name}',
                [
                    f'Type: {label}',
                    f'Client: {user.email}',
                    f'Generated: {timezone.now().isoformat()}',
                    '',
                    'This is a synthetic document created by the demo seeder.',
                ],
            )
            file_hash = hashlib.sha256(pdf).hexdigest()
            storage_key = f'documents/demo/{user.id}/{doc_type}-{file_hash[:8]}.pdf'
            default_storage.save(storage_key, ContentFile(pdf))

            status = 'approved' if approved else 'submitted'
            doc = Document.objects.create(
                client=user,
                document_type=doc_type,
                original_filename=f'{doc_type}.pdf',
                mime_type='application/pdf',
                file_size=len(pdf),
                storage_key=storage_key,
                status=status,
                virus_scan_status='clean',
                virus_scan_result='Demo seed',
            )
            DocumentVersion.objects.create(
                document=doc,
                version_number=1,
                storage_key=storage_key,
                file_hash=file_hash,
                uploaded_by=user,
            )

    # ──────────────────────────────────────────────
    # Bank statement
    # ──────────────────────────────────────────────
    def _attach_bank_statement(self, user, rng):
        from apps.banking.models import BankStatement, BankTransaction
        from apps.documents.models import Document

        if BankStatement.objects.filter(client=user).exists():
            return

        doc = Document.objects.filter(client=user, document_type='bank_statement').first()
        if not doc:
            return

        statement = BankStatement.objects.create(
            client=user,
            document=doc,
            bank_name=rng.choice(['Capitec', 'ABSA', 'FNB', 'Nedbank', 'Standard Bank']),
            processing_status='completed',
            extracted_text='(demo seed)',
            extraction_confidence=Decimal('0.90'),
        )

        # Create a handful of plausible transactions
        today = date.today()
        for i in range(20):
            tx_date = today - timedelta(days=i * 3)
            is_credit = (i == 0)  # day-0 is salary credit
            if is_credit:
                amount = Decimal(str(rng.randint(15_000, 35_000)))
                desc = 'Salary — ACME CORP'
                cat = 'salary'
                ttype = 'credit'
            else:
                amount = Decimal(str(rng.randint(50, 2_500)))
                desc = rng.choice([
                    'Checkers Grocery', 'Uber Trip', 'Engen Fuel',
                    'Netflix Subscription', 'Pick n Pay Groceries',
                    'Vodacom Airtime', 'ATM Cash Withdrawal',
                    'Debit Order — ABC Loan', 'Edgars Account',
                    'Shoprite', 'Takeaway Restaurant',
                ])
                cat = 'grocery' if 'Grocery' in desc or 'Shoprite' in desc else \
                      'transport' if 'Uber' in desc or 'Engen' in desc else \
                      'entertainment' if 'Netflix' in desc else \
                      'airtime_data' if 'Vodacom' in desc else \
                      'cash_withdrawal' if 'ATM' in desc else \
                      'loan_payment' if 'Debit Order' in desc else \
                      'retail'
                ttype = 'debit'

            BankTransaction.objects.create(
                statement=statement,
                transaction_date=tx_date,
                description=desc,
                amount=amount,
                transaction_type=ttype,
                category=cat,
                is_salary=is_credit,
                is_debit_order=('Debit Order' in desc),
            )

    # ──────────────────────────────────────────────
    # Applications + Loans + Mandates
    # ──────────────────────────────────────────────
    def _create_application(self, user, target_state, rng):
        from apps.loans.models import LoanApplication, LoanProduct
        from apps.loans.services import LoanApplicationService

        if LoanApplication.objects.filter(client=user).exists():
            return

        # Pick a product that fits the client's income
        product = LoanProduct.objects.filter(is_active=True).order_by('min_amount').first()
        amount = Decimal(str(rng.randint(2000, 15000)))
        term = rng.choice([6, 12])

        try:
            app = LoanApplicationService.create_application(
                client=user, product_id=product.id, amount=amount, term=term,
            )
        except Exception as e:
            self.stdout.write(self.style.WARNING(
                f'  Could not create application for {user.email}: {e}'
            ))
            return

        # Walk through the workflow using the real transition service
        staff = User.objects.filter(
            email='credit.officer@demo.wethu.test',
        ).first() or User.objects.filter(is_superuser=True).first()

        if staff is None:
            return

        try:
            LoanApplicationService.submit_application(app, user)

            for stage in ('document_review', 'kyc_review', 'affordability_review',
                          'credit_review', 'approved'):
                LoanApplicationService.transition(app, stage, staff)

            if target_state in ('contract_pending', 'contract_accepted'):
                LoanApplicationService.transition(app, 'contract_pending', staff)

            if target_state == 'contract_accepted':
                LoanApplicationService.transition(app, 'contract_accepted', user)

                # Create a signed mandate so the staff can review it
                self._create_mandate(app, user, rng)

        except Exception as e:
            self.stdout.write(self.style.WARNING(
                f'  Workflow error for {user.email}: {e}'
            ))

    def _create_mandate(self, application, user, rng):
        from apps.payments.mandate_service import MandateService

        loan = getattr(application, 'loan', None)
        if loan is None:
            return
        if loan.debit_instructions.exists():
            return

        try:
            instruction = MandateService.create_mandate(
                loan=loan,
                account_holder_name=user.full_name,
                account_number=f"{rng.randint(1000000000, 9999999999)}",
                bank_name=rng.choice(['Capitec', 'ABSA', 'FNB', 'Nedbank', 'Standard Bank']),
                branch_code=f"{rng.randint(100000, 999999)}",
                account_type='cheque',
                signed_by=user,
                ip_address='127.0.0.1',
                user_agent='seed',
            )
            MandateService.sign_mandate(
                instruction, user,
                ip_address='127.0.0.1',
                user_agent='seed',
            )
        except Exception as e:
            self.stdout.write(self.style.WARNING(
                f'  Mandate creation failed for {user.email}: {e}'
            ))

    # ──────────────────────────────────────────────
    # Summary
    # ──────────────────────────────────────────────
    def _print_summary(self):
        from apps.accounts.models import ClientProfile
        from apps.documents.models import Document
        from apps.loans.models import LoanApplication, Loan
        from apps.payments.models import DebitInstruction

        self.stdout.write(self.style.MIGRATE_HEADING('\n=== Summary ==='))
        self.stdout.write(f"Users created:  {self.created}")
        self.stdout.write(f"Users updated:  {self.updated}")
        self.stdout.write('')
        self.stdout.write(f"Total users:         {User.objects.count()}")
        self.stdout.write(f"Client profiles:     {ClientProfile.objects.count()}")
        self.stdout.write(f"Documents:           {Document.objects.count()}")
        self.stdout.write(f"Loan applications:   {LoanApplication.objects.count()}")
        self.stdout.write(f"Loans:               {Loan.objects.count()}")
        self.stdout.write(f"Debit instructions:  {DebitInstruction.objects.count()}")
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('\n=== Login credentials ==='))
        self.stdout.write(f"Shared password: {self.password}")
        self.stdout.write('')
        self.stdout.write('Superuser:')
        self.stdout.write('  superadmin@demo.wethu.test')
        self.stdout.write('')
        self.stdout.write('Staff:')
        for e in ('credit.officer', 'credit.officer2', 'finance.officer',
                  'collections.officer', 'compliance.officer', 'auditor'):
            self.stdout.write(f'  {e}@demo.wethu.test')
        self.stdout.write('')
        self.stdout.write('Clients (18 — mixed workflow states):')
        for spec_label, _ in (
            ('client.new', 3), ('client.incomplete', 3),
            ('client.complete_no_docs', 3), ('client.docs_submitted', 3),
            ('client.application_submitted', 2),
            ('client.contract_pending', 2),
            ('client.contract_accepted', 2),
        ):
            self.stdout.write(f'  {spec_label}.01@demo.wethu.test  …  {spec_label}.0{_[0] if False else _}@demo.wethu.test')
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Done.'))