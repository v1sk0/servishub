"""
Base class za sve bank parsere.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any
import re


@dataclass
class ParsedTransaction:
    """Standardized transaction format."""
    type: str  # CREDIT or DEBIT
    date: date
    amount: Decimal
    currency: str = 'RSD'

    # Payer info
    payer_name: Optional[str] = None
    payer_account: Optional[str] = None
    payer_address: Optional[str] = None

    # Reference (poziv na broj)
    reference: Optional[str] = None
    reference_model: Optional[str] = None
    reference_raw: Optional[str] = None

    # Purpose
    purpose: Optional[str] = None
    purpose_code: Optional[str] = None

    # Bank-specific
    bank_id: Optional[str] = None
    value_date: Optional[date] = None
    booking_date: Optional[date] = None

    # Raw data for debugging
    raw: Optional[Dict[str, Any]] = None


@dataclass
class ParseResult:
    """Result of parsing a bank statement."""
    bank_code: str
    bank_name: str
    format: str  # CSV, XML, MT940
    encoding: str
    statement_date: Optional[date]
    statement_number: Optional[str]
    transactions: List[ParsedTransaction]
    warnings: List[str] = field(default_factory=list)

    def to_dict(self):
        return {
            'bank_code': self.bank_code,
            'bank_name': self.bank_name,
            'format': self.format,
            'encoding': self.encoding,
            'statement_date': self.statement_date.isoformat() if self.statement_date else None,
            'statement_number': self.statement_number,
            'transactions': [
                {
                    'type': t.type,
                    'date': t.date.isoformat(),
                    'amount': float(t.amount),
                    'currency': t.currency,
                    'payer_name': t.payer_name,
                    'payer_account': t.payer_account,
                    'payer_address': t.payer_address,
                    'reference': t.reference,
                    'reference_model': t.reference_model,
                    'reference_raw': t.reference_raw,
                    'purpose': t.purpose,
                    'purpose_code': t.purpose_code,
                    'bank_id': t.bank_id,
                    'value_date': t.value_date.isoformat() if t.value_date else None,
                    'booking_date': t.booking_date.isoformat() if t.booking_date else None,
                    'raw': t.raw
                }
                for t in self.transactions
            ],
            'warnings': self.warnings or []
        }


class BaseBankParser(ABC):
    """
    Abstract base class za bank statement parsere.

    Svaka banka ima svoj format izvoda. Ovaj base class
    definiše zajednički interface i helper metode.
    """

    BANK_CODE: str = 'UNK'
    BANK_NAME: str = 'Unknown Bank'

    # Reference pattern: Model + broj
    # Npr: "97 000123 000001" ili "97000123000001"
    REFERENCE_PATTERN = re.compile(r'(\d{2})\s*(\d{6,18})')

    @abstractmethod
    def can_parse(self, content: bytes, filename: str) -> bool:
        """
        Proverava da li ovaj parser može da parsira dati fajl.

        Args:
            content: Raw file bytes
            filename: Original filename

        Returns:
            True if this parser can handle the file
        """
        pass

    @abstractmethod
    def parse(self, content: bytes, filename: str) -> ParseResult:
        """
        Parsira bank statement.

        Args:
            content: Raw file bytes
            filename: Original filename

        Returns:
            ParseResult with transactions
        """
        pass

    def normalize_reference(self, raw_reference: str) -> tuple:
        """
        Normalizuje poziv na broj u standardni format.

        Args:
            raw_reference: Raw reference string from bank

        Returns:
            (model, cleaned_reference) ili (None, None)
        """
        if not raw_reference:
            return None, None

        # Ukloni razmake i crte
        cleaned = re.sub(r'[\s\-]', '', raw_reference)

        # Pokušaj da izvučeš model i broj
        match = self.REFERENCE_PATTERN.match(cleaned)
        if match:
            model = match.group(1)
            number = match.group(2)
            return model, number

        return None, cleaned

    def parse_amount(self, amount_str: str) -> Decimal:
        """
        Parsira iznos iz stringa.
        Podržava: 1.234,56 (SR format) i 1,234.56 (EN format)
        """
        if not amount_str:
            return Decimal('0')

        # Ukloni whitespace
        amount_str = amount_str.strip()

        # Detektuj format
        if ',' in amount_str and '.' in amount_str:
            if amount_str.rfind(',') > amount_str.rfind('.'):
                # SR format: 1.234,56
                amount_str = amount_str.replace('.', '').replace(',', '.')
            else:
                # EN format: 1,234.56
                amount_str = amount_str.replace(',', '')
        elif ',' in amount_str:
            # Samo zarez - SR decimalni separator
            amount_str = amount_str.replace(',', '.')

        return Decimal(amount_str)

    def parse_date(self, date_str: str, formats: List[str] = None) -> Optional[date]:
        """
        Parsira datum iz stringa.

        Default formats: DD.MM.YYYY, YYYY-MM-DD, DD/MM/YYYY
        """
        if not date_str:
            return None

        date_str = date_str.strip()

        formats = formats or [
            '%d.%m.%Y',
            '%Y-%m-%d',
            '%d/%m/%Y',
            '%d-%m-%Y',
            '%Y%m%d'
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue

        return None

    def detect_encoding(self, content: bytes) -> str:
        """Detektuje encoding fajla."""
        # Probaj UTF-8 prvo
        try:
            content.decode('utf-8')
            return 'utf-8'
        except UnicodeDecodeError:
            pass

        # Probaj CP1250 (Windows Central European)
        try:
            content.decode('cp1250')
            return 'cp1250'
        except UnicodeDecodeError:
            pass

        # Fallback na latin-1
        return 'latin-1'