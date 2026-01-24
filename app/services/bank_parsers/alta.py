"""
Alta Banka XML Parser.

Alta banka šalje izvode kao XML attachment na email.
Format je specifičan za Alta banku.
"""
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal
from typing import Optional, List

from .base import BaseBankParser, ParseResult, ParsedTransaction


class AltaBankParser(BaseBankParser):
    """
    Parser za Alta Banka XML izvode.

    XML struktura (primer):
    <Statement>
        <Header>
            <AccountNumber>265-1234567890-12</AccountNumber>
            <StatementNumber>001</StatementNumber>
            <StatementDate>2026-01-24</StatementDate>
        </Header>
        <Transactions>
            <Transaction>
                <Type>C</Type>  <!-- C=Credit, D=Debit -->
                <Date>2026-01-24</Date>
                <Amount>5400.00</Amount>
                <Currency>RSD</Currency>
                <PayerName>MOBILNI DOKTOR DOO</PayerName>
                <PayerAccount>160-123456-78</PayerAccount>
                <Reference>97 000123 000001</Reference>
                <Purpose>Pretplata SH-2026-000001</Purpose>
                <PurposeCode>289</PurposeCode>
            </Transaction>
        </Transactions>
    </Statement>
    """

    BANK_CODE = 'ALTA'
    BANK_NAME = 'Alta Banka'

    def can_parse(self, content: bytes, filename: str) -> bool:
        """Proverava da li je Alta Banka XML format."""
        try:
            # Probaj da parsiraš kao XML
            text = content.decode('utf-8')
            root = ET.fromstring(text)

            # Proveri karakteristične elemente
            if root.tag == 'Statement':
                # Proveri za Alta-specifične markere
                header = root.find('Header')
                if header is not None:
                    account = header.find('AccountNumber')
                    if account is not None and account.text:
                        # Alta računi počinju sa 265-
                        if account.text.startswith('265'):
                            return True

            return False
        except Exception:
            return False

    def parse(self, content: bytes, filename: str) -> ParseResult:
        """Parsira Alta Banka XML izvod."""
        text = content.decode('utf-8')
        root = ET.fromstring(text)

        transactions: List[ParsedTransaction] = []
        warnings: List[str] = []

        # Header info
        header = root.find('Header')
        statement_date = None
        statement_number = None

        if header is not None:
            date_elem = header.find('StatementDate')
            if date_elem is not None:
                statement_date = self.parse_date(date_elem.text)

            num_elem = header.find('StatementNumber')
            if num_elem is not None:
                statement_number = num_elem.text

        # Transactions
        txns_elem = root.find('Transactions')
        if txns_elem is not None:
            for txn_elem in txns_elem.findall('Transaction'):
                try:
                    txn = self._parse_transaction(txn_elem)
                    transactions.append(txn)
                except Exception as e:
                    warnings.append(f'Failed to parse transaction: {str(e)}')

        return ParseResult(
            bank_code=self.BANK_CODE,
            bank_name=self.BANK_NAME,
            format='XML',
            encoding='utf-8',
            statement_date=statement_date,
            statement_number=statement_number,
            transactions=transactions,
            warnings=warnings
        )

    def _parse_transaction(self, elem: ET.Element) -> ParsedTransaction:
        """Parsira pojedinačnu transakciju."""
        # Tip: C=Credit, D=Debit
        type_elem = elem.find('Type')
        txn_type = 'CREDIT' if type_elem is not None and type_elem.text == 'C' else 'DEBIT'

        # Datum
        date_elem = elem.find('Date')
        txn_date = self.parse_date(date_elem.text) if date_elem is not None else date.today()

        # Iznos
        amount_elem = elem.find('Amount')
        amount = self.parse_amount(amount_elem.text) if amount_elem is not None else Decimal('0')

        # Valuta
        currency_elem = elem.find('Currency')
        currency = currency_elem.text if currency_elem is not None else 'RSD'

        # Platilac
        payer_name = self._get_text(elem, 'PayerName')
        payer_account = self._get_text(elem, 'PayerAccount')
        payer_address = self._get_text(elem, 'PayerAddress')

        # Reference (poziv na broj)
        reference_raw = self._get_text(elem, 'Reference')
        model, reference = self.normalize_reference(reference_raw)

        # Svrha
        purpose = self._get_text(elem, 'Purpose')
        purpose_code = self._get_text(elem, 'PurposeCode')

        # Bank ID
        bank_id = self._get_text(elem, 'TransactionId')

        # Value date
        value_date_elem = elem.find('ValueDate')
        value_date = self.parse_date(value_date_elem.text) if value_date_elem is not None else None

        return ParsedTransaction(
            type=txn_type,
            date=txn_date,
            amount=amount,
            currency=currency,
            payer_name=payer_name,
            payer_account=payer_account,
            payer_address=payer_address,
            reference=reference,
            reference_model=model,
            reference_raw=reference_raw,
            purpose=purpose,
            purpose_code=purpose_code,
            bank_id=bank_id,
            value_date=value_date,
            raw={'xml': ET.tostring(elem, encoding='unicode')}
        )

    def _get_text(self, elem: ET.Element, tag: str) -> Optional[str]:
        """Helper za čitanje teksta iz child elementa."""
        child = elem.find(tag)
        return child.text.strip() if child is not None and child.text else None