"""
Email servis - slanje verifikacionih emailova za registraciju.

Koristi Brevo (ex Sendinblue) API za slanje emailova.
Dokumentacija: https://developers.brevo.com/reference/sendtransacemail

Funkcionalnosti:
- Slanje verifikacionog emaila sa linkom
- Rate limiting (max 5 pokusaja po email adresi)
- Dev mode (loguje email umesto slanja)
"""

import os
import requests
from datetime import datetime, timezone
from typing import Tuple, Optional
from urllib.parse import urljoin

from ..extensions import db
from ..models.email_verification import PendingEmailVerification


class EmailError(Exception):
    """Bazna klasa za Email greske."""
    def __init__(self, message: str, code: int = 400):
        self.message = message
        self.code = code
        super().__init__(self.message)


class EmailService:
    """
    Servis za slanje email poruka i verifikaciju.

    Koristi Brevo API sa environment varijablama:
    - BREVO_API_KEY: API kljuc za Brevo
    - BREVO_FROM_EMAIL: Email adresa posaljioca
    - BREVO_FROM_NAME: Ime posaljioca (default: ServisHub)
    - FRONTEND_URL: URL fronted aplikacije za linkove
    """

    # Brevo API endpoint
    API_URL = "https://api.brevo.com/v3/smtp/email"

    # Konfiguracija
    MAX_ATTEMPTS = 5
    RESEND_COOLDOWN_SECONDS = 60

    def __init__(self):
        """Inicijalizacija Email servisa."""
        self.api_key = os.environ.get('BREVO_API_KEY')
        self.from_email = os.environ.get('BREVO_FROM_EMAIL', 'noreply@shub.rs')
        self.from_name = os.environ.get('BREVO_FROM_NAME', 'ServisHub')
        self.frontend_url = os.environ.get('FRONTEND_URL', 'https://app.shub.rs')

    def _build_verification_url(self, token: str) -> str:
        """
        Gradi URL za verifikaciju emaila.

        Args:
            token: Verifikacioni token

        Returns:
            Puni URL za verifikaciju
        """
        # URL vodi na frontend koji ce pozvati API
        return f"{self.frontend_url}/verify-email?token={token}"

    def _build_verification_email_html(self, verification_url: str) -> str:
        """
        Gradi HTML sadrzaj emaila za verifikaciju.

        Args:
            verification_url: URL za verifikaciju

        Returns:
            HTML string
        """
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Verifikacija Email Adrese</title>
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
                <h1 style="color: white; margin: 0; font-size: 24px;">ServisHub</h1>
                <p style="color: rgba(255,255,255,0.9); margin: 10px 0 0 0;">Verifikacija Email Adrese</p>
            </div>

            <div style="background: #f9fafb; padding: 30px; border: 1px solid #e5e7eb; border-top: none;">
                <h2 style="margin-top: 0; color: #1f2937;">Zdravo!</h2>

                <p>Dobili ste ovaj email jer ste pokrenuli registraciju na ServisHub platformi.</p>

                <p>Da biste nastavili sa registracijom, molimo vas da potvrdite vasu email adresu klikom na dugme ispod:</p>

                <div style="text-align: center; margin: 30px 0;">
                    <a href="{verification_url}"
                       style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                              color: white;
                              padding: 14px 30px;
                              text-decoration: none;
                              border-radius: 8px;
                              font-weight: 600;
                              display: inline-block;">
                        Potvrdi Email Adresu
                    </a>
                </div>

                <p style="color: #6b7280; font-size: 14px;">
                    Ako dugme ne radi, kopirajte ovaj link u vas browser:<br>
                    <a href="{verification_url}" style="color: #667eea; word-break: break-all;">{verification_url}</a>
                </p>

                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 30px 0;">

                <p style="color: #6b7280; font-size: 13px; margin-bottom: 0;">
                    <strong>Vazno:</strong> Ovaj link vazi 24 sata. Ako niste vi pokrenuli registraciju,
                    mozete slobodno ignorisati ovaj email.
                </p>
            </div>

            <div style="text-align: center; padding: 20px; color: #9ca3af; font-size: 12px;">
                <p style="margin: 0;">&copy; {datetime.now().year} ServisHub. Sva prava zadrzana.</p>
                <p style="margin: 5px 0 0 0;">Ovaj email je automatski generisan, molimo ne odgovarajte na njega.</p>
            </div>
        </body>
        </html>
        """

    def _build_verification_email_text(self, verification_url: str) -> str:
        """
        Gradi plain text sadrzaj emaila za verifikaciju.

        Args:
            verification_url: URL za verifikaciju

        Returns:
            Plain text string
        """
        return f"""
