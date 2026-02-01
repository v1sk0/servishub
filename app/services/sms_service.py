"""
SMS servis - slanje SMS poruka kupcima i OTP verifikacija.

Koristi D7 Networks API za slanje SMS poruka.
Dokumentacija: https://d7networks.com/docs/

Funkcionalnosti:
- Slanje SMS kada je servisni nalog spreman (READY)
- Slanje podsjetnika za preuzimanje (10, 30 dana)
- OTP verifikacija telefona
- Rate limiting
"""

import os
import random
import string
import requests
from datetime import datetime, timedelta
from typing import Optional, Tuple

from ..extensions import db
from ..models import TenantUser


class SMSLimitExceeded(Exception):
    """Izuzetak kada je dostignut SMS limit."""
    def __init__(self, message: str = "SMS limit dostignut za ovaj mesec"):
        self.message = message
        super().__init__(self.message)


class SMSDisabled(Exception):
    """Izuzetak kada je SMS onemogućen za tenanta."""
    def __init__(self, message: str = "SMS je onemogućen za ovaj servis"):
        self.message = message
        super().__init__(self.message)


class SMSError(Exception):
    """Bazna klasa za SMS greske."""
    def __init__(self, message: str, code: int = 400):
        self.message = message
        self.code = code
        super().__init__(self.message)


