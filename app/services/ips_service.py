"""
IPS QR Code Service - Generisanje QR kodova po NBS standardu.

REFERENCE: https://ips.nbs.rs

Koristi se za generisanje IPS QR kodova na uplatnicama
koji se mogu skenirati u mBanking aplikacijama.
"""
import qrcode
from qrcode.constants import ERROR_CORRECT_M
from io import BytesIO
from decimal import Decimal
from typing import Optional
import re
import base64


class IPSService:
    """
    Generiše IPS QR kodove prema specifikaciji Narodne Banke Srbije.

    KRITIČNO - NBS pravila:
    - R tag: 18 cifara domaćeg računa (NE IBAN!)
    - RO tag: MAX 25 karaktera
    - I tag: 5-18 karaktera, format RSD{iznos,decimale}
    - P tag: OPCIONALAN - ako se ne koristi, potpuno izostaviti
    - SF: 221 za pravna lica, 289 za građane
    """

    IPS_VERSION = '01'
    MAX_RECIPIENT_NAME = 70  # Do 3 reda
    MAX_PURPOSE = 35
    MAX_REFERENCE = 25  # KORIGOVANO sa 35!

    # Default za B2B transakcije
    DEFAULT_PURPOSE_CODE = '221'  # Usluge pravnim licima

    def __init__(self, settings=None):
        self.settings = settings

    @staticmethod
    def normalize_account_number(account: str) -> str:
        """
        Normalizuje broj računa u 18-cifreni format za IPS.

        Podržava formate:
        - 265-1234567890-12 → 265000123456789012
        - RS35265... (IBAN) → 265000123456789012
        - 265000123456789012 (već normalizovan)

        Returns:
            18-cifreni string (bez crtica)

        Raises:
            ValueError: Ako format nije validan
        """
        if not account:
            raise ValueError("Account number is required")

        # Ukloni razmake
        account = account.strip()

        # Ako je IBAN (RS35...), izvuci domaći račun
        if account.upper().startswith('RS'):
            # RS + 2 check digits + 18 cifara računa
            if len(account) >= 22:
                account = account[4:22]  # Preskoči RS35, uzmi 18 cifara

        # Ukloni crtice i proveri format XXX-XXXXXXXXXX-XX
        if '-' in account:
            parts = account.split('-')
            if len(parts) == 3:
                bank = parts[0].zfill(3)       # 3 cifre banke
                main = parts[1].zfill(13)       # 13 cifara računa
                check = parts[2].zfill(2)       # 2 kontrolne cifre
                account = bank + main + check

        # Ukloni sve ne-cifre
        account = re.sub(r'\D', '', account)

        # Dopuni nulama do 18 cifara
        if len(account) < 18:
            account = account.zfill(18)

        # Validacija
        if len(account) != 18:
            raise ValueError(f"Account must be 18 digits, got {len(account)}")

        if not account.isdigit():
            raise ValueError("Account must contain only digits")

        return account

    @staticmethod
    def calculate_mod97_control(reference_base: str) -> int:
        """Računa MOD 97 kontrolnu cifru po ISO 7064."""
        check_number = int(reference_base + "00")
        return 98 - (check_number % 97)

    @staticmethod
    def generate_payment_reference(tenant_id: int, invoice_seq: int) -> dict:
        """
        Generiše poziv na broj - MAX 25 karaktera za IPS!

        Format: 97{tenant_id:06d}{seq:05d} = 2+6+5 = 13 cifara (OK za 25 max)
        """
        # Skrati invoice_seq na 5 cifara da stane u 25 char limit
        base = f"{tenant_id:06d}{invoice_seq:05d}"
        control = IPSService.calculate_mod97_control(base)

        full_ref = f"97{base}"  # 13 cifara - OK za RO tag

        return {
            'model': '97',
            'base': base,
            'control': f"{control:02d}",
            'full': full_ref,
            'display': f"97 {base[:6]} {base[6:]}",
            'formatted': f"97 {base[:6]}-{base[6:]}-{control:02d}"
        }

    def format_amount(self, amount: Decimal) -> str:
        """
        Formatira iznos za IPS I tag.

        Format: RSD{iznos,decimale} bez razmaka
        Min 5, max 18 karaktera.

        Primeri:
        - 5400.00 → "RSD5400,00"
        - 12345.67 → "RSD12345,67"
        """
        # Format sa 2 decimale, zameni tačku zarezom
        amount_str = f"{amount:.2f}".replace('.', ',')
        result = f"RSD{amount_str}"

        # Validacija dužine
        if len(result) < 5 or len(result) > 18:
            raise ValueError(f"Amount string must be 5-18 chars, got {len(result)}: {result}")

        return result

    def generate_qr_string(
        self,
        payment,
        tenant,
        settings=None,
        include_payer: bool = False  # Default: NE uključuj P tag
    ) -> str:
        """
        Generiše IPS format string za QR kod.

        VAŽNO: P tag se podrazumevano izostavlja jer banka
        popunjava podatke o platiocu iz naloga!
        """
        s = settings or self.settings
        if not s:
            raise ValueError("PlatformSettings required for IPS generation")

        # 1. Račun primaoca - 18 cifara (NE IBAN!)
        account = self.normalize_account_number(s.company_bank_account)

        # 2. Naziv primaoca (max 70, do 3 reda)
        recipient = self._truncate(s.company_name or 'SERVISHUB DOO', self.MAX_RECIPIENT_NAME)

        # 3. Iznos - format RSD{iznos,decimale}
        amount = self.format_amount(payment.total_amount)

        # 4. Šifra plaćanja - 221 za B2B
        purpose_code = s.ips_purpose_code or self.DEFAULT_PURPOSE_CODE

        # 5. Svrha (max 35)
        purpose = self._truncate(f"Pretplata {payment.invoice_number}", self.MAX_PURPOSE)

        # 6. Poziv na broj (max 25!)
        reference = payment.payment_reference or ''
        reference = re.sub(r'[\s\-]', '', reference)  # Ukloni razmake i crtice
        if len(reference) > self.MAX_REFERENCE:
            reference = reference[:self.MAX_REFERENCE]

        # Sastavi string - BEZ P taga ako include_payer=False
        parts = [
            "K:PR",
            f"V:{self.IPS_VERSION}",
            "C:1",
            f"R:{account}",
            f"N:{recipient}",
            f"I:{amount}",
        ]

        # P tag je OPCIONALAN - ako se ne uključuje, NE dodajemo prazan tag
        if include_payer and tenant and tenant.name:
            payer = self._truncate(tenant.name, self.MAX_RECIPIENT_NAME)
            parts.append(f"P:{payer}")

        parts.append(f"SF:{purpose_code}")
        parts.append(f"S:{purpose}")
        # RO tag SAMO ako postoji reference - prazan RO kvari QR kod!
        if reference:
            parts.append(f"RO:{reference}")

        return '|'.join(parts)

    def generate_qr_image(
        self,
        qr_string: str,
        size: int = 300,
        border: int = 4
    ) -> bytes:
        """Generiše QR kod sliku kao PNG."""
        qr = qrcode.QRCode(
            version=None,
            error_correction=ERROR_CORRECT_M,
            box_size=10,
            border=border,
        )
        qr.add_data(qr_string)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        # Resize ako je potrebno
        if hasattr(img, 'resize'):
            img = img.resize((size, size))

        buffer = BytesIO()
        img.save(buffer, format='PNG')
        return buffer.getvalue()

    def generate_qr_base64(self, qr_string: str, size: int = 300) -> str:
        """Generiše QR kao base64 data URL."""
        png_bytes = self.generate_qr_image(qr_string, size)
        b64 = base64.b64encode(png_bytes).decode('utf-8')
        return f"data:image/png;base64,{b64}"

    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        """Skraćuje tekst na max dužinu."""
        text = text.replace('|', ' ').replace('\n', ' ').strip()
        if len(text) > max_len:
            return text[:max_len-3] + '...'
        return text

    @staticmethod
    def validate_account(account: str) -> bool:
        """Validira domaći broj računa."""
        try:
            normalized = IPSService.normalize_account_number(account)
            return len(normalized) == 18
        except ValueError:
            return False