ServisHub - Verifikacija Email Adrese

Zdravo!

Dobili ste ovaj email jer ste pokrenuli registraciju na ServisHub platformi.

Da biste nastavili sa registracijom, molimo vas da potvrdite vasu email adresu
otvaranjem sledeceg linka u vasem browseru:

{verification_url}

Vazno: Ovaj link vazi 24 sata. Ako niste vi pokrenuli registraciju,
mozete slobodno ignorisati ovaj email.

---
(c) {datetime.now().year} ServisHub. Sva prava zadrzana.
Ovaj email je automatski generisan, molimo ne odgovarajte na njega.
        """

    def send_verification_email(self, email: str) -> Tuple[bool, str, Optional[str]]:
        """
        Salje verifikacioni email na zadatu adresu.

        Proverava rate limiting i kreira/azurira PendingEmailVerification zapis.

        Args:
            email: Email adresa

        Returns:
            Tuple (success: bool, message: str, token_for_dev: Optional[str])

        Raises:
            EmailError: Ako slanje nije uspelo
        """
        email = email.lower().strip()

        # Proveri rate limiting
        can_send, seconds_remaining = PendingEmailVerification.can_resend(email)
        if not can_send:
            if seconds_remaining == -1:
                raise EmailError(
                    "Previse pokusaja za ovu email adresu. Pokusajte ponovo za nekoliko sati.",
                    429
                )
            raise EmailError(
                f"Molimo sacekajte {seconds_remaining} sekundi pre nego sto zatrazite novi email.",
                429
            )

        # Kreiraj verifikacioni zapis
        verification, plain_token, is_new = PendingEmailVerification.create_or_update(email)

        # Gradi URL
        verification_url = self._build_verification_url(plain_token)

        # U development modu, samo loguj (ne salji stvarno)
        if not self.api_key or os.environ.get('FLASK_ENV') == 'development':
            print(f"[DEV] Email to {email}")
            print(f"[DEV] Verification URL: {verification_url}")
            print(f"[DEV] Token: {plain_token}")
            return True, "Verifikacioni email uspesno poslat (DEV mode)", plain_token

        # Pripremi email sadrzaj
        html_content = self._build_verification_email_html(verification_url)
        text_content = self._build_verification_email_text(verification_url)

        # Posalji email preko Brevo API
        try:
            payload = {
                "sender": {
                    "name": self.from_name,
                    "email": self.from_email
                },
                "to": [{"email": email}],
                "subject": "ServisHub - Potvrdite vasu email adresu",
                "htmlContent": html_content,
                "textContent": text_content
            }

            # SECURITY: Ne loguj verification URL - sadrzi token!
            print(f"[EMAIL] Sending verification email to: {email}")

            response = requests.post(
                self.API_URL,
                json=payload,
                headers={
                    "api-key": self.api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                },
                timeout=10
            )

            print(f"[EMAIL] Brevo response status: {response.status_code}")
            print(f"[EMAIL] Brevo response body: {response.text}")

            # Brevo vraca 201 Created za uspesno slanje
            if response.status_code in [200, 201, 202]:
                print(f"[EMAIL] Successfully sent to {email}")
                return True, "Verifikacioni email uspesno poslat", None
            else:
                error_msg = "Nepoznata greska"
                try:
                    error_data = response.json()
                    print(f"[EMAIL] Error data: {error_data}")
                    if 'message' in error_data:
                        error_msg = error_data['message']
                except:
                    pass
                print(f"[EMAIL] Failed to send: {error_msg}")
                raise EmailError(f"Slanje emaila nije uspelo: {error_msg}", 500)

        except requests.RequestException as e:
            print(f"[EMAIL] Request exception: {str(e)}")
            raise EmailError(f"Greska pri slanju emaila: {str(e)}", 500)

    def verify_email_token(self, token: str) -> Tuple[bool, str]:
        """
        Verifikuje token iz emaila.

        Args:
            token: Token iz URL-a

        Returns:
            Tuple (success: bool, email_or_error: str)
        """
        return PendingEmailVerification.verify_token(token)

    def is_email_verified(self, email: str) -> bool:
        """
        Proverava da li je email verifikovan.

        Args:
            email: Email adresa

        Returns:
            bool: True ako je verifikovan
        """
        return PendingEmailVerification.is_verified(email)

    def delete_verification(self, email: str):
        """
        Brise verifikacioni zapis (posle uspesne registracije).

        Args:
            email: Email adresa
        """
        PendingEmailVerification.delete_for_email(email)

    def can_resend(self, email: str) -> Tuple[bool, int]:
        """
        Proverava da li moze da se posalje novi email.

        Args:
            email: Email adresa

        Returns:
            Tuple (can_resend: bool, seconds_remaining: int)
        """
        return PendingEmailVerification.can_resend(email)


    # =========================================================================
    # BILLING EMAILS
    # =========================================================================

    def send_invoice_email(self, email: str, tenant_name: str, invoice_number: str,
                           amount: float, due_date: str, period: str) -> bool:
        """
        Salje email sa novom fakturom.

        Args:
            email: Email adresa tenanta
            tenant_name: Naziv servisa
            invoice_number: Broj fakture
            amount: Iznos u RSD
            due_date: Rok placanja (formatirano)
            period: Period fakture (npr. "Januar 2026")

        Returns:
            bool: True ako je uspesno poslato
        """
        subject = f"ServisHub - Nova faktura {invoice_number}"
        html_content = self._build_invoice_email_html(
            tenant_name, invoice_number, amount, due_date, period
        )
        text_content = self._build_invoice_email_text(
            tenant_name, invoice_number, amount, due_date, period
        )
        return self._send_email(email, subject, html_content, text_content)

    def send_payment_reminder_email(self, email: str, tenant_name: str,
                                    invoice_number: str, amount: float,
                                    days_overdue: int) -> bool:
        """
        Salje podsetnik za neplacenu fakturu.

        Args:
            email: Email adresa
            tenant_name: Naziv servisa
            invoice_number: Broj fakture
            amount: Iznos
            days_overdue: Broj dana kasnjenja

        Returns:
            bool: True ako je uspesno
        """
        subject = f"ServisHub - Podsetnik za uplatu {invoice_number}"
        html_content = self._build_reminder_email_html(
            tenant_name, invoice_number, amount, days_overdue
        )
        text_content = self._build_reminder_email_text(
            tenant_name, invoice_number, amount, days_overdue
        )
        return self._send_email(email, subject, html_content, text_content)

    def send_suspension_warning_email(self, email: str, tenant_name: str,
                                      amount: float, days_until_suspension: int) -> bool:
        """
        Salje upozorenje o skoroj suspenziji.

        Args:
            email: Email adresa
            tenant_name: Naziv servisa
            amount: Ukupno dugovanje
            days_until_suspension: Dana do suspenzije

        Returns:
            bool: True ako je uspesno
        """
        subject = "ServisHub - VAZNO: Suspenzija naloga za nekoliko dana"
        html_content = self._build_suspension_warning_html(
            tenant_name, amount, days_until_suspension
        )
        text_content = self._build_suspension_warning_text(
            tenant_name, amount, days_until_suspension
        )
        return self._send_email(email, subject, html_content, text_content)

    def send_suspension_notice_email(self, email: str, tenant_name: str,
                                     amount: float, reason: str) -> bool:
        """
        Salje obavestenje o suspenziji naloga.

        Args:
            email: Email adresa
            tenant_name: Naziv servisa
            amount: Ukupno dugovanje
            reason: Razlog suspenzije

        Returns:
            bool: True ako je uspesno
        """
        subject = "ServisHub - Nalog je suspendovan"
        html_content = self._build_suspension_notice_html(tenant_name, amount, reason)
        text_content = self._build_suspension_notice_text(tenant_name, amount, reason)
        return self._send_email(email, subject, html_content, text_content)

    def send_payment_confirmation_email(self, email: str, tenant_name: str,
                                        invoice_number: str, amount: float) -> bool:
        """
        Salje potvrdu o primljenoj uplati.

        Args:
            email: Email adresa
            tenant_name: Naziv servisa
            invoice_number: Broj fakture
            amount: Placeni iznos

        Returns:
            bool: True ako je uspesno
        """
        subject = f"ServisHub - Potvrda uplate {invoice_number}"
        html_content = self._build_payment_confirmation_html(
            tenant_name, invoice_number, amount
        )
        text_content = self._build_payment_confirmation_text(
            tenant_name, invoice_number, amount
        )
        return self._send_email(email, subject, html_content, text_content)

    def _send_email(self, to_email: str, subject: str,
                    html_content: str, text_content: str) -> bool:
        """
        Interni helper za slanje emaila.

        Returns:
            bool: True ako uspesno
        """
        # U development modu, samo loguj
        if not self.api_key or os.environ.get('FLASK_ENV') == 'development':
            print(f"[DEV EMAIL] To: {to_email}")
            print(f"[DEV EMAIL] Subject: {subject}")
            return True

        try:
            payload = {
                "sender": {
                    "name": self.from_name,
                    "email": self.from_email
                },
                "to": [{"email": to_email}],
                "subject": subject,
                "htmlContent": html_content,
                "textContent": text_content
            }

            response = requests.post(
                self.API_URL,
                json=payload,
                headers={
                    "api-key": self.api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                },
                timeout=10
            )

            return response.status_code in [200, 201, 202]

        except Exception as e:
            print(f"[EMAIL ERROR] {str(e)}")
            return False

    def _build_invoice_email_html(self, tenant_name: str, invoice_number: str,
                                  amount: float, due_date: str, period: str) -> str:
        """Gradi HTML za fakturu email."""
        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
                <h1 style="color: white; margin: 0;">ServisHub</h1>
                <p style="color: rgba(255,255,255,0.9); margin: 10px 0 0 0;">Nova faktura</p>
            </div>
            <div style="background: #f9fafb; padding: 30px; border: 1px solid #e5e7eb;">
                <h2 style="margin-top: 0;">Postovani {tenant_name},</h2>
                <p>Generisana je nova faktura za vasu pretplatu na ServisHub platformi.</p>

                <div style="background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 20px; margin: 20px 0;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr><td style="padding: 8px 0; color: #6b7280;">Broj fakture:</td><td style="padding: 8px 0; text-align: right; font-weight: 600;">{invoice_number}</td></tr>
                        <tr><td style="padding: 8px 0; color: #6b7280;">Period:</td><td style="padding: 8px 0; text-align: right;">{period}</td></tr>
                        <tr><td style="padding: 8px 0; color: #6b7280;">Rok placanja:</td><td style="padding: 8px 0; text-align: right;">{due_date}</td></tr>
                        <tr style="border-top: 2px solid #e5e7eb;"><td style="padding: 12px 0; font-weight: 600;">UKUPNO:</td><td style="padding: 12px 0; text-align: right; font-size: 20px; font-weight: 700; color: #667eea;">{amount:,.0f} RSD</td></tr>
                    </table>
                </div>

                <p><strong>Uplatni racun:</strong> 265-1234567-89</p>
                <p><strong>Poziv na broj:</strong> {invoice_number}</p>

                <div style="text-align: center; margin: 30px 0;">
                    <a href="{self.frontend_url}/subscription" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 14px 30px; text-decoration: none; border-radius: 8px; font-weight: 600;">Pogledaj detalje</a>
                </div>
            </div>
            <div style="text-align: center; padding: 20px; color: #9ca3af; font-size: 12px;">
                <p>&copy; {datetime.now().year} ServisHub</p>
            </div>
        </body>
        </html>
        """

    def _build_invoice_email_text(self, tenant_name: str, invoice_number: str,
                                  amount: float, due_date: str, period: str) -> str:
        """Gradi text za fakturu email."""
        return f"""
ServisHub - Nova faktura

Postovani {tenant_name},

Generisana je nova faktura za vasu pretplatu.

Broj fakture: {invoice_number}
Period: {period}
Rok placanja: {due_date}
UKUPNO: {amount:,.0f} RSD

Uplatni racun: 265-1234567-89
Poziv na broj: {invoice_number}

---
(c) {datetime.now().year} ServisHub
        """

    def _build_reminder_email_html(self, tenant_name: str, invoice_number: str,
                                   amount: float, days_overdue: int) -> str:
        """Gradi HTML za podsetnik."""
        urgency_color = '#dc2626' if days_overdue > 7 else '#f59e0b'
        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: {urgency_color}; padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
                <h1 style="color: white; margin: 0;">ServisHub</h1>
                <p style="color: rgba(255,255,255,0.9); margin: 10px 0 0 0;">Podsetnik za uplatu</p>
            </div>
            <div style="background: #f9fafb; padding: 30px; border: 1px solid #e5e7eb;">
                <h2 style="margin-top: 0;">Postovani {tenant_name},</h2>
                <p>Zelimo da vas podsetimo da faktura <strong>{invoice_number}</strong> kasni <strong>{days_overdue} dana</strong>.</p>

                <div style="background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 20px; margin: 20px 0;">
                    <p style="margin: 0; color: #991b1b;"><strong>Dugovanje: {amount:,.0f} RSD</strong></p>
                </div>

                <p>Molimo vas da uplatite sto pre kako biste izbegli suspenziju naloga.</p>

                <p><strong>Uplatni racun:</strong> 265-1234567-89<br><strong>Poziv na broj:</strong> {invoice_number}</p>
            </div>
        </body>
        </html>
        """

    def _build_reminder_email_text(self, tenant_name: str, invoice_number: str,
                                   amount: float, days_overdue: int) -> str:
        """Gradi text za podsetnik."""
        return f"""
