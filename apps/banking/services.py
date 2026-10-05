"""Bank statement processing and transaction extraction."""
import json  # noqa: F401  (kept for downstream callers that may rely on the namespace)
import logging
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.utils import timezone
from pypdf import PdfReader

from .models import BankStatement, BankTransaction
from .parsers import get_parser_for_bank

logger = logging.getLogger('apps.banking')


# ── Spending buckets (deterministic categorisation) ─────────────────
SPENDING_BUCKETS = {
    'groceries':       ['checkers', 'pick n pay', 'spar', 'woolworths', 'food lover',
                        'shoprite', 'boxer', 'usave', 'ok foods'],
    'transport':       ['uber', 'bolt', 'shell', 'engen', 'total', 'sasol', 'gautrain',
                        'putco', 'taxify'],
    'entertainment':   ['netflix', 'spotify', 'showmax', 'dstv', 'apple.com', 'youtube',
                        'playstation', 'xbox', 'steam'],
    'debit_orders':    ['debit order', 'debi-check', 'naedo'],
    'loan_repayments': ['loan', 'credit', 'finan', 'african bank', 'capitec loan',
                        'absa loan', 'fnb loan', 'nedbank loan'],
    'airtime_data':    ['vodacom', 'mtn', 'cell c', 'telkom', 'rain', 'airtime'],
    'cash_withdrawal': ['atm', 'cash withdrawal', 'cash send', 'sparkatm'],
    'bank_fees':       ['fee', 'admin fee', 'service fee', 'monthly fee'],
    'transfers':       ['transfer', 'payshap', 'eft'],
    'retail':          ['edgars', 'mr price', 'foschini', 'truworths', 'ackermans',
                        'pep', 'jet', 'tfg', 'sportscene'],
    'insurance':       ['insurance', 'assurance', 'funeral cover', 'hollard',
                        'discovery', 'momentum', 'sanlam', 'old mutual'],
    'education':       ['school', 'university', 'college', 'tuition', 'unisa'],
    'gambling':        ['lotto', 'betway', 'hollywoodbets', 'supabets', 'sportingbet',
                        '1xbet', 'gambling'],
    'alcohol':         ['liquor', 'bottle store', 'tops', 'ultra', 'beer', 'wine'],
}


