"""
Smoke test za v303 Billing Enhancement.

Testira:
- IPS QR generacija (NBS format)
- PDF uplatnica/faktura
- Bank parser (Alta XML)
- Payment reference generacija

Pokreni sa: python tests/test_v303_smoke.py
"""
from decimal import Decimal
from datetime import date, datetime
from dataclasses import dataclass
import sys
import os

# Dodaj app folder u path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Mock objekti za testiranje bez DB
@dataclass
class MockSettings:
    company_name: str = "SERVISHUB DOO BEOGRAD"
    company_address: str = "Bulevar Kralja Aleksandra 123"
    company_bank_account: str = "265-1234567890123-45"
    ips_purpose_code: str = "221"


@dataclass
class MockTenant:
    id: int = 42
    name: str = "MOBILNI DOKTOR DOO"


@dataclass
class MockPayment:
    id: int = 1
    invoice_number: str = "SH-2026-000001"
    total_amount: Decimal = Decimal("5400.00")
    currency: str = "RSD"
    payment_reference: str = "970000422026000001"
    payment_reference_model: str = "97"
    ips_qr_string: str = None
    created_at: datetime = None
    due_date: date = None
    subtotal: Decimal = Decimal("5400.00")
    discount_amount: Decimal = Decimal("0")
    items_json: list = None

    def __post_init__(self):
        self.created_at = datetime.now()
        self.due_date = date.today()


def test_ips_account_normalization():
    """Test normalizacije broja računa."""
    print("\n=== Test: IPS Account Normalization ===")
    from app.services.ips_service import IPSService

    test_cases = [
        ("265-1234567890123-45", "265123456789012345"),
        ("265-0000000012345-67", "265000000001234567"),
        ("RS35265123456789012345", "265123456789012345"),
    ]

    for input_val, expected in test_cases:
        try:
            result = IPSService.normalize_account_number(input_val)
            status = "[OK]" if result == expected else "[FAIL]"
            print(f"  {status} '{input_val}' -> '{result}' (expected: {expected})")
        except Exception as e:
            print(f"  [FAIL] '{input_val}' -> ERROR: {e}")

    print("  Done.")


def test_payment_reference_generation():
    """Test generisanja poziva na broj."""
    print("\n=== Test: Payment Reference Generation ===")
    from app.services.ips_service import IPSService

    # Format v3.04: 97 + tenant_id(6 cifara) + year(4) + seq(6 cifara) = 18 cifara
    year = 2026
    test_cases = [
        (42, 1, "970000422026000001"),      # 97 + 000042 + 2026 + 000001
        (123, 456, "970001232026000456"),    # 97 + 000123 + 2026 + 000456
        (1, 99999, "970000012026099999"),    # 97 + 000001 + 2026 + 099999
    ]

    for tenant_id, seq, expected in test_cases:
        result = IPSService.generate_payment_reference(tenant_id, seq, year=year)
        status = "[OK]" if result['full'] == expected else "[FAIL]"
        print(f"  {status} tenant={tenant_id}, seq={seq} -> '{result['full']}' (expected: {expected})")
        print(f"      display: '{result['display']}'")

    print("  Done.")


def test_ips_qr_string_generation():
    """Test generisanja IPS QR stringa."""
    print("\n=== Test: IPS QR String Generation ===")
    from app.services.ips_service import IPSService

    settings = MockSettings()
    tenant = MockTenant()
    payment = MockPayment()

    ips = IPSService(settings)
    qr_string = ips.generate_qr_string(payment, tenant, settings)

    print(f"  QR String: {qr_string}")

    # Validacija komponenti
    checks = [
        ("K:PR" in qr_string, "K:PR tag"),
        ("V:01" in qr_string, "V:01 version"),
        ("R:" in qr_string, "R: recipient account"),
        ("N:" in qr_string, "N: recipient name"),
        ("I:RSD" in qr_string, "I: amount with RSD"),
        ("SF:221" in qr_string, "SF: purpose code"),
        ("RO:" in qr_string, "RO: reference"),
        ("|P:" not in qr_string, "P tag omitted (correct)"),
    ]

    for check, desc in checks:
        status = "[OK]" if check else "[FAIL]"
        print(f"  {status} {desc}")

    # Proveri dužinu RO taga (max 25)
    ro_part = [p for p in qr_string.split("|") if p.startswith("RO:")][0]
    ro_value = ro_part[3:]
    ro_ok = len(ro_value) <= 25
    print(f"  {'[OK]' if ro_ok else '[FAIL]'} RO length: {len(ro_value)} (max 25)")

    print("  Done.")


