"""
PDF Service - Generisanje uplatnica i računa.

Koristi ReportLab za PDF generaciju.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from io import BytesIO
from datetime import datetime
from decimal import Decimal
from typing import Optional

from .ips_service import IPSService


class PDFService:
    """
    Generiše PDF dokumente za billing:
    - Uplatnica (payment slip) sa IPS QR
    - Račun/Faktura (invoice)
    """

    # Uplatnica dimenzije (standardna srpska uplatnica)
    UPLATNICA_WIDTH = 200 * mm
    UPLATNICA_HEIGHT = 99 * mm

    def __init__(self, settings=None):
        self.settings = settings
        self.ips_service = IPSService(settings)

    def generate_uplatnica(self, payment, tenant, settings=None) -> bytes:
        """
        Generiše srpsku uplatnicu u PDF formatu.

        Args:
            payment: SubscriptionPayment object
            tenant: Tenant object
            settings: PlatformSettings

        Returns:
            PDF kao bytes
        """
        s = settings or self.settings
        buffer = BytesIO()

        c = canvas.Canvas(buffer, pagesize=(self.UPLATNICA_WIDTH, self.UPLATNICA_HEIGHT))

        # Bela pozadina
        c.setFillColor(colors.white)
        c.rect(0, 0, self.UPLATNICA_WIDTH, self.UPLATNICA_HEIGHT, fill=1)

        # Border
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.5)
        c.rect(2*mm, 2*mm, self.UPLATNICA_WIDTH - 4*mm, self.UPLATNICA_HEIGHT - 4*mm)

        # Naslov
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(8*mm, self.UPLATNICA_HEIGHT - 12*mm, "NALOG ZA UPLATU")

        # Leva strana - Primalac i svrha
        y = self.UPLATNICA_HEIGHT - 22*mm

        c.setFont("Helvetica", 7)
        c.drawString(8*mm, y, "Primalac:")
        c.setFont("Helvetica-Bold", 9)
        c.drawString(8*mm, y - 5*mm, s.company_name or "SERVISHUB DOO")

        y -= 15*mm
        c.setFont("Helvetica", 7)
        c.drawString(8*mm, y, "Svrha uplate:")
        c.setFont("Helvetica", 9)
        c.drawString(8*mm, y - 5*mm, f"Pretplata {payment.invoice_number}")

        y -= 15*mm
        c.setFont("Helvetica", 7)
        c.drawString(8*mm, y, "Uplatilac:")
        c.setFont("Helvetica-Bold", 9)
        c.drawString(8*mm, y - 5*mm, tenant.name or "")

        # Desna strana - Podaci za uplatu
        x_right = 105*mm
        y = self.UPLATNICA_HEIGHT - 22*mm

        c.setFont("Helvetica", 7)
        c.drawString(x_right, y, "Šifra plaćanja:")
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x_right, y - 5*mm, s.ips_purpose_code or "221")

        y -= 15*mm
        c.setFont("Helvetica", 7)
        c.drawString(x_right, y, "Valuta:")
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x_right, y - 5*mm, payment.currency or "RSD")

        c.drawString(x_right + 25*mm, y, "Iznos:")
        c.setFont("Helvetica-Bold", 12)
        c.drawString(x_right + 25*mm, y - 5*mm, f"{payment.total_amount:,.2f}")

        y -= 15*mm
        c.setFont("Helvetica", 7)
        c.drawString(x_right, y, "Račun primaoca:")
        c.setFont("Helvetica-Bold", 9)
        account = s.company_bank_account or ""
        c.drawString(x_right, y - 5*mm, account)

        y -= 15*mm
        c.setFont("Helvetica", 7)
        c.drawString(x_right, y, "Model:")
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x_right, y - 5*mm, payment.payment_reference_model or "97")

        c.setFont("Helvetica", 7)
        c.drawString(x_right + 20*mm, y, "Poziv na broj:")
        c.setFont("Helvetica-Bold", 9)
        ref_display = payment.payment_reference or ""
        c.drawString(x_right + 20*mm, y - 5*mm, ref_display)

        # QR Kod - donji desni ugao
        qr_size = 30*mm
        qr_x = self.UPLATNICA_WIDTH - qr_size - 8*mm
        qr_y = 8*mm

        if payment.ips_qr_string:
            try:
                qr_bytes = self.ips_service.generate_qr_image(payment.ips_qr_string, size=150)
                qr_img = ImageReader(BytesIO(qr_bytes))
                c.drawImage(qr_img, qr_x, qr_y, width=qr_size, height=qr_size)
            except Exception:
                # Ako QR ne uspe, nastavi bez njega
                pass

        # Završi
        c.save()
        return buffer.getvalue()

    def generate_invoice_pdf(self, payment, tenant, settings=None) -> bytes:
        """
        Generiše detaljan račun/fakturu u PDF formatu.

        Args:
            payment: SubscriptionPayment object sa items_json
            tenant: Tenant object
            settings: PlatformSettings

        Returns:
            PDF kao bytes
        """
        s = settings or self.settings
        buffer = BytesIO()

        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        # Header
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, height - 50, "RAČUN / FAKTURA")

        c.setFont("Helvetica", 10)
        c.drawString(50, height - 70, f"Broj: {payment.invoice_number}")
        c.drawString(50, height - 85, f"Datum: {payment.created_at.strftime('%d.%m.%Y')}")
        due_date = payment.due_date or payment.created_at
        if hasattr(due_date, 'strftime'):
            c.drawString(50, height - 100, f"Valuta plaćanja: {due_date.strftime('%d.%m.%Y')}")

        # Primalac (mi)
        y = height - 140
        c.setFont("Helvetica-Bold", 10)
        c.drawString(50, y, "PRIMALAC:")
        c.setFont("Helvetica", 10)
        c.drawString(50, y - 15, s.company_name or "SERVISHUB DOO")
        c.drawString(50, y - 30, s.company_address or "")
        c.drawString(50, y - 45, f"Račun: {s.company_bank_account or ''}")

        # Platilac (tenant)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(300, y, "PLATILAC:")
        c.setFont("Helvetica", 10)
        c.drawString(300, y - 15, tenant.name or "")
        if hasattr(tenant, 'adresa_sedista'):
            c.drawString(300, y - 30, tenant.adresa_sedista or "")
        if hasattr(tenant, 'pib') and tenant.pib:
            c.drawString(300, y - 45, f"PIB: {tenant.pib}")

        # Tabela stavki
        y = height - 220
        c.setFont("Helvetica-Bold", 10)
        c.drawString(50, y, "R.br")
        c.drawString(80, y, "Opis")
        c.drawString(350, y, "Kol.")
        c.drawString(400, y, "Cena")
        c.drawString(480, y, "Ukupno")

        c.line(50, y - 5, 550, y - 5)

        y -= 20
        c.setFont("Helvetica", 10)
        items = getattr(payment, 'items_json', None) or []
        for i, item in enumerate(items, 1):
            c.drawString(50, y, str(i))
            desc = item.get('description', '')[:50] if isinstance(item, dict) else str(item)[:50]
            c.drawString(80, y, desc)
            qty = item.get('quantity', 1) if isinstance(item, dict) else 1
            c.drawString(350, y, str(qty))
            unit_price = item.get('unit_price', 0) if isinstance(item, dict) else 0
            c.drawString(400, y, f"{unit_price:,.2f}")
            total = item.get('total', 0) if isinstance(item, dict) else 0
            c.drawString(480, y, f"{total:,.2f}")
            y -= 15

        # Ako nema stavki, prikaži osnovne info
        if not items:
            c.drawString(50, y, "1")
            c.drawString(80, y, f"Mesečna pretplata - {payment.invoice_number}")
            c.drawString(350, y, "1")
            c.drawString(400, y, f"{float(payment.total_amount):,.2f}")
            c.drawString(480, y, f"{float(payment.total_amount):,.2f}")
            y -= 15

        # Totali
        y -= 20
        c.line(350, y + 10, 550, y + 10)

        c.setFont("Helvetica", 10)
        subtotal = getattr(payment, 'subtotal', payment.total_amount)
        c.drawString(350, y, "Osnovica:")
        c.drawString(480, y, f"{float(subtotal):,.2f} RSD")

        discount = getattr(payment, 'discount_amount', None)
        if discount and float(discount) > 0:
            y -= 15
            c.drawString(350, y, "Popust:")
            c.drawString(480, y, f"-{float(discount):,.2f} RSD")

        y -= 15
        c.setFont("Helvetica-Bold", 12)
        c.drawString(350, y, "ZA UPLATU:")
        c.drawString(480, y, f"{float(payment.total_amount):,.2f} RSD")

        # Uplatni podaci
        y -= 50
        c.setFont("Helvetica-Bold", 10)
        c.drawString(50, y, "PODACI ZA UPLATU:")
        c.setFont("Helvetica", 10)
        c.drawString(50, y - 15, f"Račun: {s.company_bank_account or ''}")
        c.drawString(50, y - 30, f"Poziv na broj: {payment.payment_reference or ''}")
        c.drawString(50, y - 45, f"Svrha: Pretplata {payment.invoice_number}")

        # QR kod
        if payment.ips_qr_string:
            try:
                qr_bytes = self.ips_service.generate_qr_image(payment.ips_qr_string, size=200)
                qr_img = ImageReader(BytesIO(qr_bytes))
                c.drawImage(qr_img, 400, y - 80, width=50*mm, height=50*mm)
                c.setFont("Helvetica", 8)
                c.drawString(400, y - 90, "Skenirajte za plaćanje")
            except Exception:
                pass

        # Footer
        c.setFont("Helvetica", 8)
        c.drawString(50, 30, f"Generisano: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        c.drawString(400, 30, "ServisHub - www.servishub.rs")

        c.save()
        return buffer.getvalue()