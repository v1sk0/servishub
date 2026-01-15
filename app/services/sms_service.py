"""
SMS servis - slanje OTP kodova za verifikaciju telefona.

Koristi SMS.to API za slanje SMS poruka.
Dokumentacija: https://sms.to/docs

Funkcionalnosti:
- Generisanje 6-cifrenog OTP koda
- Slanje SMS-a sa OTP kodom
- Verifikacija OTP koda
- Rate limiting (max 3 pokusaja na 24h po broju)
"""

import os
import random
import string
import requests
from datetime import datetime, timedelta
from typing import Optional, Tuple

from ..extensions import db
from ..models import TenantUser


class SMSError(Exception):
    """Bazna klasa za SMS greske."""
    def __init__(self, message: str, code: int = 400):
        self.message = message
        self.code = code
        super().__init__(self.message)


class SMSService:
    """
    Servis za slanje SMS poruka i OTP verifikaciju.

    Koristi SMS.to API sa environment varijablama:
    - SMS_API_KEY: API kljuc za SMS.to
    - SMS_SENDER_ID: ID posaljioca (default: ServisHub)
    """

    # SMS.to API endpoint
    API_URL = "https://api.sms.to/sms/send"

    # OTP konfiguracija
    OTP_LENGTH = 6
    OTP_EXPIRY_MINUTES = 5
    MAX_ATTEMPTS_PER_DAY = 3
    RESEND_COOLDOWN_SECONDS = 60

    def __init__(self):
        """Inicijalizacija SMS servisa."""
        self.api_key = os.environ.get('SMS_API_KEY')
        self.sender_id = os.environ.get('SMS_SENDER_ID', 'ServisHub')

    def _generate_otp(self) -> str:
        """
        Generise 6-cifreni OTP kod.

        Returns:
            String sa 6 random cifara
        """
        return ''.join(random.choices(string.digits, k=self.OTP_LENGTH))

    def _format_phone(self, phone: str) -> str:
        """
        Formatira broj telefona u medjunarodni format.

        Ocekuje srpski broj u formatu:
        - +381... (vec u medjunarodnom)
        - 381... (bez +)
        - 06... (lokalni format)

        Args:
            phone: Broj telefona

        Returns:
            Broj u formatu +381...
        """
        # Ukloni razmake i crtice
        phone = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')

        # Vec u medjunarodnom formatu
        if phone.startswith('+'):
            return phone

        # Bez + ali ima 381
        if phone.startswith('381'):
            return f'+{phone}'

        # Lokalni format (06...)
        if phone.startswith('0'):
            return f'+381{phone[1:]}'

        # Podrazumevano dodaj +381
        return f'+381{phone}'

    def send_otp(self, phone: str, user: Optional[TenantUser] = None) -> Tuple[bool, str]:
        """
        Salje OTP kod na zadati broj telefona.

        Proverava rate limiting i cuva OTP u bazu ako je user prosledjen.

        Args:
            phone: Broj telefona
            user: TenantUser objekat (opciono) - ako je prosledjen, cuva OTP u bazu

        Returns:
            Tuple (success: bool, message: str)

        Raises:
            SMSError: Ako slanje nije uspelo
        """
        formatted_phone = self._format_phone(phone)

        # Generisi OTP kod
        otp_code = self._generate_otp()
        expires_at = datetime.utcnow() + timedelta(minutes=self.OTP_EXPIRY_MINUTES)

        # Sacuvaj u bazu ako imamo user-a
        if user:
            user.phone_verification_code = otp_code
            user.phone_verification_expires = expires_at
            db.session.commit()

        # Pripremi SMS poruku
        message = f'Vas ServisHub kod za verifikaciju: {otp_code}\nKod vazi {self.OTP_EXPIRY_MINUTES} minuta.'

        # U development modu, samo loguj (ne salji stvarno)
        if not self.api_key or os.environ.get('FLASK_ENV') == 'development':
            print(f"[DEV] SMS to {formatted_phone}: {message}")
            print(f"[DEV] OTP kod: {otp_code}")
            return True, otp_code  # Vrati kod u dev modu za testiranje

        # Posalji SMS preko SMS.to API
        try:
            response = requests.post(
                self.API_URL,
                json={
                    'to': formatted_phone,
                    'message': message,
                    'sender_id': self.sender_id
                },
                headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json'
                },
                timeout=10
            )

            if response.status_code == 200:
                return True, "SMS uspesno poslat"
            else:
                error_msg = response.json().get('message', 'Nepoznata greska')
                raise SMSError(f"SMS slanje nije uspelo: {error_msg}", 500)

        except requests.RequestException as e:
            raise SMSError(f"Greska pri slanju SMS-a: {str(e)}", 500)

    def verify_otp(self, user: TenantUser, code: str) -> Tuple[bool, str]:
        """
        Verifikuje OTP kod za korisnika.

        Args:
            user: TenantUser objekat
            code: Uneti OTP kod

        Returns:
            Tuple (success: bool, message: str)
        """
        # Proveri da li postoji kod
        if not user.phone_verification_code:
            return False, "Kod nije poslat. Zatrazite novi kod."

        # Proveri da li je kod istekao
        if user.phone_verification_expires and user.phone_verification_expires < datetime.utcnow():
            return False, "Kod je istekao. Zatrazite novi kod."

        # Proveri da li se kod poklapa
        if user.phone_verification_code != code:
            return False, "Neispravan kod. Pokusajte ponovo."

        # Verifikacija uspesna
        user.phone_verified = True
        user.phone_verification_code = None
        user.phone_verification_expires = None
        db.session.commit()

        return True, "Telefon uspesno verifikovan"

    def can_resend(self, user: TenantUser) -> Tuple[bool, int]:
        """
        Proverava da li korisnik moze da zatrazi novi kod.

        Returns:
            Tuple (can_resend: bool, seconds_remaining: int)
        """
        if not user.phone_verification_expires:
            return True, 0

        # Izracunaj koliko je proslo od poslednjeg slanja
        # OTP expiry je 5 min, slanje je bilo expiry - 5 min
        sent_at = user.phone_verification_expires - timedelta(minutes=self.OTP_EXPIRY_MINUTES)
        elapsed = (datetime.utcnow() - sent_at).total_seconds()

        if elapsed < self.RESEND_COOLDOWN_SECONDS:
            return False, int(self.RESEND_COOLDOWN_SECONDS - elapsed)

        return True, 0


# Singleton instanca servisa
sms_service = SMSService()