ServisHub - Podsetnik za uplatu

Postovani {tenant_name},

Faktura {invoice_number} kasni {days_overdue} dana.
Dugovanje: {amount:,.0f} RSD

Molimo uplatite sto pre.

Uplatni racun: 265-1234567-89
Poziv na broj: {invoice_number}
        """

    def _build_suspension_warning_html(self, tenant_name: str, amount: float,
                                       days_until: int) -> str:
        """Gradi HTML za upozorenje o suspenziji."""
        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: #dc2626; padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
                <h1 style="color: white; margin: 0;">VAZNO OBAVESTENJE</h1>
            </div>
            <div style="background: #fef2f2; padding: 30px; border: 1px solid #fecaca;">
                <h2 style="margin-top: 0; color: #991b1b;">Postovani {tenant_name},</h2>
                <p style="color: #991b1b; font-size: 18px;"><strong>Vas nalog ce biti suspendovan za {days_until} dana!</strong></p>
                <p>Ukupno dugovanje: <strong>{amount:,.0f} RSD</strong></p>
                <p>Molimo vas da hitno izmirte dugovanje kako biste nastavili sa koriscenjem ServisHub platforme.</p>
                <p><strong>Uplatni racun:</strong> 265-1234567-89</p>
            </div>
        </body>
        </html>
        """

    def _build_suspension_warning_text(self, tenant_name: str, amount: float,
                                       days_until: int) -> str:
        return f"""
VAZNO OBAVESTENJE - ServisHub

Postovani {tenant_name},

Vas nalog ce biti suspendovan za {days_until} dana!
Ukupno dugovanje: {amount:,.0f} RSD

Molimo hitno izmirte dugovanje.
Uplatni racun: 265-1234567-89
        """

    def _build_suspension_notice_html(self, tenant_name: str, amount: float,
                                      reason: str) -> str:
        """Gradi HTML za obavestenje o suspenziji."""
        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: #7f1d1d; padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
                <h1 style="color: white; margin: 0;">Nalog Suspendovan</h1>
            </div>
            <div style="background: #fef2f2; padding: 30px; border: 1px solid #fecaca;">
                <h2 style="margin-top: 0; color: #991b1b;">Postovani {tenant_name},</h2>
                <p>Vas nalog na ServisHub platformi je suspendovan.</p>
                <p><strong>Razlog:</strong> {reason}</p>
                <p><strong>Dugovanje:</strong> {amount:,.0f} RSD</p>
                <hr style="border: none; border-top: 1px solid #fecaca;">
                <p>Da biste reaktivirali nalog, molimo uplatite dugovanje ili nas kontaktirajte za dogovor.</p>
                <p><strong>Uplatni racun:</strong> 265-1234567-89</p>
                <p><strong>Kontakt:</strong> podrska@shub.rs</p>
            </div>
        </body>
        </html>
        """

    def _build_suspension_notice_text(self, tenant_name: str, amount: float,
                                      reason: str) -> str:
        return f"""