def test_ips_qr_image_generation():
    """Test generisanja QR slike."""
    print("\n=== Test: IPS QR Image Generation ===")
    from app.services.ips_service import IPSService

    settings = MockSettings()
    tenant = MockTenant()
    payment = MockPayment()

    ips = IPSService(settings)
    qr_string = ips.generate_qr_string(payment, tenant, settings)

    try:
        qr_bytes = ips.generate_qr_image(qr_string, size=200)
        print(f"  [OK] QR image generated: {len(qr_bytes)} bytes")

        # Proveri PNG header
        is_png = qr_bytes[:8] == b'\x89PNG\r\n\x1a\n'
        print(f"  {'[OK]' if is_png else '[FAIL]'} Valid PNG format")

        # Base64 verzija
        qr_base64 = ips.generate_qr_base64(qr_string, size=200)
        is_data_url = qr_base64.startswith("data:image/png;base64,")
        print(f"  {'[OK]' if is_data_url else '[FAIL]'} Valid base64 data URL")

    except Exception as e:
        print(f"  [FAIL] QR generation failed: {e}")

    print("  Done.")


def test_pdf_uplatnica_generation():
    """Test generisanja PDF uplatnice."""
    print("\n=== Test: PDF Uplatnica Generation ===")
    from app.services.pdf_service import PDFService
    from app.services.ips_service import IPSService

    settings = MockSettings()
    tenant = MockTenant()
    payment = MockPayment()

    # Generiši IPS string za payment
    ips = IPSService(settings)
    payment.ips_qr_string = ips.generate_qr_string(payment, tenant, settings)

    try:
        pdf_service = PDFService(settings)
        pdf_bytes = pdf_service.generate_uplatnica(payment, tenant, settings)

        print(f"  [OK] Uplatnica PDF generated: {len(pdf_bytes)} bytes")

        # Proveri PDF header
        is_pdf = pdf_bytes[:4] == b'%PDF'
        print(f"  {'[OK]' if is_pdf else '[FAIL]'} Valid PDF format")

        # Sačuvaj za manuelnu inspekciju
        with open("test_uplatnica.pdf", "wb") as f:
            f.write(pdf_bytes)
        print("  [OK] Saved as test_uplatnica.pdf")

    except Exception as e:
        print(f"  [FAIL] Uplatnica generation failed: {e}")
        import traceback
        traceback.print_exc()

    print("  Done.")


def test_pdf_invoice_generation():
    """Test generisanja PDF fakture."""
    print("\n=== Test: PDF Invoice Generation ===")
    from app.services.pdf_service import PDFService
    from app.services.ips_service import IPSService

    settings = MockSettings()
    tenant = MockTenant()
    payment = MockPayment()

    # Generiši IPS string
    ips = IPSService(settings)
    payment.ips_qr_string = ips.generate_qr_string(payment, tenant, settings)

    try:
        pdf_service = PDFService(settings)
        pdf_bytes = pdf_service.generate_invoice_pdf(payment, tenant, settings)

        print(f"  [OK] Invoice PDF generated: {len(pdf_bytes)} bytes")

        # Proveri PDF header
        is_pdf = pdf_bytes[:4] == b'%PDF'
        print(f"  {'[OK]' if is_pdf else '[FAIL]'} Valid PDF format")

        # Sačuvaj za manuelnu inspekciju
        with open("test_invoice.pdf", "wb") as f:
            f.write(pdf_bytes)
        print("  [OK] Saved as test_invoice.pdf")

    except Exception as e:
        print(f"  [FAIL] Invoice generation failed: {e}")
        import traceback
        traceback.print_exc()

    print("  Done.")


