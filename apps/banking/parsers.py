"""Bank statement parsers for South African banks.

This module provides parsers that extract transactions from the raw text of
bank statements (obtained via pypdf). Each parser handles the specific layout
of a bank. The output is a list of dicts compatible with BankTransaction.
"""
import re
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import List, Dict, Any, Optional

from django.utils import timezone


class BaseBankStatementParser(ABC):
    """Abstract base class for bank statement parsers."""

    @abstractmethod
    def parse(self, text: str) -> List[Dict[str, Any]]:
        pass

    @staticmethod
    def _parse_date(date_str: str) -> Optional[datetime.date]:
        date_str = date_str.strip()
        formats = [
            '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d', '%Y-%m-%d',
            '%d %b %Y', '%d %B %Y', '%d/%m', '%d-%m',
        ]
        for fmt in formats:
            try:
                if fmt in ('%d/%m', '%d-%m'):
                    parsed = datetime.strptime(date_str, fmt)
                    year = timezone.now().year
                    return parsed.replace(year=year).date()
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _parse_amount(amount_str: str) -> Optional[Decimal]:
        if not amount_str:
            return None
        # Strip currency, spaces; keep digits, minus, dot, comma
        cleaned = re.sub(r'[^\d,.\-]', '', amount_str)
        cleaned = cleaned.replace(',', '').replace(' ', '')
        # Handle trailing minus (European style)
        if cleaned.endswith('-'):
            cleaned = '-' + cleaned[:-1]
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None

    @staticmethod
    def _detect_transaction_type(amount: Decimal) -> str:
        return 'credit' if amount >= 0 else 'debit'


class GenericBankStatementParser(BaseBankStatementParser):
    """
    Generic fallback parser. Handles the common layout:
    DD/MM/YYYY  Description  Amount
    DD/MM       Description  Amount
    Description  Amount  DD/MM/YYYY
    """

    def parse(self, text: str) -> List[Dict[str, Any]]:
        transactions = []
        lines = text.split('\n')
        pending_date = None
        pending_desc = ""

        date_at_start = re.compile(r'^\s*(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\s+(.*)$')
        amount_pattern = re.compile(r'([+-]?[\d,]+\.\d{2})')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            m = date_at_start.match(line)
            if m:
                date_str = m.group(1)
                rest = m.group(2)
                amt = amount_pattern.search(rest)
                if amt:
                    amount = self._parse_amount(amt.group(1))
                    tx_date = self._parse_date(date_str)
                    if amount is not None and tx_date:
                        desc = rest[:amt.start()].strip()
                        tx_type = self._detect_transaction_type(amount)
                        if amount < 0:
                            amount = abs(amount)
                        transactions.append({
                            'transaction_date': tx_date,
                            'description': desc,
                            'amount': amount,
                            'transaction_type': tx_type,
                            'raw_data': {'line': line},
                        })
                    pending_date = None
                    pending_desc = ""
                else:
                    pending_date = date_str
                    pending_desc = rest
            else:
                if pending_date:
                    amt = amount_pattern.search(line)
                    if amt:
                        amount = self._parse_amount(amt.group(1))
                        tx_date = self._parse_date(pending_date)
                        if amount is not None and tx_date:
                            desc_part = line[:amt.start()].strip()
                            full_desc = f"{pending_desc} {desc_part}".strip()
                            tx_type = self._detect_transaction_type(amount)
                            if amount < 0:
                                amount = abs(amount)
                            transactions.append({
                                'transaction_date': tx_date,
                                'description': full_desc,
                                'amount': amount,
                                'transaction_type': tx_type,
                                'raw_data': {'line': line},
                            })
                        pending_date = None
                        pending_desc = ""
                    else:
                        pending_desc += " " + line
        return transactions


