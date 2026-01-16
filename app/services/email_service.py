"""
Email servis - slanje verifikacionih emailova za registraciju.

Koristi SendGrid API za slanje emailova.
Dokumentacija: https://docs.sendgrid.com/api-reference/mail-send/mail-send

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

    Koristi SendGrid API sa environment varijablama:
    - SENDGRID_API_KEY: API kljuc za SendGrid
    - SENDGRID_FROM_EMAIL: Email adresa posaljioca
    - SENDGRID_FROM_NAME: Ime posaljioca (default: ServisHub)
    - FRONTEND_URL: URL fronted aplikacije za linkove
    """

    # SendGrid API endpoint
    API_URL = "https://api.sendgrid.com/v3/mail/send"

    # Konfiguracija
    MAX_ATTEMPTS = 5
    RESEND_COOLDOWN_SECONDS = 60

    def __init__(self):
        """Inicijalizacija Email servisa."""
        self.api_key = os.environ.get('SENDGRID_API_KEY')
        self.from_email = os.environ.get('SENDGRID_FROM_EMAIL', 'noreply@servishub.rs')
        self.from_name = os.environ.get('SENDGRID_FROM_NAME', 'ServisHub')
        self.frontend_url = os.environ.get('FRONTEND_URL', 'https://app.servishub.rs')

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

        # Posalji email preko SendGrid API
        try:
            response = requests.post(
                self.API_URL,
                json={
                    "personalizations": [
                        {
                            "to": [{"email": email}],
                            "subject": "ServisHub - Potvrdite vasu email adresu"
                        }
                    ],
                    "from": {
                        "email": self.from_email,
                        "name": self.from_name
                    },
                    "content": [
                        {
                            "type": "text/plain",
                            "value": text_content
                        },
                        {
                            "type": "text/html",
                            "value": html_content
                        }
                    ]
                },
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                timeout=10
            )

            # SendGrid vraca 202 Accepted za uspesno slanje
            if response.status_code in [200, 201, 202]:
                return True, "Verifikacioni email uspesno poslat", None
            else:
                error_msg = "Nepoznata greska"
                try:
                    error_data = response.json()
                    if 'errors' in error_data:
                        error_msg = error_data['errors'][0].get('message', error_msg)
                except:
                    pass
                raise EmailError(f"Slanje emaila nije uspelo: {error_msg}", 500)

        except requests.RequestException as e:
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


# Singleton instanca servisa
email_service = EmailService()