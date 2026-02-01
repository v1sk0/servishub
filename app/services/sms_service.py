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


class SMSOptedOut(Exception):
    """Izuzetak kada je klijent odbio SMS obaveštenja."""
    def __init__(self, message: str = "Klijent je odbio SMS obaveštenja"):
        self.message = message
        super().__init__(self.message)


class SMSMessageTooLong(Exception):
    """Izuzetak kada je poruka duža od 160 karaktera."""
    def __init__(self, message: str = "SMS poruka ne sme biti duža od 160 karaktera"):
        self.message = message
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

    # SMS validacija
    MAX_SMS_LENGTH = 160  # Striktni limit - bez multi-segment

    # GSM-7 transliteracija - ćiriliča i specijalni karakteri
    TRANSLITERATION_MAP = {
        'ć': 'c', 'Ć': 'C',
        'č': 'c', 'Č': 'C',
        'š': 's', 'Š': 'S',
        'đ': 'dj', 'Đ': 'Dj',
        'ž': 'z', 'Ž': 'Z',
        # Ćirilica (ako neko unese)
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd',
        'е': 'e', 'ж': 'z', 'з': 'z', 'и': 'i', 'ј': 'j',
        'к': 'k', 'л': 'l', 'љ': 'lj', 'м': 'm', 'н': 'n',
        'њ': 'nj', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's',
        'т': 't', 'ћ': 'c', 'у': 'u', 'ф': 'f', 'х': 'h',
        'ц': 'c', 'ч': 'c', 'џ': 'dz', 'ш': 's',
    }

    # OTP konfiguracija
    OTP_LENGTH = 6
    OTP_EXPIRY_MINUTES = 5
    MAX_ATTEMPTS_PER_DAY = 3
    RESEND_COOLDOWN_SECONDS = 60

    def __init__(self):
        """Inicijalizacija SMS servisa."""
        self.api_token = os.environ.get('D7_API_TOKEN')
        self.sender_id = os.environ.get('D7_SENDER_ID', 'ServisHub')

    def transliterate_gsm7(self, text: str) -> str:
        """
        Konvertuje specijalne karaktere u GSM-7 kompatibilne.

        ćčšđž → ccsdz (latinica)
        Ćirilica → latinica

        Args:
            text: Originalni tekst

        Returns:
            GSM-7 kompatibilan tekst
        """
        result = text
        for char, replacement in self.TRANSLITERATION_MAP.items():
            result = result.replace(char, replacement)
        return result

    def validate_and_prepare_message(self, message: str) -> Tuple[bool, str, str]:
        """
        Validira i priprema SMS poruku za slanje.

        1. Transliteruje specijalne karaktere
        2. Proverava dužinu (max 160)
        3. Vraća grešku ako je poruka preduga

        Args:
            message: Originalna poruka

        Returns:
            Tuple (is_valid, prepared_message, error)
        """
        # 1. Transliteracija
        prepared = self.transliterate_gsm7(message)

        # 2. Provera dužine
        if len(prepared) > self.MAX_SMS_LENGTH:
            return False, prepared, f"Poruka ima {len(prepared)} karaktera (max {self.MAX_SMS_LENGTH})"

        return True, prepared, None

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

        Flow sa naplatom:
        1. Proveri opt-out status
        2. Proveri da li tenant ima SMS uključen
        3. Proveri da li ima dovoljno kredita
        4. Validiraj i pripremi poruku (GSM-7, max 160)
        5. Naplati kredit
        6. Pošalji SMS
        7. Ako ne uspe - refund kredit

        Args:
            ticket: ServiceTicket objekat

        Returns:
            Tuple (success, error_message)
        """
        from .sms_billing_service import sms_billing_service, SMS_COST_CREDITS

        # 1. Proveri opt-out
        if hasattr(ticket, 'sms_opt_out') and ticket.sms_opt_out:
            print(f"[SMS] Skipped - customer opted out: ticket {ticket.id}")
            return False, "opted_out"

        if not ticket.customer_phone:
            return False, "Kupac nema broj telefona"

        if ticket.sms_notification_completed:
            return False, "SMS već poslat za ovaj nalog"

        # Proveri limit tenanta (admin override)
        can_send, reason = self.check_tenant_limit(ticket.tenant_id)
        if not can_send:
            return False, reason

        # Proveri rate limit (Redis) - burst protection
        from .sms_rate_limiter import rate_limiter
        rate_ok, rate_reason = rate_limiter.can_send(ticket.tenant_id, ticket.customer_phone)
        if not rate_ok:
            self._log_sms_usage(
                tenant_id=ticket.tenant_id,
                sms_type='TICKET_READY',
                recipient=ticket.customer_phone,
                status='failed',
                reference_type='ticket',
                reference_id=ticket.id,
                error_message=rate_reason
            )
            return False, rate_reason

        # Proveri da li tenant ima SMS uključen i kredit
        billing_ok, billing_reason = sms_billing_service.can_send_sms(ticket.tenant_id)
        if not billing_ok:
            # Logiraj kao neuspešno bez naplate
            self._log_sms_usage(
                tenant_id=ticket.tenant_id,
                sms_type='TICKET_READY',
                recipient=ticket.customer_phone,
                status='failed',
                reference_type='ticket',
                reference_id=ticket.id,
                error_message=billing_reason
            )
            return False, billing_reason

        # Dohvati ime servisa (tenant)
        tenant_name = ticket.tenant.name if ticket.tenant else "Servis"

        # Pripremi poruku
        raw_message = (
            f"{tenant_name}: Vas uredjaj {ticket.brand} {ticket.model} "
            f"je spreman za preuzimanje. "
            f"Nalog: SRV-{ticket.ticket_number:04d}"
        )

        # Validiraj i pripremi poruku (GSM-7 transliteracija, max 160)
        is_valid, message, validation_error = self.validate_and_prepare_message(raw_message)
        if not is_valid:
            # Poruka preduga - logiraj i odbij
            print(f"[SMS ERROR] Message too long: {validation_error}")
            self._log_sms_usage(
                tenant_id=ticket.tenant_id,
                sms_type='TICKET_READY',
                recipient=ticket.customer_phone,
                status='failed',
                reference_type='ticket',
                reference_id=ticket.id,
                error_message=f"message_too_long: {validation_error}"
            )
            return False, f"message_too_long: {validation_error}"

        # Formatiraj broj
        formatted_phone = self._format_phone(ticket.customer_phone)

        # Naplati kredit PRIJE slanja
        charge_success, transaction_id, charge_msg = sms_billing_service.charge_for_sms(
            tenant_id=ticket.tenant_id,
            sms_type='TICKET_READY',
            reference_id=ticket.id,
            description=f"SMS nalog spreman - SRV-{ticket.ticket_number:04d}"
        )

        if not charge_success:
            self._log_sms_usage(
                tenant_id=ticket.tenant_id,
                sms_type='TICKET_READY',
                recipient=formatted_phone,
                status='failed',
                reference_type='ticket',
                reference_id=ticket.id,
                error_message=charge_msg
            )
            return False, charge_msg

        # Dev mode - ne šalje stvarno ali naplaćuje
        if not self.api_token or os.environ.get('FLASK_ENV') == 'development':
            print(f"[DEV SMS READY] To: {formatted_phone}")
            print(f"[DEV SMS READY] Message: {message}")
            print(f"[DEV SMS READY] Charged: {SMS_COST_CREDITS} credits")
            ticket.sms_notification_completed = True
            self._log_sms_usage(
                tenant_id=ticket.tenant_id,
                sms_type='TICKET_READY',
                recipient=formatted_phone,
                status='sent',
                reference_type='ticket',
                reference_id=ticket.id
            )
            # Record rate limit za dev mode
            rate_limiter.record_send(ticket.tenant_id, ticket.customer_phone)
            db.session.commit()
            return True, None

        # Pošalji SMS
        success, error = self._send_via_d7(formatted_phone, message)

        if success:
            # Uspešno poslato
            ticket.sms_notification_completed = True
            self._log_sms_usage(
                tenant_id=ticket.tenant_id,
                sms_type='TICKET_READY',
                recipient=formatted_phone,
                status='sent',
                reference_type='ticket',
                reference_id=ticket.id
            )
            self._log_ticket_notification(ticket, 'SMS_READY', message)
            # Record rate limit
            rate_limiter.record_send(ticket.tenant_id, ticket.customer_phone)
            db.session.commit()
        else:
            # Neuspešno - REFUND kredit
            sms_billing_service.refund_sms(transaction_id, f"SMS slanje neuspešno: {error}")
            self._log_sms_usage(
                tenant_id=ticket.tenant_id,
                sms_type='TICKET_READY',
                recipient=formatted_phone,
                status='failed',
                reference_type='ticket',
                reference_id=ticket.id,
                error_message=error
            )

        return success, error

    def send_pickup_reminder_sms(self, ticket, days: int) -> Tuple[bool, Optional[str]]:
        """
        Šalje podsetnik za preuzimanje uređaja.

        Flow sa naplatom:
        1. Proveri opt-out status
        2. Proveri da li tenant ima SMS uključen
        3. Proveri da li ima dovoljno kredita
        4. Validiraj poruku
        5. Naplati kredit
        6. Pošalji SMS
        7. Ako ne uspe - refund kredit

        Args:
            ticket: ServiceTicket objekat
            days: Broj dana od kada je nalog spreman (10 ili 30)

        Returns:
            Tuple (success, error_message)
        """
        from .sms_billing_service import sms_billing_service, SMS_COST_CREDITS

        # 1. Proveri opt-out
        if hasattr(ticket, 'sms_opt_out') and ticket.sms_opt_out:
            print(f"[SMS] Reminder skipped - customer opted out: ticket {ticket.id}")
            return False, "opted_out"

        if not ticket.customer_phone:
            return False, "Kupac nema broj telefona"

        # Proveri da li je reminder vec poslat
        if days == 10 and ticket.sms_notification_10_days:
            return False, "10-dnevni reminder već poslat"
        if days == 30 and ticket.sms_notification_30_days:
            return False, "30-dnevni reminder već poslat"

        sms_type = f'PICKUP_REMINDER_{days}'
        formatted_phone = self._format_phone(ticket.customer_phone)

        # Proveri limit tenanta (admin override)
        can_send, reason = self.check_tenant_limit(ticket.tenant_id)
        if not can_send:
            return False, reason

        # Proveri rate limit (Redis) - burst protection
        from .sms_rate_limiter import rate_limiter
        rate_ok, rate_reason = rate_limiter.can_send(ticket.tenant_id, ticket.customer_phone)
        if not rate_ok:
            self._log_sms_usage(
                tenant_id=ticket.tenant_id,
                sms_type=sms_type,
                recipient=formatted_phone,
                status='failed',
                reference_type='ticket',
                reference_id=ticket.id,
                error_message=rate_reason
            )
            return False, rate_reason

        # Proveri da li tenant ima SMS uključen i kredit
        billing_ok, billing_reason = sms_billing_service.can_send_sms(ticket.tenant_id)
        if not billing_ok:
            self._log_sms_usage(
                tenant_id=ticket.tenant_id,
                sms_type=sms_type,
                recipient=formatted_phone,
                status='failed',
                reference_type='ticket',
                reference_id=ticket.id,
                error_message=billing_reason
            )
            return False, billing_reason

        tenant_name = ticket.tenant.name if ticket.tenant else "Servis"

        # Pripremi poruku
        raw_message = (
            f"{tenant_name}: Podsetnik - Vas uredjaj {ticket.brand} {ticket.model} "
            f"ceka preuzimanje vec {days} dana. "
            f"Nalog: SRV-{ticket.ticket_number:04d}"
        )

        # Validiraj i pripremi poruku (GSM-7 transliteracija, max 160)
        is_valid, message, validation_error = self.validate_and_prepare_message(raw_message)
        if not is_valid:
            print(f"[SMS ERROR] Reminder message too long: {validation_error}")
            self._log_sms_usage(
                tenant_id=ticket.tenant_id,
                sms_type=sms_type,
                recipient=formatted_phone,
                status='failed',
                reference_type='ticket',
                reference_id=ticket.id,
                error_message=f"message_too_long: {validation_error}"
            )
            return False, f"message_too_long: {validation_error}"

        # Naplati kredit PRIJE slanja
        charge_success, transaction_id, charge_msg = sms_billing_service.charge_for_sms(
            tenant_id=ticket.tenant_id,
            sms_type=sms_type,
            reference_id=ticket.id,
            description=f"SMS podsetnik {days} dana - SRV-{ticket.ticket_number:04d}"
        )

        if not charge_success:
            self._log_sms_usage(
                tenant_id=ticket.tenant_id,
                sms_type=sms_type,
                recipient=formatted_phone,
                status='failed',
                reference_type='ticket',
                reference_id=ticket.id,
                error_message=charge_msg
            )
            return False, charge_msg

        # Dev mode - ne šalje stvarno ali naplaćuje
        if not self.api_token or os.environ.get('FLASK_ENV') == 'development':
            print(f"[DEV SMS REMINDER {days}] To: {formatted_phone}")
            print(f"[DEV SMS REMINDER {days}] Message: {message}")
            print(f"[DEV SMS REMINDER {days}] Charged: {SMS_COST_CREDITS} credits")
            if days == 10:
                ticket.sms_notification_10_days = True
            elif days == 30:
                ticket.sms_notification_30_days = True
            self._log_sms_usage(
                tenant_id=ticket.tenant_id,
                sms_type=sms_type,
                recipient=formatted_phone,
                status='sent',
                reference_type='ticket',
                reference_id=ticket.id
            )
            # Record rate limit za dev mode
            rate_limiter.record_send(ticket.tenant_id, ticket.customer_phone)
            db.session.commit()
            return True, None

        # Pošalji SMS
        success, error = self._send_via_d7(formatted_phone, message)

        if success:
            # Uspešno poslato
            if days == 10:
                ticket.sms_notification_10_days = True
            elif days == 30:
                ticket.sms_notification_30_days = True
            self._log_sms_usage(
                tenant_id=ticket.tenant_id,
                sms_type=sms_type,
                recipient=formatted_phone,
                status='sent',
                reference_type='ticket',
                reference_id=ticket.id
            )
            self._log_ticket_notification(ticket, f'SMS_REMINDER_{days}', message)
            # Record rate limit
            rate_limiter.record_send(ticket.tenant_id, ticket.customer_phone)
            db.session.commit()
        else:
            # Neuspešno - REFUND kredit
            sms_billing_service.refund_sms(transaction_id, f"SMS slanje neuspešno: {error}")
            self._log_sms_usage(
                tenant_id=ticket.tenant_id,
                sms_type=sms_type,
                recipient=formatted_phone,
                status='failed',
                reference_type='ticket',
                reference_id=ticket.id,
                error_message=error
            )

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