class CapitecBankStatementParser(BaseBankStatementParser):
    """
    Parser for Capitec Bank statements.

    Format examples observed:
        Date Description Category Money In Money Out Fee*Balance
        01/02/2026 Thuthukageneraldeale Siyabuswa (Card 2438) Groceries -22.00 6 505.22
        01/02/2026 Banking App Immediate Payment: Mdu Digital Payments -75.00 -1.006 421.03

    Strategy:
        - Find all lines starting with a DD/MM/YYYY date.
        - Take the first amount with a decimal .XX as the transaction amount
          (money in / money out), ignoring the trailing balance.
        - Treat trailing positive amounts without sign as credits only if the
          description clearly suggests income (Salary, Payment Received, etc.).
    """

    # Amount pattern: negative optional, digits with comma, decimal
    AMOUNT_RE = re.compile(r'-?\d{1,3}(?:,\d{3})*\.\d{2}|-?\d+\.\d{2}')

    # Income keywords — used to decide credit vs debit for unsigned amounts
    INCOME_KEYWORDS = (
        'salary', 'wages', 'payroll', 'stipend',
        'payment received', 'transfer received',
        'deposit', 'refund', 'cash deposit',
        'allowance', 'other income', 'interest received',
    )

    def parse(self, text: str) -> List[Dict[str, Any]]:
        transactions = []
        lines = text.split('\n')
        pending_date = None
        pending_desc = ""

        for line in lines:
            line = line.strip()
            if not line:
                continue

            date_match = re.match(r'^(\d{2}/\d{2}/\d{4})\s+(.*)$', line)
            if date_match:
                date_str = date_match.group(1)
                rest = date_match.group(2)

                # Find the FIRST amount. On Capitec, positive amounts (credits)
                # are printed without a '+' or '-' prefix.
                amounts = self.AMOUNT_RE.findall(rest)

                if amounts:
                    # Take the first amount as the transaction value
                    raw_amt = amounts[0]
                    amount = self._parse_amount(raw_amt)
                    tx_date = self._parse_date(date_str)

                    if amount is not None and tx_date:
                        # Description is everything before the first amount
                        first_amt_pos = rest.find(raw_amt)
                        desc = rest[:first_amt_pos].strip()

                        # Decide type
                        desc_lower = desc.lower()
                        if raw_amt.startswith('-'):
                            tx_type = 'debit'
                            amount = abs(amount)
                        elif any(kw in desc_lower for kw in self.INCOME_KEYWORDS):
                            tx_type = 'credit'
                        else:
                            # Unsigned amount, unknown direction: assume debit.
                            # (Capitec prints money-in with a leading space; the
                            # AMOUNT_RE will still match it but we can't tell
                            # reliably from the regex. Income keywords cover the
                            # common cases.)
                            tx_type = 'debit'

                        transactions.append({
                            'transaction_date': tx_date,
                            'description': desc,
                            'amount': amount,
                            'transaction_type': tx_type,
                            'raw_data': {'line': line},
                        })

                    pending_date = None
                    pending_desc = ""
                else:
                    # No amount yet — buffer the description
                    pending_date = date_str
                    pending_desc = rest
            else:
                # Continuation line (no date at start)
                if pending_date:
                    amounts = self.AMOUNT_RE.findall(line)
                    if amounts:
                        raw_amt = amounts[0]
                        amount = self._parse_amount(raw_amt)
                        tx_date = self._parse_date(pending_date)

                        if amount is not None and tx_date:
                            first_amt_pos = line.find(raw_amt)
                            desc_part = line[:first_amt_pos].strip()
                            full_desc = f"{pending_desc} {desc_part}".strip()
                            desc_lower = full_desc.lower()

                            if raw_amt.startswith('-'):
                                tx_type = 'debit'
                                amount = abs(amount)
                            elif any(kw in desc_lower for kw in self.INCOME_KEYWORDS):
                                tx_type = 'credit'
                            else:
                                tx_type = 'debit'

                            transactions.append({
                                'transaction_date': tx_date,
                                'description': full_desc,
                                'amount': amount,
                                'transaction_type': tx_type,
                                'raw_data': {'line': line},
                            })

                        pending_date = None
                        pending_desc = ""
                    else:
                        pending_desc += " " + line

        return transactions


class StandardBankParser(GenericBankStatementParser):
    pass


class FNBParser(GenericBankStatementParser):
    pass


class ABSAParser(GenericBankStatementParser):
    pass


class NedbankParser(GenericBankStatementParser):
    pass


class DiscoveryBankParser(GenericBankStatementParser):
    pass


class TymeBankParser(GenericBankStatementParser):
    pass


class AfricanBankParser(GenericBankStatementParser):
    pass


class InvestecParser(GenericBankStatementParser):
    pass


def get_parser_for_bank(bank_name: str = '') -> BaseBankStatementParser:
    bank_name = (bank_name or '').lower()
    if 'capitec' in bank_name:
        return CapitecBankStatementParser()
    elif 'standard' in bank_name:
        return StandardBankParser()
    elif 'fnb' in bank_name or 'first national' in bank_name:
        return FNBParser()
    elif 'absa' in bank_name:
        return ABSAParser()
    elif 'nedbank' in bank_name:
        return NedbankParser()
    elif 'discovery' in bank_name:
        return DiscoveryBankParser()
    elif 'tyme' in bank_name:
        return TymeBankParser()
    elif 'african' in bank_name:
        return AfricanBankParser()
    elif 'investec' in bank_name:
        return InvestecParser()
    return GenericBankStatementParser()