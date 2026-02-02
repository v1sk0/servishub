"""
PDF Service - Generisanje uplatnica i računa.

Koristi ReportLab za PDF generaciju.
Podrška za srpsku latinicu kroz DejaVu Sans font ili transliteraciju.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from io import BytesIO
from datetime import datetime
from decimal import Decimal
from typing import Optional
import os

from .ips_service import IPSService

# Registracija Unicode fonta za srpsku latinicu
_FONT_REGISTERED = False
_FONT_NAME = "Helvetica"  # Default fallback
_FONT_NAME_BOLD = "Helvetica-Bold"


def _register_unicode_font():
    """
    Registruje DejaVu Sans font ako je dostupan.
    Fallback na Helvetica ako font nije pronađen.
    """
    global _FONT_REGISTERED, _FONT_NAME, _FONT_NAME_BOLD

    if _FONT_REGISTERED:
        return

    # Lista mogućih lokacija za DejaVu fontove
    font_paths = [
        # Windows
        "C:/Windows/Fonts/DejaVuSans.ttf",
        "C:/Windows/Fonts/dejavusans.ttf",
        # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        # macOS
        "/Library/Fonts/DejaVuSans.ttf",
        # Relative to app
        os.path.join(os.path.dirname(__file__), "fonts", "DejaVuSans.ttf"),
    ]

    font_paths_bold = [
        "C:/Windows/Fonts/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/dejavusans-bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/Library/Fonts/DejaVuSans-Bold.ttf",
        os.path.join(os.path.dirname(__file__), "fonts", "DejaVuSans-Bold.ttf"),
    ]

    font_found = None
    font_bold_found = None

    for path in font_paths:
        if os.path.exists(path):
            font_found = path
            break

    for path in font_paths_bold:
        if os.path.exists(path):
            font_bold_found = path
            break

    if font_found:
        try:
            pdfmetrics.registerFont(TTFont('DejaVuSans', font_found))
            _FONT_NAME = 'DejaVuSans'

            if font_bold_found:
                pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', font_bold_found))
                _FONT_NAME_BOLD = 'DejaVuSans-Bold'
            else:
                _FONT_NAME_BOLD = 'DejaVuSans'

        except Exception:
            pass  # Koristi Helvetica fallback

    _FONT_REGISTERED = True


def _transliterate(text: str) -> str:
    """
    Konvertuje srpsku latinicu u ASCII karaktere.
    Koristi se ako Unicode font nije dostupan.
    """
    if not text:
        return text

    replacements = {
        'č': 'c', 'Č': 'C',
        'ć': 'c', 'Ć': 'C',
        'š': 's', 'Š': 'S',
        'ž': 'z', 'Ž': 'Z',
        'đ': 'dj', 'Đ': 'Dj',
    }

    for serbian, ascii_char in replacements.items():
        text = text.replace(serbian, ascii_char)

    return text


def _safe_text(text: str) -> str:
    """
    Priprema tekst za PDF - transliteruje ako nema Unicode fonta.
    """
    if not text:
        return ""

    # Ako koristimo Helvetica (nema Unicode podršku), transliteriši
    if _FONT_NAME == "Helvetica":
        return _transliterate(text)

    return text


class PDFService:
    """
    Generiše PDF dokumente za billing:
    - Uplatnica (payment slip) sa IPS QR - standardni NBS format
    - Račun/Faktura (invoice)
    """

    # Standardne dimenzije srpske uplatnice po NBS pravilniku
    # 210 x 99 mm (1/3 A4 papira)
    UPLATNICA_WIDTH = 210 * mm
    UPLATNICA_HEIGHT = 99 * mm

    def __init__(self, settings=None):
        self.settings = settings
        self.ips_service = IPSService(settings)
        # Registruj font pri kreiranju servisa
        _register_unicode_font()

    def generate_uplatnica(self, payment, tenant, settings=None) -> bytes:
        """
        Generiše standardnu srpsku uplatnicu (Obrazac br. 1) po NBS pravilniku.

        Dimenzije: 210 x 99 mm
        Layout po NBS standardu:
        - Header "NALOG ZA UPLATU" preko cele širine (bez vertikalne linije)
        - Ispod headera: leva strana (platilac) | desna strana (podaci o plaćanju)
        - Labele su NA gornjoj liniji polja (presecaju liniju)

        Args:
            payment: SubscriptionPayment object
            tenant: Tenant object (platilac)
            settings: PlatformSettings (primalac)

        Returns:
            PDF kao bytes
        """
        s = settings or self.settings
        buffer = BytesIO()

        c = canvas.Canvas(buffer, pagesize=(self.UPLATNICA_WIDTH, self.UPLATNICA_HEIGHT))

        # Dimenzije
        W = self.UPLATNICA_WIDTH
        H = self.UPLATNICA_HEIGHT
        margin = 2 * mm
        mid_x = 105 * mm  # Vertikalna podela levo/desno
        header_h = 12 * mm  # Visina header sekcije

        # Bela pozadina
        c.setFillColor(colors.white)
        c.rect(0, 0, W, H, fill=1)

        c.setStrokeColor(colors.black)
        c.setFillColor(colors.black)

        # ============================================================
        # SPOLJNI OKVIR
        # ============================================================
        c.setLineWidth(0.8)
        c.rect(margin, margin, W - 2*margin, H - 2*margin)

        # ============================================================
        # HEADER - "NALOG ZA UPLATU" (preko cele širine)
        # ============================================================
        header_y = H - margin - header_h

        # Horizontalna linija ispod headera
        c.setLineWidth(0.5)
        c.line(margin, header_y, W - margin, header_y)

        # Tekst headera - centriran
        c.setFont(_FONT_NAME_BOLD, 14)
        c.drawCentredString(W / 2, header_y + 4*mm, "NALOG ZA UPLATU")

        # ============================================================
        # VERTIKALNA LINIJA - počinje ISPOD headera
        # ============================================================
        c.setLineWidth(0.5)
        c.line(mid_x, margin, mid_x, header_y)

        # ============================================================
        # HELPER: Crtanje polja sa labelom IZNAD boxa
        # ============================================================
        def draw_field_with_label(x, y, width, height, label, value=None, value_font_size=9,
                                   value_bold=False, align='left', label_font_size=6):
            """
            Crta polje gde je labela pozicionirana IZNAD boxa.
            Tekst je vertikalno i horizontalno centriran prema align parametru.
            """
            # Labela IZNAD boxa (1.5mm iznad)
            c.setFont(_FONT_NAME_BOLD, label_font_size)
            c.setFillColor(colors.black)
            c.drawString(x, y + height + 1.5*mm, label)

            # Box
            c.setLineWidth(0.3)
            c.rect(x, y, width, height)

            # Vrednost unutar polja - VERTIKALNO CENTRIRANO
            if value:
                if value_bold:
                    c.setFont(_FONT_NAME_BOLD, value_font_size)
                else:
                    c.setFont(_FONT_NAME, value_font_size)

                # Vertikalno centriranje: baseline na sredini boxa
                # Font size u pt, 1pt = 0.35mm približno
                text_y = y + height/2 - value_font_size * 0.12 * mm

                if align == 'center':
                    c.drawCentredString(x + width/2, text_y, value)
                elif align == 'right':
                    c.drawRightString(x + width - 3*mm, text_y, value)
                else:
                    c.drawString(x + 3*mm, text_y, value)

        def draw_field_multiline(x, y, width, height, label, lines, label_font_size=6):
            """
            Crta polje sa labelom IZNAD i više linija teksta.
            Tekst je vertikalno centriran unutar boxa.
            """
            # Labela IZNAD boxa (1.5mm iznad)
            c.setFont(_FONT_NAME_BOLD, label_font_size)
            c.setFillColor(colors.black)
            c.drawString(x, y + height + 1.5*mm, label)

            # Box
            c.setLineWidth(0.3)
            c.rect(x, y, width, height)

            # Izračunaj ukupnu visinu teksta
            total_text_height = 0
            line_heights = []
            for text, bold, size in lines:
                line_heights.append(size * 0.35 * mm)
                total_text_height += size * 0.35 * mm + 1.5*mm

            # Vertikalno centriranje - počni od sredine
            start_y = y + height/2 + total_text_height/2 - line_heights[0]/2

            line_y = start_y
            for i, (text, bold, size) in enumerate(lines):
                if bold:
                    c.setFont(_FONT_NAME_BOLD, size)
                else:
                    c.setFont(_FONT_NAME, size)
                c.drawString(x + 3*mm, line_y, _safe_text(text) if text else "")
                line_y -= (size * 0.35 + 1.5) * mm

        # ============================================================
        # LEVA STRANA - PLATILAC
        # ============================================================
        left_x = margin + 3*mm
        left_w = mid_x - margin - 6*mm
        label_space = 5 * mm  # Prostor za labelu iznad boxa

        # Platilac polje (15mm visine) - spušteno
        platilac_h = 15 * mm
        platilac_y = header_y - label_space - platilac_h - 2*mm
        platilac_lines = [
            (tenant.name or "", True, 9),
            (getattr(tenant, 'adresa_sedista', '') or "", False, 8),
        ]
        draw_field_multiline(left_x, platilac_y, left_w, platilac_h, "PLATILAC", platilac_lines)

        # Svrha placanja polje (10mm visine)
        svrha_h = 10 * mm
        svrha_y = platilac_y - label_space - svrha_h
        svrha_text = f"Pretplata {payment.invoice_number}"
        svrha_lines = [(svrha_text, False, 9)]
        draw_field_multiline(left_x, svrha_y, left_w, svrha_h, "SVRHA PLACANJA", svrha_lines)

        # Primalac polje (15mm visine)
        primalac_h = 15 * mm
        primalac_y = svrha_y - label_space - primalac_h
        primalac_lines = [
            (s.company_name or "SERVISHUB DOO", True, 9),
            (getattr(s, 'company_address', '') or "", False, 8),
        ]
        draw_field_multiline(left_x, primalac_y, left_w, primalac_h, "PRIMALAC", primalac_lines)

        # ============================================================
        # DESNA STRANA - PODACI O PLAĆANJU
        # ============================================================
        right_x = mid_x + 3*mm
        right_w = W - margin - mid_x - 6*mm

        # Red 1: Šifra plaćanja | Valuta | Iznos - spušteno
        row1_h = 9 * mm
        row1_y = header_y - label_space - row1_h - 2*mm

        # Šifra plaćanja - CENTAR
        sifra_w = 22 * mm
        draw_field_with_label(right_x, row1_y, sifra_w, row1_h, "SIFRA PLACANJA",
                              s.ips_purpose_code or "221", 11, True, 'center')

        # Valuta - CENTAR
        valuta_x = right_x + sifra_w + 2*mm
        valuta_w = 18 * mm
        draw_field_with_label(valuta_x, row1_y, valuta_w, row1_h, "VALUTA",
                              payment.currency or "RSD", 11, True, 'center')

        # Iznos - DESNO
        iznos_x = valuta_x + valuta_w + 2*mm
        iznos_w = right_w - sifra_w - valuta_w - 4*mm
        iznos_str = f"={payment.total_amount:,.2f}"
        draw_field_with_label(iznos_x, row1_y, iznos_w, row1_h, "IZNOS",
                              iznos_str, 11, True, 'right')

        # Red 2: Račun primaoca - LEVO
        row2_h = 9 * mm
        row2_y = row1_y - label_space - row2_h
        draw_field_with_label(right_x, row2_y, right_w, row2_h, "RACUN PRIMAOCA",
                              s.company_bank_account or "", 11, True, 'left')

        # Red 3: Model | Poziv na broj
        row3_h = 9 * mm
        row3_y = row2_y - label_space - row3_h

        # Model - CENTAR
        model_w = 18 * mm
        draw_field_with_label(right_x, row3_y, model_w, row3_h, "MODEL",
                              payment.payment_reference_model or "97", 11, True, 'center')

        # Poziv na broj - LEVO
        poziv_x = right_x + model_w + 2*mm
        poziv_w = right_w - model_w - 2*mm
        draw_field_with_label(poziv_x, row3_y, poziv_w, row3_h, "POZIV NA BROJ (ODOBRENJE)",
                              payment.payment_reference or "", 11, True, 'left')

        # ============================================================
        # QR KOD - donji desni ugao
        # ============================================================
        if payment.ips_qr_string:
            try:
                qr_size = 22 * mm
                qr_x = W - margin - qr_size - 3*mm
                qr_y = margin + 3*mm

                qr_bytes = self.ips_service.generate_qr_image(payment.ips_qr_string, size=150)
                qr_img = ImageReader(BytesIO(qr_bytes))
                c.drawImage(qr_img, qr_x, qr_y, width=qr_size, height=qr_size)

                # Label ispod QR koda
                c.setFont(_FONT_NAME, 5)
                c.drawCentredString(qr_x + qr_size/2, qr_y - 2*mm, "NBS IPS QR")
            except Exception:
                pass

        # ============================================================
        # DONJI DEO - Potpis i datum (leva strana)
        # ============================================================
        footer_y = margin + 5*mm

        c.setFont(_FONT_NAME, 6)
        c.drawString(left_x, footer_y + 8*mm, "Mesto i datum")
        c.setLineWidth(0.3)
        c.line(left_x, footer_y + 4*mm, left_x + 40*mm, footer_y + 4*mm)

        c.drawString(left_x + 45*mm, footer_y + 8*mm, "Potpis platioca")
        c.line(left_x + 45*mm, footer_y + 4*mm, mid_x - 5*mm, footer_y + 4*mm)

        # M.P. (desna strana, levo od QR koda)
        c.drawString(right_x, footer_y + 8*mm, "M.P.")

        c.save()
        return buffer.getvalue()

    def generate_invoice_pdf(self, payment, tenant, settings=None) -> bytes:
        """
        Generiše profesionalnu fakturu u Enterprise SaaS stilu.

        Layout sa fiksnim Y pozicijama za konzistentnost:
        A) Header - Izdavalac levo, Faktura kartica desno
        B) Kupac - Podaci o kupcu + ServisHub nalog info
        C) Stavke - Tabela sa periodom, količinom, cenama
        D) Zbir - Desno poravnato
        E) Plaćanje - Podaci za uplatu + IPS QR kod
        F) Footer - Uslovi, podrška

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

        # Konstante za layout
        margin = 20 * mm
        content_width = width - 2 * margin
        mid_x = width / 2

        # Boje
        light_gray = colors.Color(0.95, 0.95, 0.95)
        dark_gray = colors.Color(0.4, 0.4, 0.4)
        black = colors.black

        # ================================================================
        # A) HEADER - Izdavalac levo, Faktura kartica desno
        # ================================================================
        # Fiksne Y pozicije
        header_top = height - 20 * mm

        # -- Levo: Izdavalac --
        c.setFillColor(black)
        c.setFont(_FONT_NAME_BOLD, 14)
        c.drawString(margin, header_top, "ServisHub")

        c.setFont(_FONT_NAME, 9)
        y = header_top - 16
        c.drawString(margin, y, _safe_text(s.company_name or "ServisHub DOO"))
        y -= 11
        if getattr(s, 'company_address', ''):
            c.drawString(margin, y, _safe_text(s.company_address))
            y -= 11
        if getattr(s, 'company_city', ''):
            city_line = f"{getattr(s, 'company_postal_code', '')} {s.company_city}".strip()
            c.drawString(margin, y, _safe_text(city_line))
            y -= 11

        c.setFont(_FONT_NAME, 8)
        if getattr(s, 'company_pib', ''):
            c.drawString(margin, y, f"PIB: {s.company_pib}   MB: {getattr(s, 'company_mb', '')}")
            y -= 11

        c.setFillColor(dark_gray)
        c.drawString(margin, y, "Nije u sistemu PDV-a")
        y -= 13

        c.setFillColor(black)
        contact_parts = []
        if getattr(s, 'company_phone', ''):
            contact_parts.append(s.company_phone)
        if getattr(s, 'company_email', ''):
            contact_parts.append(s.company_email)
        if contact_parts:
            c.drawString(margin, y, " | ".join(contact_parts))

        # -- Desno: Faktura info (bez pozadine, samo okvir) --
        card_width = 70 * mm
        card_x = width - margin - card_width
        card_top = header_top + 3

        # FAKTURA naslov - veliki
        c.setFillColor(black)
        c.setFont(_FONT_NAME_BOLD, 22)
        c.drawRightString(width - margin, card_top, "FAKTURA")

        # Detalji fakture - desno poravnato
        c.setFont(_FONT_NAME, 9)
        detail_y = card_top - 20
        c.drawRightString(width - margin, detail_y, f"Broj: {payment.invoice_number}")
        detail_y -= 12
        c.drawRightString(width - margin, detail_y, f"Datum: {payment.created_at.strftime('%d.%m.%Y')}")
        detail_y -= 12

        period_end = getattr(payment, 'period_end', None)
        if period_end and hasattr(period_end, 'strftime'):
            c.drawRightString(width - margin, detail_y, f"Datum prometa: {period_end.strftime('%d.%m.%Y')}")
        else:
            c.drawRightString(width - margin, detail_y, f"Datum prometa: {payment.created_at.strftime('%d.%m.%Y')}")
        detail_y -= 12
        c.drawRightString(width - margin, detail_y, f"Valuta: {payment.currency or 'RSD'}")

        # ================================================================
        # SEPARATOR LINIJA
        # ================================================================
        sep1_y = height - 75 * mm
        c.setStrokeColor(colors.Color(0.85, 0.85, 0.85))
        c.setLineWidth(0.5)
        c.line(margin, sep1_y, width - margin, sep1_y)

        # ================================================================
        # B) KUPAC - Dve kolone, centrirane
        # ================================================================
        buyer_top = sep1_y - 8 * mm

        # -- Levo: Kupac --
        c.setFillColor(dark_gray)
        c.setFont(_FONT_NAME_BOLD, 8)
        c.drawString(margin, buyer_top, "KUPAC")

        c.setFillColor(black)
        c.setFont(_FONT_NAME_BOLD, 10)
        c.drawString(margin, buyer_top - 14, _safe_text(tenant.name or ""))

        c.setFont(_FONT_NAME, 9)
        buyer_y = buyer_top - 28
        if hasattr(tenant, 'adresa_sedista') and tenant.adresa_sedista:
            c.drawString(margin, buyer_y, _safe_text(tenant.adresa_sedista))
            buyer_y -= 11
        if hasattr(tenant, 'pib') and tenant.pib:
            pib_mb = f"PIB: {tenant.pib}"
            if hasattr(tenant, 'mb') and tenant.mb:
                pib_mb += f"   MB: {tenant.mb}"
            c.drawString(margin, buyer_y, pib_mb)
            buyer_y -= 11
        if hasattr(tenant, 'email') and tenant.email:
            c.drawString(margin, buyer_y, tenant.email)

        # -- Desno: ServisHub nalog --
        right_col_x = mid_x + 15 * mm
        c.setFillColor(dark_gray)
        c.setFont(_FONT_NAME_BOLD, 8)
        c.drawString(right_col_x, buyer_top, "NALOG")

        c.setFillColor(black)
        c.setFont(_FONT_NAME, 9)
        account_y = buyer_top - 14

        customer_id = f"SH-{tenant.id}" if hasattr(tenant, 'id') else ""
        c.drawString(right_col_x, account_y, f"Customer ID: {customer_id}")
        account_y -= 11

        if hasattr(tenant, 'slug') and tenant.slug:
            c.drawString(right_col_x, account_y, f"Account: {tenant.slug}")
            account_y -= 11

        period_start = getattr(payment, 'period_start', None)
        period_end = getattr(payment, 'period_end', None)
        if period_start and period_end:
            period_str = f"{period_start.strftime('%d.%m.%Y')} - {period_end.strftime('%d.%m.%Y')}"
            c.drawString(right_col_x, account_y, f"Period: {period_str}")

        # ================================================================
        # C) STAVKE - Tabela
        # ================================================================
        table_top = sep1_y - 55 * mm

        # Zaglavlje tabele
        header_height = 7 * mm
        c.setFillColor(light_gray)
        c.rect(margin, table_top, content_width, header_height, fill=1, stroke=0)

        # Definicija kolona
        col_rbr = margin + 3 * mm
        col_opis = margin + 15 * mm
        col_period = margin + 90 * mm
        col_kol = margin + 120 * mm
        col_cena = margin + 138 * mm

        # Zaglavlje tekst
        c.setFillColor(dark_gray)
        c.setFont(_FONT_NAME_BOLD, 8)
        c.drawString(col_rbr, table_top + 2 * mm, "R.br.")
        c.drawString(col_opis, table_top + 2 * mm, "Naziv usluge / paketa")
        c.drawString(col_period, table_top + 2 * mm, "Period")
        c.drawCentredString(col_kol + 5 * mm, table_top + 2 * mm, "Kol.")
        c.drawRightString(col_cena + 15 * mm, table_top + 2 * mm, "Cena")
        c.drawRightString(width - margin - 3 * mm, table_top + 2 * mm, "Ukupno")

        # Linija ispod zaglavlja
        c.setStrokeColor(colors.Color(0.75, 0.75, 0.75))
        c.setLineWidth(0.5)
        c.line(margin, table_top, width - margin, table_top)

        # Stavke
        c.setFillColor(black)
        c.setFont(_FONT_NAME, 9)
        items = getattr(payment, 'items_json', None) or []
        row_y = table_top - 10 * mm

        period_str_short = ""
        if period_start and period_end:
            period_str_short = f"{period_start.strftime('%d.%m')}-{period_end.strftime('%d.%m.%y')}"

        if items:
            for i, item in enumerate(items, 1):
                desc = item.get('description', '') if isinstance(item, dict) else str(item)
                qty = item.get('quantity', 1) if isinstance(item, dict) else 1
                unit_price = item.get('unit_price', 0) if isinstance(item, dict) else 0
                total = item.get('total', 0) if isinstance(item, dict) else 0
                item_period = item.get('period', period_str_short) if isinstance(item, dict) else period_str_short

                c.drawString(col_rbr, row_y, str(i))
                desc_truncated = desc[:40] + "..." if len(desc) > 40 else desc
                c.drawString(col_opis, row_y, _safe_text(desc_truncated))
                c.drawString(col_period, row_y, item_period or "-")
                c.drawCentredString(col_kol + 5 * mm, row_y, str(qty))
                c.drawRightString(col_cena + 15 * mm, row_y, f"{float(unit_price):,.2f}")
                c.drawRightString(width - margin - 3 * mm, row_y, f"{float(total):,.2f}")

                row_y -= 9 * mm
        else:
            c.drawString(col_rbr, row_y, "1")
            desc = f"ServisHub pretplata - {payment.invoice_number}"
            c.drawString(col_opis, row_y, _safe_text(desc))
            c.drawString(col_period, row_y, period_str_short or "-")
            c.drawCentredString(col_kol + 5 * mm, row_y, "1")
            c.drawRightString(col_cena + 15 * mm, row_y, f"{float(payment.total_amount):,.2f}")
            c.drawRightString(width - margin - 3 * mm, row_y, f"{float(payment.total_amount):,.2f}")
            row_y -= 9 * mm

        # Linija ispod stavki
        c.setStrokeColor(colors.Color(0.85, 0.85, 0.85))
        c.line(margin, row_y + 5 * mm, width - margin, row_y + 5 * mm)

        # ================================================================
        # D) ZBIR - Desno poravnato
        # ================================================================
        totals_label_x = width - margin - 55 * mm
        totals_value_x = width - margin
        totals_y = row_y - 8 * mm

        c.setFillColor(black)
        c.setFont(_FONT_NAME, 9)
        subtotal = float(getattr(payment, 'subtotal', payment.total_amount) or payment.total_amount)
        c.drawRightString(totals_label_x, totals_y, "Medjuzbir:")
        c.drawRightString(totals_value_x, totals_y, f"{subtotal:,.2f} RSD")
        totals_y -= 11

        discount = float(getattr(payment, 'discount_amount', 0) or 0)
        if discount > 0:
            discount_reason = getattr(payment, 'discount_reason', '') or ''
            label = f"Popust ({discount_reason}):" if discount_reason else "Popust:"
            c.drawRightString(totals_label_x, totals_y, label)
            c.drawRightString(totals_value_x, totals_y, f"-{discount:,.2f} RSD")
            totals_y -= 11

        osnovica = subtotal - discount
        c.drawRightString(totals_label_x, totals_y, "Osnovica:")
        c.drawRightString(totals_value_x, totals_y, f"{osnovica:,.2f} RSD")
        totals_y -= 11

        c.setFillColor(dark_gray)
        c.setFont(_FONT_NAME, 8)
        c.drawRightString(totals_label_x, totals_y, "PDV:")
        c.drawRightString(totals_value_x, totals_y, "nije u sistemu PDV-a")
        totals_y -= 14

        # Linija iznad ZA UPLATU
        c.setStrokeColor(colors.Color(0.7, 0.7, 0.7))
        c.setLineWidth(0.5)
        c.line(totals_label_x - 10 * mm, totals_y + 10, totals_value_x, totals_y + 10)

        # ZA UPLATU - bold
        c.setFillColor(black)
        c.setFont(_FONT_NAME_BOLD, 11)
        c.drawRightString(totals_label_x, totals_y - 2, "ZA UPLATU:")
        c.drawRightString(totals_value_x, totals_y - 2, f"{float(payment.total_amount):,.2f} RSD")

        # Zapamti gde se završava zbir sekcija
        totals_end_y = totals_y - 15

        # ================================================================
        # E) PLAĆANJE + QR - ispod zbira
        # ================================================================
        payment_section_y = min(totals_end_y - 10 * mm, 100 * mm)

        # Separator
        c.setStrokeColor(colors.Color(0.85, 0.85, 0.85))
        c.setLineWidth(0.5)
        c.line(margin, payment_section_y + 12 * mm, width - margin, payment_section_y + 12 * mm)

        # Label
        c.setFillColor(dark_gray)
        c.setFont(_FONT_NAME_BOLD, 8)
        c.drawString(margin, payment_section_y + 5 * mm, "PODACI ZA PLACANJE")

        # Podaci - levo
        c.setFillColor(black)
        c.setFont(_FONT_NAME, 9)
        pay_y = payment_section_y - 5 * mm

        due_date = getattr(payment, 'due_date', None)
        if due_date and hasattr(due_date, 'strftime'):
            c.drawString(margin, pay_y, f"Rok placanja: {due_date.strftime('%d.%m.%Y')}")
        pay_y -= 11

        c.drawString(margin, pay_y, "Nacin placanja: virman")
        pay_y -= 11

        bank_account = getattr(s, 'company_bank_account', '') or ''
        bank_name = getattr(s, 'company_bank_name', '') or ''
        c.drawString(margin, pay_y, f"Racun: {bank_account}")
        pay_y -= 11
        if bank_name:
            c.drawString(margin, pay_y, f"Banka: {_safe_text(bank_name)}")
            pay_y -= 11

        c.setFont(_FONT_NAME_BOLD, 9)
        c.drawString(margin, pay_y, f"Poziv na broj: {payment.payment_reference or payment.invoice_number}")

        # QR Kod - desno od podataka za plaćanje
        if payment.ips_qr_string:
            try:
                qr_size = 30 * mm
                qr_x = width - margin - qr_size
                qr_y = payment_section_y - qr_size + 5 * mm

                qr_bytes = self.ips_service.generate_qr_image(payment.ips_qr_string, size=180)
                qr_img = ImageReader(BytesIO(qr_bytes))
                c.drawImage(qr_img, qr_x, qr_y, width=qr_size, height=qr_size)

                c.setFillColor(dark_gray)
                c.setFont(_FONT_NAME, 7)
                c.drawCentredString(qr_x + qr_size / 2, qr_y - 4 * mm, "Skenirajte za uplatu")
            except Exception:
                pass

        # ================================================================
        # F) FOOTER - fiksna pozicija na dnu
        # ================================================================
        footer_y = 28 * mm

        c.setStrokeColor(colors.Color(0.85, 0.85, 0.85))
        c.setLineWidth(0.5)
        c.line(margin, footer_y + 10 * mm, width - margin, footer_y + 10 * mm)

        c.setFillColor(dark_gray)
        c.setFont(_FONT_NAME, 7)

        footer_text = [
            "Usluga: pristup i koriscenje ServisHub platforme za navedeni period.",
            "Pretplata se automatski obnavlja mesecno, osim ako se otkaze pre isteka perioda.",
        ]

        text_y = footer_y
        for line in footer_text:
            c.drawString(margin, text_y, _safe_text(line))
            text_y -= 9

        c.drawRightString(width - margin, footer_y, "Za podrsku: support@shub.rs")

        c.setFont(_FONT_NAME, 6)
        c.drawString(margin, 12, f"Generisano: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        c.drawRightString(width - margin, 12, f"Faktura {payment.invoice_number}")

        c.save()
        return buffer.getvalue()