class SMSService:
    """
    Servis za slanje SMS poruka i OTP verifikaciju.

    Koristi D7 Networks API sa environment varijablama:
    - D7_API_TOKEN: API token za D7 Networks
    - D7_SENDER_ID: ID posaljioca (default: ServisHub, max 11 karaktera)
    """

    # D7 Networks API endpoint
    API_URL = "https://api.d7networks.com/messages/v1/send"

    # OTP konfiguracija
    OTP_LENGTH = 6
    OTP_EXPIRY_MINUTES = 5
    MAX_ATTEMPTS_PER_DAY = 3
    RESEND_COOLDOWN_SECONDS = 60

    def __init__(self):
        """Inicijalizacija SMS servisa."""
        self.api_token = os.environ.get('D7_API_TOKEN')
        self.sender_id = os.environ.get('D7_SENDER_ID', 'ServisHub')

    def check_tenant_limit(self, tenant_id: int) -> Tuple[bool, str]:
        """
        Proverava da li tenant može poslati SMS.

        Returns:
            Tuple (can_send, reason)
        """
        from ..models import TenantSmsConfig

        config = TenantSmsConfig.get_or_create(tenant_id)

        if not config.sms_enabled:
            return False, "SMS je onemogućen za ovaj servis"

        if not config.can_send():
            return False, f"Dostignut mesečni limit od {config.monthly_limit} SMS poruka"

        return True, "OK"

    def _log_sms_usage(self, tenant_id: int, sms_type: str, recipient: str,
                       status: str = 'sent', reference_type: str = None,
                       reference_id: int = None, error_message: str = None,
                       provider_message_id: str = None, user_id: int = None):
        """
        Loguje SMS potrošnju u TenantSmsUsage.

        Args:
            tenant_id: ID tenanta
            sms_type: Tip SMS-a (TICKET_READY, OTP, etc.)
            recipient: Broj telefona
            status: Status (sent, failed, pending)
            reference_type: Tip reference (ticket, user)
            reference_id: ID reference
            error_message: Poruka greške
            provider_message_id: ID poruke od provajdera
            user_id: ID korisnika koji je inicirao
        """
        from ..models import TenantSmsUsage

        try:
            TenantSmsUsage.log_sms(
                tenant_id=tenant_id,
                sms_type=sms_type,
                recipient=recipient,
                status=status,
                reference_type=reference_type,
                reference_id=reference_id,
                error_message=error_message,
                provider_message_id=provider_message_id,
                user_id=user_id
            )
            db.session.commit()
        except Exception as e:
            print(f"[SMS USAGE LOG ERROR] {e}")
            # Ne prekidaj slanje ako logovanje ne uspe

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
        if not self.api_token or os.environ.get('FLASK_ENV') == 'development':
            print(f"[DEV] SMS to {formatted_phone}: {message}")
            print(f"[DEV] OTP kod: {otp_code}")
            return True, otp_code  # Vrati kod u dev modu za testiranje

        # Posalji SMS preko D7 Networks API
        success, error = self._send_via_d7(formatted_phone, message)
        if success:
            return True, "SMS uspesno poslat"
        else:
            raise SMSError(f"SMS slanje nije uspelo: {error}", 500)

    def _send_via_d7(self, phone: str, message: str) -> Tuple[bool, Optional[str]]:
        """
        Šalje SMS preko D7 Networks API.

        Args:
            phone: Broj telefona u formatu +381...
            message: Tekst poruke

        Returns:
            Tuple (success, error_message)
        """
        try:
            # Ukloni + za D7 format
            phone_number = phone.lstrip('+')

            payload = {
                "messages": [
                    {
                        "channel": "sms",
                        "recipients": [phone_number],
                        "content": message,
                        "msg_type": "text",
                        "data_coding": "text"
                    }
                ],
                "message_globals": {
                    "originator": self.sender_id
                }
            }

            headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }

            print(f"[SMS] Sending to {phone_number}: {message[:50]}...")

            response = requests.post(
                self.API_URL,
                json=payload,
                headers=headers,
                timeout=15
            )

            print(f"[SMS] D7 response status: {response.status_code}")
            print(f"[SMS] D7 response: {response.text[:200]}")

            if response.status_code in [200, 201, 202]:
                return True, None
            else:
                return False, f"D7 returned {response.status_code}: {response.text[:200]}"

        except requests.RequestException as e:
            return False, str(e)

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


    # =========================================================================
    # TICKET NOTIFICATIONS
    # =========================================================================

    def send_ticket_ready_sms(self, ticket) -> Tuple[bool, Optional[str]]:
        """
        Šalje SMS kada je servisni nalog spreman za preuzimanje.

        Args:
            ticket: ServiceTicket objekat

        Returns:
            Tuple (success, error_message)
        """
        if not ticket.customer_phone:
            return False, "Kupac nema broj telefona"

        if ticket.sms_notification_completed:
            return False, "SMS već poslat za ovaj nalog"

        # Proveri limit tenanta
        can_send, reason = self.check_tenant_limit(ticket.tenant_id)
        if not can_send:
            return False, reason

        # Dohvati ime servisa (tenant)
        tenant_name = ticket.tenant.name if ticket.tenant else "Servis"

        message = (
            f"{tenant_name}: Vas uredjaj {ticket.brand} {ticket.model} "
            f"je spreman za preuzimanje. "
            f"Nalog: SRV-{ticket.ticket_number:04d}"
        )

        # Skrati poruku na 160 karaktera
        if len(message) > 160:
            message = message[:157] + "..."

        # Formatiraj broj
        formatted_phone = self._format_phone(ticket.customer_phone)

        # Dev mode
        if not self.api_token or os.environ.get('FLASK_ENV') == 'development':
            print(f"[DEV SMS READY] To: {formatted_phone}")
            print(f"[DEV SMS READY] Message: {message}")
            ticket.sms_notification_completed = True
            # Logiraj i u dev modu
            self._log_sms_usage(
                tenant_id=ticket.tenant_id,
                sms_type='TICKET_READY',
                recipient=formatted_phone,
                status='sent',
                reference_type='ticket',
                reference_id=ticket.id
            )
            db.session.commit()
            return True, None

        # Posalji
        success, error = self._send_via_d7(formatted_phone, message)

        # Logiraj potrošnju
        self._log_sms_usage(
            tenant_id=ticket.tenant_id,
            sms_type='TICKET_READY',
            recipient=formatted_phone,
            status='sent' if success else 'failed',
            reference_type='ticket',
            reference_id=ticket.id,
            error_message=error if not success else None
        )

        if success:
            # Oznaci da je SMS poslat
            ticket.sms_notification_completed = True
            # Logiraj notifikaciju
            self._log_ticket_notification(ticket, 'SMS_READY', message)
            db.session.commit()

        return success, error

    def send_pickup_reminder_sms(self, ticket, days: int) -> Tuple[bool, Optional[str]]:
        """
        Šalje podsetnik za preuzimanje uređaja.

        Args:
            ticket: ServiceTicket objekat
            days: Broj dana od kada je nalog spreman (10 ili 30)

        Returns:
            Tuple (success, error_message)
        """
        if not ticket.customer_phone:
            return False, "Kupac nema broj telefona"

        # Proveri da li je reminder vec poslat
        if days == 10 and ticket.sms_notification_10_days:
            return False, "10-dnevni reminder već poslat"
        if days == 30 and ticket.sms_notification_30_days:
            return False, "30-dnevni reminder već poslat"

        # Proveri limit tenanta
        can_send, reason = self.check_tenant_limit(ticket.tenant_id)
        if not can_send:
            return False, reason

        tenant_name = ticket.tenant.name if ticket.tenant else "Servis"

        message = (
            f"{tenant_name}: Podsetnik - Vas uredjaj {ticket.brand} {ticket.model} "
            f"ceka preuzimanje vec {days} dana. "
            f"Nalog: SRV-{ticket.ticket_number:04d}"
        )

        if len(message) > 160:
            message = message[:157] + "..."

        formatted_phone = self._format_phone(ticket.customer_phone)
        sms_type = f'PICKUP_REMINDER_{days}'

        # Dev mode
        if not self.api_token or os.environ.get('FLASK_ENV') == 'development':
            print(f"[DEV SMS REMINDER {days}] To: {formatted_phone}")
            print(f"[DEV SMS REMINDER {days}] Message: {message}")
            if days == 10:
                ticket.sms_notification_10_days = True
            elif days == 30:
                ticket.sms_notification_30_days = True
            # Logiraj i u dev modu
            self._log_sms_usage(
                tenant_id=ticket.tenant_id,
                sms_type=sms_type,
                recipient=formatted_phone,
                status='sent',
                reference_type='ticket',
                reference_id=ticket.id
            )
            db.session.commit()
            return True, None

        success, error = self._send_via_d7(formatted_phone, message)

        # Logiraj potrošnju
        self._log_sms_usage(
            tenant_id=ticket.tenant_id,
            sms_type=sms_type,
            recipient=formatted_phone,
            status='sent' if success else 'failed',
            reference_type='ticket',
            reference_id=ticket.id,
            error_message=error if not success else None
        )

        if success:
            if days == 10:
                ticket.sms_notification_10_days = True
            elif days == 30:
                ticket.sms_notification_30_days = True
            self._log_ticket_notification(ticket, f'SMS_REMINDER_{days}', message)
            db.session.commit()

        return success, error

    def _log_ticket_notification(self, ticket, notification_type: str, message: str):
        """Loguje SMS notifikaciju u ticket notification log."""
        from ..models.ticket import TicketNotificationLog

        try:
            log = TicketNotificationLog(
                ticket_id=ticket.id,
                notification_type='SMS',
                comment=f"[{notification_type}] {message[:100]}",
                contact_successful=True
            )
            db.session.add(log)
        except Exception as e:
            print(f"[SMS LOG ERROR] {e}")


# Singleton instanca servisa
sms_service = SMSService()