def test_alta_bank_parser():
    """Test Alta Banka XML parsera."""
    print("\n=== Test: Alta Bank XML Parser ===")
    from app.services.bank_parsers.alta import AltaBankParser

    # Mock Alta XML
    xml_content = b'''<?xml version="1.0" encoding="UTF-8"?>
<Statement>
    <Header>
        <AccountNumber>265-1234567890-12</AccountNumber>
        <StatementNumber>001</StatementNumber>
        <StatementDate>2026-01-24</StatementDate>
    </Header>
    <Transactions>
        <Transaction>
            <Type>C</Type>
            <Date>2026-01-24</Date>
            <Amount>5400.00</Amount>
            <Currency>RSD</Currency>
            <PayerName>MOBILNI DOKTOR DOO</PayerName>
            <PayerAccount>160-123456-78</PayerAccount>
            <Reference>97 000042 000001</Reference>
            <Purpose>Pretplata SH-2026-000001</Purpose>
            <PurposeCode>221</PurposeCode>
        </Transaction>
        <Transaction>
            <Type>C</Type>
            <Date>2026-01-24</Date>
            <Amount>3980.00</Amount>
            <Currency>RSD</Currency>
            <PayerName>TECH SERVIS DOO</PayerName>
            <PayerAccount>160-654321-99</PayerAccount>
            <Reference>97 000123 000002</Reference>
            <Purpose>Pretplata januar</Purpose>
            <PurposeCode>221</PurposeCode>
        </Transaction>
    </Transactions>
</Statement>'''

    parser = AltaBankParser()

    # Test can_parse
    can_parse = parser.can_parse(xml_content, "izvod.xml")
    print(f"  {'[OK]' if can_parse else '[FAIL]'} can_parse() returns True")

    # Test parse
    try:
        result = parser.parse(xml_content, "izvod.xml")

        print(f"  [OK] Parsed successfully:")
        print(f"      Bank: {result.bank_code} ({result.bank_name})")
        print(f"      Date: {result.statement_date}")
        print(f"      Transactions: {len(result.transactions)}")

        for i, txn in enumerate(result.transactions):
            print(f"      [{i+1}] {txn.type}: {txn.amount} {txn.currency} from {txn.payer_name}")
            print(f"          Reference: {txn.reference_model} {txn.reference}")

        # Proveri normalizaciju reference
        first_txn = result.transactions[0]
        ref_ok = first_txn.reference == "000042000001"
        print(f"  {'[OK]' if ref_ok else '[FAIL]'} Reference normalized correctly")

    except Exception as e:
        print(f"  [FAIL] Parse failed: {e}")
        import traceback
        traceback.print_exc()

    print("  Done.")


def test_bank_parser_registry():
    """Test bank parser registry."""
    print("\n=== Test: Bank Parser Registry ===")
    from app.services.bank_parsers import get_supported_banks, detect_bank_and_parse

    banks = get_supported_banks()
    print(f"  Supported banks: {len(banks)}")
    for bank in banks:
        print(f"      - {bank['code']}: {bank['name']}")

    print("  Done.")


def main():
    print("=" * 60)
    print("v303 Billing Enhancement - Smoke Test")
    print("=" * 60)

    tests = [
        test_ips_account_normalization,
        test_payment_reference_generation,
        test_ips_qr_string_generation,
        test_ips_qr_image_generation,
        test_pdf_uplatnica_generation,
        test_pdf_invoice_generation,
        test_alta_bank_parser,
        test_bank_parser_registry,
    ]

    failed = 0
    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"\n  [FAIL] TEST FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    if failed == 0:
        print("ALL TESTS PASSED [OK]")
    else:
        print(f"FAILED: {failed} test(s)")
    print("=" * 60)

    # Cleanup test files
    for f in ["test_uplatnica.pdf", "test_invoice.pdf"]:
        if os.path.exists(f):
            print(f"\nTest PDF saved: {f}")


if __name__ == "__main__":
    main()