ServisHub - Nalog Suspendovan

Postovani {tenant_name},

Vas nalog je suspendovan.
Razlog: {reason}
Dugovanje: {amount:,.0f} RSD

Za reaktivaciju uplatite dugovanje ili nas kontaktirajte.
Uplatni racun: 265-1234567-89
Kontakt: podrska@shub.rs
        """

    def _build_payment_confirmation_html(self, tenant_name: str,
                                         invoice_number: str, amount: float) -> str:
        """Gradi HTML za potvrdu uplate."""
        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: #059669; padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
                <h1 style="color: white; margin: 0;">Uplata Primljena</h1>
            </div>
            <div style="background: #ecfdf5; padding: 30px; border: 1px solid #a7f3d0;">
                <h2 style="margin-top: 0; color: #065f46;">Postovani {tenant_name},</h2>
                <p>Vasa uplata je uspesno evidentirana!</p>
                <div style="background: white; border-radius: 8px; padding: 20px; margin: 20px 0;">
                    <p style="margin: 0;"><strong>Faktura:</strong> {invoice_number}</p>
                    <p style="margin: 10px 0 0 0;"><strong>Iznos:</strong> {amount:,.0f} RSD</p>
                </div>
                <p>Hvala vam na poverenju!</p>
            </div>
            <div style="text-align: center; padding: 20px; color: #9ca3af; font-size: 12px;">
                <p>&copy; {datetime.now().year} ServisHub</p>
            </div>
        </body>
        </html>
        """

    def _build_payment_confirmation_text(self, tenant_name: str,
                                         invoice_number: str, amount: float) -> str:
        return f"""
ServisHub - Uplata Primljena

Postovani {tenant_name},

Vasa uplata je uspesno evidentirana!

Faktura: {invoice_number}
Iznos: {amount:,.0f} RSD

Hvala vam na poverenju!

---
(c) {datetime.now().year} ServisHub
        """


