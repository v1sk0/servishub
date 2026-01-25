"""
Alta Banka XML Parser.

Alta banka šalje izvode kao XML attachment na email (pmtnotification format).
Format je specifičan za Alta banku iBanking sistem.
"""
import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List

from .base import BaseBankParser, ParseResult, ParsedTransaction


class AltaBankParser(BaseBankParser):
    """
    Parser za Alta Banka XML izvode (pmtnotification format).

    Pravi XML struktura od Alta banke:
    <pmtnotification>
        <acctid>190-0000000029120-24</acctid>
        <stmtnumber>13</stmtnumber>
        <ledgerbal>
            <dtasof>2026-01-22T00:00:00</dtasof>
        </ledgerbal>
        <trnlist count="3">
            <stmttrn>
                <fitid>870001081810062</fitid>
                <benefit>credit</benefit>  <!-- credit=uplata, debit=isplata -->
                <payeeinfo>
                    <name>FIRMA DOO</name>
                    <city>BEOGRAD</city>
                </payeeinfo>
                <payeeaccountinfo>
                    <acctid>190-0000000023845-38</acctid>
                    <bankid>190</bankid>
                    <bankname>ALTA BANKA A.D. BEOGRAD</bankname>
                </payeeaccountinfo>
                <dtposted>2026-01-22T00:00:00</dtposted>
                <trnamt>125259.00</trnamt>
                <purpose>UPLATA PAZARA</purpose>
                <purposecode>165</purposecode>
                <curdef>RSD</curdef>
                <refnumber>22012026</refnumber>
                <refmodel>97</refmodel>
                <payeerefnumber>220126-20-4-7-pp</payeerefnumber>
                <payeerefmodel>97</payeerefmodel>
            </stmttrn>
        </trnlist>
        <rejected count="0">
            <!-- Odbijene transakcije -->
        </rejected>
    </pmtnotification>
    """

    BANK_CODE = 'ALTA'
    BANK_NAME = 'Alta Banka'

    # Alta banka ima bank ID 190
    ALTA_BANK_ID = '190'

    def can_parse(self, content: bytes, filename: str) -> bool:
        """Proverava da li je Alta Banka XML format."""
        try:
            # Probaj da parsiraš kao XML
            text = content.decode('utf-8')
            root = ET.fromstring(text)

            # Proveri za pmtnotification root element
            if root.tag == 'pmtnotification':
                # Proveri za Alta-specifične markere
                acctid = root.find('acctid')
                if acctid is not None and acctid.text:
                    # Alta računi počinju sa 190-
                    if acctid.text.startswith(self.ALTA_BANK_ID):
                        return True

                # Alternativno, proveri bankname u transakcijama
                trnlist = root.find('trnlist')
                if trnlist is not None:
                    stmttrn = trnlist.find('stmttrn')
                    if stmttrn is not None:
                        bankname = stmttrn.find('.//bankname')
                        if bankname is not None and 'ALTA' in (bankname.text or '').upper():
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

        # Statement info
        statement_number = None
        statement_date = None

        stmtnum_elem = root.find('stmtnumber')
        if stmtnum_elem is not None:
            statement_number = stmtnum_elem.text

        # Datum izvoda iz ledgerbal/dtasof
        ledgerbal = root.find('ledgerbal')
        if ledgerbal is not None:
            dtasof = ledgerbal.find('dtasof')
            if dtasof is not None:
                statement_date = self._parse_datetime(dtasof.text)

        # Parse transactions from trnlist
        trnlist = root.find('trnlist')
        if trnlist is not None:
            for stmttrn in trnlist.findall('stmttrn'):
                try:
                    txn = self._parse_transaction(stmttrn)
                    transactions.append(txn)
                except Exception as e:
                    warnings.append(f'Failed to parse transaction: {str(e)}')

        # Parse rejected transactions (opciono, za informaciju)
        rejected = root.find('rejected')
        if rejected is not None:
            rejected_count = rejected.get('count', '0')
            if rejected_count and int(rejected_count) > 0:
                warnings.append(f'Izvod sadrži {rejected_count} odbijenih transakcija')

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
        """Parsira pojedinačnu transakciju iz stmttrn elementa."""

        # Tip: credit=CREDIT, debit=DEBIT
        benefit_elem = elem.find('benefit')
        if benefit_elem is not None and benefit_elem.text:
            txn_type = 'CREDIT' if benefit_elem.text.lower() == 'credit' else 'DEBIT'
        else:
            txn_type = 'CREDIT'

        # Datum transakcije (dtposted)
        dtposted = elem.find('dtposted')
        txn_date = self._parse_datetime(dtposted.text) if dtposted is not None else date.today()

        # Value date (dtavail)
        dtavail = elem.find('dtavail')
        value_date = self._parse_datetime(dtavail.text) if dtavail is not None else None

        # Iznos
        trnamt = elem.find('trnamt')
        amount = self.parse_amount(trnamt.text) if trnamt is not None else Decimal('0')

        # Valuta
        curdef = elem.find('curdef')
        currency = curdef.text if curdef is not None and curdef.text else 'RSD'

        # Payer info - iz payeeinfo elementa
        payer_name = None
        payer_address = None
        payeeinfo = elem.find('payeeinfo')
        if payeeinfo is not None:
            name_elem = payeeinfo.find('name')
            payer_name = name_elem.text.strip() if name_elem is not None and name_elem.text else None

            city_elem = payeeinfo.find('city')
            payer_address = city_elem.text.strip() if city_elem is not None and city_elem.text else None

        # Payer account - iz payeeaccountinfo
        payer_account = None
        payeeaccountinfo = elem.find('payeeaccountinfo')
        if payeeaccountinfo is not None:
            acctid = payeeaccountinfo.find('acctid')
            payer_account = acctid.text.strip() if acctid is not None and acctid.text else None

        # Reference (poziv na broj) - može biti u refnumber ili payeerefnumber
        # refnumber = poziv na broj primaoca
        # payeerefnumber = poziv na broj platioca
        reference_raw = None
        reference = None
        model = None

        # Prvo probaj refnumber (primateljeva referenca)
        refnumber = elem.find('refnumber')
        refmodel = elem.find('refmodel')

        if refnumber is not None and refnumber.text and refnumber.text.strip():
            reference_raw = refnumber.text.strip()
            model = refmodel.text.strip() if refmodel is not None and refmodel.text else None
            model_part, reference = self.normalize_reference(reference_raw)
            if model_part and not model:
                model = model_part
        else:
            # Ako nema refnumber, koristi payeerefnumber
            payeerefnumber = elem.find('payeerefnumber')
            payeerefmodel = elem.find('payeerefmodel')

            if payeerefnumber is not None and payeerefnumber.text:
                reference_raw = payeerefnumber.text.strip()
                model = payeerefmodel.text.strip() if payeerefmodel is not None and payeerefmodel.text else None
                model_part, reference = self.normalize_reference(reference_raw)
                if model_part and not model:
                    model = model_part

        # Svrha
        purpose = self._get_text(elem, 'purpose')
        purpose_code = self._get_text(elem, 'purposecode')

        # Bank transaction ID
        bank_id = self._get_text(elem, 'fitid')

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

    def _parse_datetime(self, dt_str: str) -> Optional[date]:
        """Parsira datetime string u date (format: 2026-01-22T00:00:00)."""
        if not dt_str:
            return None

        dt_str = dt_str.strip()

        # Format: 2026-01-22T00:00:00
        try:
            if 'T' in dt_str:
                return datetime.fromisoformat(dt_str.replace('Z', '+00:00')).date()
            else:
                return self.parse_date(dt_str)
        except Exception:
            return self.parse_date(dt_str)

    def _get_text(self, elem: ET.Element, tag: str) -> Optional[str]:
        """Helper za čitanje teksta iz child elementa."""
        child = elem.find(tag)
        return child.text.strip() if child is not None and child.text else None