class BankStatementService:

    # ── Processing pipeline ──────────────────────────────────────
    @staticmethod
    def process_statement(statement: BankStatement) -> bool:
        """Extract text from PDF, parse transactions, and store them."""
        statement.processing_status = 'processing'
        statement.save(update_fields=['processing_status'])

        try:
            if not statement.document:
                raise ValueError("No associated document")

            file_path = statement.document.storage_key
            if not default_storage.exists(file_path):
                raise FileNotFoundError("Document file not found")

            with default_storage.open(file_path, 'rb') as f:
                reader = PdfReader(f)
                text = ""
                for page in reader.pages:
                    text += page.extract_text() + "\n"

            statement.extracted_text = text
            statement.extraction_confidence = Decimal('0.80')
            statement.save(update_fields=['extracted_text', 'extraction_confidence'])

            parser = get_parser_for_bank(statement.bank_name)
            transactions_data = parser.parse(text)

            statement.transactions.all().delete()

            for tx_data in transactions_data:
                BankTransaction.objects.create(statement=statement, **tx_data)

            BankStatementService.categorize_transactions(
                BankTransaction.objects.filter(statement=statement)
            )

            statement.processing_status = 'completed'
            statement.save(update_fields=['processing_status'])

            # Invalidate cached AI analysis — the source data changed
            cache.delete(f"ai_analysis:bank_statement:{statement.id}")
            return True
        except Exception as e:
            logger.error("Bank statement processing failed: %s", e)
            statement.processing_status = 'failed'
            statement.save(update_fields=['processing_status'])
            return False

    # ── Legacy fallback parser (kept for compatibility) ──────────
    @staticmethod
    def parse_transactions_from_text(text: str) -> list:
        """Fallback parser for simple line formats."""
        import re
        transactions = []
        pattern = re.compile(
            r'(?P<date>\d{2}/\d{2})\s+(?P<desc>.+?)\s+(?P<amount>[+-]?[\d,]+\.\d{2})',
            re.IGNORECASE,
        )
        for line in text.split('\n'):
            match = pattern.search(line.strip())
            if match:
                date_str = match.group('date')
                desc = match.group('desc').strip()
                amount_str = match.group('amount').replace(',', '').replace('+', '')
                try:
                    amount = Decimal(amount_str)
                except InvalidOperation:
                    continue
                tx_type = 'credit' if amount >= 0 else 'debit'
                if amount < 0:
                    amount = abs(amount)
                try:
                    day, month = map(int, date_str.split('/'))
                    year = timezone.now().year
                    tx_date = datetime(year, month, day).date()
                except ValueError:
                    continue
                transactions.append({
                    'transaction_date': tx_date,
                    'description': desc,
                    'amount': amount,
                    'transaction_type': tx_type,
                    'raw_data': {'line': line.strip()},
                })
        return transactions

    # ── Categorization ───────────────────────────────────────────
    @staticmethod
    def categorize_transactions(transactions) -> None:
        """Categorize transactions using simple keyword rules."""
        categories = {
            'salary': ['salary', 'wages', 'payroll', 'stipend'],
            'debit_order': ['debit order', 'debi-check', 'naedo'],
            'grocery': ['checkers', 'pick n pay', 'spar', 'woolworths'],
            'transport': ['uber', 'bolt', 'shell', 'engen', 'total'],
            'entertainment': ['netflix', 'spotify', 'showmax', 'dstv'],
            'loan_payment': ['loan', 'credit', 'finan', 'capitec', 'absa'],
        }
        for tx in transactions:
            desc = (tx.description or '').lower()
            category = 'uncategorized'
            is_salary = False
            is_debit_order = False
            for cat, keywords in categories.items():
                if any(kw in desc for kw in keywords):
                    category = cat
                    if cat == 'salary':
                        is_salary = True
                    if cat == 'debit_order':
                        is_debit_order = True
                    break
            tx.category = category
            tx.is_salary = is_salary
            tx.is_debit_order = is_debit_order
            tx.save(update_fields=[
                'category', 'is_salary', 'is_debit_order', 'updated_at',
            ])

    # ── AI analysis (Grok primary / GLM fallback) ────────────────
    @staticmethod
    def analyze_with_ai(statement: BankStatement):
        """
        Run AI analysis on the transactions of a statement.

        Uses settings.AI_DEFAULT_PROVIDER (default: grok).
        Falls back to settings.AI_FALLBACK_PROVIDER (default: glm),
        then to the mock provider.

        Results are cached for 24 hours per statement to protect
        free-tier quota.
        """
        from apps.ai.services import AIService

        cache_key = f"ai_analysis:bank_statement:{statement.id}"
        cached = cache.get(cache_key)
        if cached:
            logger.info("Returning cached AI analysis for statement %s", statement.id)
            return cached

        # ── Populate transactions FIRST (bug fix) ─────────────────
        transactions = list(
            BankTransaction.objects.filter(statement=statement).values(
                'transaction_date', 'description', 'amount',
                'transaction_type', 'category',
            )
        )
        for tx in transactions:
            tx['amount'] = str(tx['amount'])
            tx['transaction_date'] = tx['transaction_date'].isoformat()

        provider = getattr(settings, 'AI_DEFAULT_PROVIDER', 'grok')

        payday = AIService.run_analysis(
            provider, transactions, 'payday', input_ref=str(statement.id),
        )
        debt = AIService.run_analysis(
            provider, transactions, 'debt', input_ref=str(statement.id),
        )
        general = AIService.run_analysis(
            provider, transactions, 'general', input_ref=str(statement.id),
        )

        result = (payday, debt, general)
        cache.set(cache_key, result, timeout=86400)  # 24 hours
        return result

    # ── Deterministic spending summary (no AI) ───────────────────
    @staticmethod
    def summarize_spending(statement) -> dict:
        """
        Summarise a bank statement's transactions into spending buckets.

        Deterministic — no AI. Groups transactions by bucket (from
        SPENDING_BUCKETS) and produces monthly totals + overall trends.

        Returns a dict shaped for direct template rendering.
        """
        txs = list(statement.transactions.all())
        if not txs:
            return {
                'buckets': [],
                'monthly': [],
                'totals': {'credit': 0.0, 'debit': 0.0, 'net': 0.0},
            }

        buckets = defaultdict(Decimal)
        monthly = defaultdict(lambda: {'credit': Decimal('0'), 'debit': Decimal('0')})
        totals = {'credit': Decimal('0'), 'debit': Decimal('0')}

        for tx in txs:
            desc = (tx.description or '').lower()
            bucket = 'other'
            for name, keywords in SPENDING_BUCKETS.items():
                if any(kw in desc for kw in keywords):
                    bucket = name
                    break

            amount = tx.amount or Decimal('0')
            if tx.transaction_type == 'credit':
                totals['credit'] += amount
            else:
                totals['debit'] += amount
                buckets[bucket] += amount

            if tx.transaction_date:
                month_key = tx.transaction_date.strftime('%Y-%m')
                if tx.transaction_type == 'credit':
                    monthly[month_key]['credit'] += amount
                else:
                    monthly[month_key]['debit'] += amount

        sorted_buckets = sorted(
            ({'bucket': k, 'amount': float(v)} for k, v in buckets.items() if v > 0),
            key=lambda x: x['amount'],
            reverse=True,
        )

        sorted_months = sorted(monthly.keys())
        monthly_series = [
            {
                'month': m,
                'credit': float(monthly[m]['credit']),
                'debit': float(monthly[m]['debit']),
                'net': float(monthly[m]['credit'] - monthly[m]['debit']),
            }
            for m in sorted_months
        ]

        return {
            'buckets': sorted_buckets,
            'monthly': monthly_series,
            'totals': {
                'credit': float(totals['credit']),
                'debit': float(totals['debit']),
                'net': float(totals['credit'] - totals['debit']),
            },
        }