# Singleton instanca servisa
email_service = EmailService()


def send_supplier_order_email(order, event_type):
    """
    Salje email notifikaciju vezanu za supplier order.

    Non-blocking - loguje greske ali ne baca exception.
    Idempotent via NotificationLog event_key.

    event_type: new_order, offered, confirmed, shipped, delivered, rejected, cancelled, expired, reminder_pending
    """
    from app.models import Supplier, Tenant
    from app.models.notification import NotificationLog, NotificationStatus

    event_key = f'supplier_order_{event_type}_{order.id}'

    # Idempotency check
    if NotificationLog.already_sent(event_key):
        return

    supplier = Supplier.query.get(order.seller_supplier_id) if order.seller_supplier_id else None
    tenant = Tenant.query.get(order.buyer_tenant_id) if order.buyer_tenant_id else None

    subjects = {
        'new_order': f'Nova narudzbina {order.order_number}',
        'offered': f'Dobavljac potvrdio dostupnost - {order.order_number}',
        'confirmed': f'Narudzbina potvrđena - {order.order_number}',
        'shipped': f'Narudzbina poslata - {order.order_number}',
        'delivered': f'Narudzbina isporucena - {order.order_number}',
        'rejected': f'Narudzbina odbijena - {order.order_number}',
        'cancelled': f'Narudzbina otkazana - {order.order_number}',
        'expired': f'Narudzbina istekla - {order.order_number}',
        'reminder_pending': f'Podsetnik: Imate neobradjenu narudzbinu {order.order_number}',
    }

    subject = subjects.get(event_type, f'Azuriranje narudzbine {order.order_number}')

    # Determine recipient
    recipient_email = None
    if event_type in ('new_order', 'confirmed', 'reminder_pending'):
        # Email supplier-u
        if supplier and supplier.email:
            recipient_email = supplier.email
    elif event_type in ('offered', 'rejected', 'cancelled', 'expired', 'shipped', 'delivered'):
        # Email tenant-u
        if tenant and tenant.email:
            recipient_email = tenant.email

    if not recipient_email:
        return

    try:
        success = email_service._send_email(
            to_email=recipient_email,
            subject=subject,
            html_content=f'<p>{subject}</p><p>Broj narudzbine: {order.order_number}<br>Status: {order.status.value}</p>',
        )

        # Log notification
        from app.extensions import db
        log = NotificationLog(
            event_key=event_key,
            notification_type='EMAIL',
            channel='EMAIL',
            recipient=recipient_email,
            subject=subject,
            status=NotificationStatus.SENT if success else NotificationStatus.FAILED,
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        pass