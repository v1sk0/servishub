"""
Notification Service - centralizovan servis za slanje admin notifikacija.

Funkcionalnosti:
- Slanje security, billing i system notifikacija
- Idempotency (sprečava duplikate preko event_key)
- Rate limiting (sprečava spam)
- Retry sa exponential backoff
- Logging svih notifikacija u notification_log
"""

import os
import time
import requests
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import List, Dict, Optional, Tuple, Any
from flask import request, g

from ..extensions import db
from ..models.notification import (
    AdminNotificationSettings, NotificationLog,
    NotificationType, RATE_LIMITS
)


class NotificationService:
    """
    Centralizovan servis za slanje notifikacija administratorima.

    Koristi Brevo (ex Sendinblue) za email. SMS priprema za budućnost.
    """

    # Brevo API endpoint
    API_URL = "https://api.brevo.com/v3/smtp/email"

    # Retry config
    MAX_RETRIES = 3
    BACKOFF_MULTIPLIER = 2  # 1s, 2s, 4s

    def __init__(self):
        """Inicijalizacija servisa."""
        self.api_key = os.environ.get('BREVO_API_KEY')
        self.from_email = os.environ.get('BREVO_FROM_EMAIL', 'noreply@servishub.rs')
        self.from_name = os.environ.get('BREVO_FROM_NAME', 'ServisHub')
        self.frontend_url = os.environ.get('FRONTEND_URL', 'https://app.servishub.rs')

    # =========================================================================
    # CORE METHODS
    # =========================================================================

    @staticmethod
    def get_settings() -> AdminNotificationSettings:
        """Dohvata singleton instancu notification settings."""
        return AdminNotificationSettings.get_settings()

    @staticmethod
    def generate_event_key(event_type: str, context: Dict[str, Any]) -> str:
        """
        Generiše unique key za sprečavanje duplikata.

        Args:
            event_type: Tip notifikacije
            context: Kontekst sa podacima (email, invoice_number, itd.)

        Returns:
            Event key string
        """
        now = datetime.utcnow()

        if event_type == 'FAILED_LOGIN':
            # Max 1 notifikacija po email-u na sat
            email = context.get('email', 'unknown')
            return f"FAILED_LOGIN:{email}:{now.strftime('%Y-%m-%d-%H')}"

        elif event_type == 'NEW_PAYMENT':
            # Max 1 notifikacija po uplatnici
            invoice = context.get('invoice_number', now.isoformat())
            return f"NEW_PAYMENT:{invoice}"

        elif event_type == 'DAILY_SUMMARY':
            # Max 1 dnevno
            return f"DAILY_SUMMARY:{date.today().isoformat()}"

        elif event_type == 'WEEKLY_REPORT':
            # Max 1 nedeljno (po ISO nedelji)
            week = now.isocalendar()[1]
            return f"WEEKLY_REPORT:{now.year}-W{week:02d}"

        elif event_type == 'NEW_TENANT_REGISTERED':
            tenant_id = context.get('tenant_id', now.isoformat())
            return f"NEW_TENANT:{tenant_id}"

        elif event_type == 'TENANT_SUSPENDED':
            tenant_id = context.get('tenant_id', now.isoformat())
            return f"SUSPENDED:{tenant_id}:{now.strftime('%Y-%m-%d')}"

        # Default: event + timestamp (hour granularity)
        return f"{event_type}:{now.strftime('%Y-%m-%d-%H')}"

    @staticmethod
    def check_rate_limit(notification_type: str) -> bool:
        """
        Proverava da li je dozvoljeno slanje (rate limit).

        Returns:
            True ako je OK da se pošalje
        """
        limits = RATE_LIMITS.get(notification_type)
        if not limits:
            return True  # Nema limita

        return NotificationLog.check_rate_limit(
            notification_type,
            max_count=limits['max_count'],
            window_hours=limits['window_hours']
        )

    def _send_email_with_retry(self, to_emails: List[str], subject: str,
                                html_content: str, text_content: str) -> Tuple[bool, Optional[str]]:
        """
        Šalje email sa retry logikom (exponential backoff).

        Args:
            to_emails: Lista email adresa
            subject: Subject emaila
            html_content: HTML body
            text_content: Plain text body

        Returns:
            Tuple (success, error_message)
        """
        # Dev mode - samo loguj
        if not self.api_key or os.environ.get('FLASK_ENV') == 'development':
            print(f"[DEV NOTIFICATION] To: {to_emails}")
            print(f"[DEV NOTIFICATION] Subject: {subject}")
            return True, None

        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                # Brevo API payload format
                payload = {
                    "sender": {
                        "name": self.from_name,
                        "email": self.from_email
                    },
                    "to": [{"email": email} for email in to_emails],
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

                if response.status_code in [200, 201, 202]:
                    return True, None
                else:
                    last_error = f"Brevo returned {response.status_code}: {response.text[:200]}"

            except Exception as e:
                last_error = str(e)

            # Exponential backoff
            if attempt < self.MAX_RETRIES - 1:
                sleep_time = self.BACKOFF_MULTIPLIER ** attempt
                time.sleep(sleep_time)

        return False, last_error

    def _log_notification(self, notification_type: str, recipient: str,
                          subject: str, content: str, status: str,
                          event_key: str = None, payload: Dict = None,
                          error_message: str = None,
                          tenant_id: int = None, admin_id: int = None) -> NotificationLog:
        """
        Loguje notifikaciju u bazu.

        Returns:
            NotificationLog objekat
        """
        ip_address = None
        user_agent = None
        try:
            if request:
                ip_address = request.remote_addr
                user_agent = request.headers.get('User-Agent', '')[:500]
        except RuntimeError:
            pass

        log = NotificationLog(
            notification_type=notification_type,
            channel='email',
            recipient=recipient,
            subject=subject,
            content=content[:1000] if content else None,  # Truncate
            status=status,
            event_key=event_key,
            payload=payload or {},
            error_message=error_message,
            related_tenant_id=tenant_id,
            related_admin_id=admin_id,
            ip_address=ip_address,
            user_agent=user_agent
        )

        if status == 'sent':
            log.sent_at = datetime.utcnow()

        db.session.add(log)
        db.session.commit()
        return log

    def _send_notification(self, notification_type: NotificationType,
                           subject: str, html_content: str, text_content: str,
                           context: Dict[str, Any] = None,
                           tenant_id: int = None, admin_id: int = None) -> bool:
        """
        Interni helper za slanje notifikacije sa svim proverama.

        Returns:
            bool: True ako je uspešno poslato
        """
        context = context or {}
        type_str = notification_type.value

        # 1. Proveri da li je notifikacija uključena
        settings = self.get_settings()
        if not settings.should_notify(notification_type):
            print(f"[NOTIFICATION] {type_str} is disabled, skipping")
            return False

        # 2. Proveri da li ima primalaca
        recipients = settings.get_recipients('email')
        if not recipients:
            print(f"[NOTIFICATION] No recipients configured, skipping")
            return False

        # 3. Generiši event key i proveri idempotency
        event_key = self.generate_event_key(type_str, context)
        if NotificationLog.already_sent(event_key):
            print(f"[NOTIFICATION] Already sent: {event_key}")
            return False

        # 4. Proveri rate limit
        if not self.check_rate_limit(type_str):
            print(f"[NOTIFICATION] Rate limit exceeded for {type_str}")
            return False

        # 5. Pošalji email
        success, error = self._send_email_with_retry(
            recipients, subject, html_content, text_content
        )

        # 6. Loguj
        self._log_notification(
            notification_type=type_str,
            recipient=', '.join(recipients),
            subject=subject,
            content=text_content,
            status='sent' if success else 'failed',
            event_key=event_key,
            payload=context,
            error_message=error,
            tenant_id=tenant_id,
            admin_id=admin_id
        )

        return success

    # =========================================================================
    # SECURITY NOTIFICATIONS
    # =========================================================================

    def notify_failed_login(self, email: str, ip: str, attempts: int) -> bool:
        """
        Šalje notifikaciju o neuspešnim pokušajima prijave.

        Args:
            email: Email koji pokušava da se prijavi
            ip: IP adresa
            attempts: Broj pokušaja
        """
        settings = self.get_settings()
        if attempts < settings.failed_login_threshold:
            return False

        subject = f"[SECURITY] Neuspešni pokušaji prijave: {email}"
        html = self._build_security_email_html(
            title="Neuspešni pokušaji prijave",
            message=f"Detektovano je <strong>{attempts}</strong> neuspešnih pokušaja prijave.",
            details={
                "Email": email,
                "IP adresa": ip,
                "Broj pokušaja": str(attempts),
                "Vreme": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
            },
            severity="warning"
        )
        text = f"Neuspešni pokušaji prijave\n\nEmail: {email}\nIP: {ip}\nPokušaji: {attempts}"

        return self._send_notification(
            NotificationType.FAILED_LOGIN,
            subject, html, text,
            context={'email': email, 'ip': ip, 'attempts': attempts}
        )

    def notify_new_device_login(self, admin_email: str, admin_name: str,
                                 ip: str, user_agent: str) -> bool:
        """
        Šalje notifikaciju o prijavi sa novog uređaja.
        """
        subject = f"[SECURITY] Nova prijava: {admin_email}"
        html = self._build_security_email_html(
            title="Prijava sa novog uređaja",
            message=f"Admin <strong>{admin_name}</strong> se prijavio sa novog uređaja/lokacije.",
            details={
                "Admin": f"{admin_name} ({admin_email})",
                "IP adresa": ip,
                "Uređaj": user_agent[:100] if user_agent else "Nepoznato",
                "Vreme": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
            },
            severity="info"
        )
        text = f"Nova prijava\n\nAdmin: {admin_name}\nIP: {ip}"

        return self._send_notification(
            NotificationType.NEW_DEVICE_LOGIN,
            subject, html, text,
            context={'admin_email': admin_email, 'ip': ip}
        )

    def notify_password_change(self, admin_email: str, admin_name: str) -> bool:
        """Šalje notifikaciju o promeni lozinke."""
        subject = f"[SECURITY] Promenjena lozinka: {admin_email}"
        html = self._build_security_email_html(
            title="Promenjena admin lozinka",
            message=f"Admin <strong>{admin_name}</strong> je promenio svoju lozinku.",
            details={
                "Admin": f"{admin_name} ({admin_email})",
                "Vreme": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
            },
            severity="info"
        )
        text = f"Promenjena lozinka\n\nAdmin: {admin_name} ({admin_email})"

        return self._send_notification(
            NotificationType.ADMIN_PASSWORD_CHANGE,
            subject, html, text,
            context={'admin_email': admin_email}
        )

    def notify_2fa_disabled(self, admin_email: str, admin_name: str) -> bool:
        """Šalje notifikaciju o isključivanju 2FA."""
        subject = f"[SECURITY] 2FA isključen: {admin_email}"
        html = self._build_security_email_html(
            title="2FA autentifikacija isključena",
            message=f"Admin <strong>{admin_name}</strong> je isključio dvo-faktorsku autentifikaciju.",
            details={
                "Admin": f"{admin_name} ({admin_email})",
                "Vreme": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
            },
            severity="warning"
        )
        text = f"2FA isključen\n\nAdmin: {admin_name} ({admin_email})"

        return self._send_notification(
            NotificationType.TWO_FA_DISABLED,
            subject, html, text,
            context={'admin_email': admin_email}
        )

    # =========================================================================
    # BILLING NOTIFICATIONS
    # =========================================================================

    def notify_new_payment(self, tenant_name: str, tenant_id: int,
                           invoice_number: str, amount: Decimal) -> bool:
        """Šalje notifikaciju o novoj uplati."""
        subject = f"[BILLING] Nova uplata: {tenant_name} - {amount:,.0f} RSD"
        html = self._build_billing_email_html(
            title="Nova uplata primljena",
            message=f"Servis <strong>{tenant_name}</strong> je izvršio uplatu.",
            details={
                "Servis": tenant_name,
                "Faktura": invoice_number,
                "Iznos": f"{amount:,.0f} RSD",
                "Vreme": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
            },
            color="#059669"
        )
        text = f"Nova uplata\n\nServis: {tenant_name}\nFaktura: {invoice_number}\nIznos: {amount:,.0f} RSD"

        return self._send_notification(
            NotificationType.NEW_PAYMENT,
            subject, html, text,
            context={'tenant_id': tenant_id, 'invoice_number': invoice_number, 'amount': str(amount)},
            tenant_id=tenant_id
        )

    def notify_payment_overdue(self, tenant_name: str, tenant_id: int,
                               days_overdue: int, amount: Decimal) -> bool:
        """Šalje notifikaciju o kašnjenju uplate."""
        subject = f"[BILLING] Kasni uplata: {tenant_name} ({days_overdue} dana)"
        html = self._build_billing_email_html(
            title="Faktura prekoračila rok",
            message=f"Servis <strong>{tenant_name}</strong> kasni sa uplatom.",
            details={
                "Servis": tenant_name,
                "Dana kašnjenja": str(days_overdue),
                "Dugovanje": f"{amount:,.0f} RSD"
            },
            color="#f59e0b" if days_overdue <= 7 else "#dc2626"
        )
        text = f"Kašnjenje uplate\n\nServis: {tenant_name}\nDana: {days_overdue}\nDugovanje: {amount:,.0f} RSD"

        return self._send_notification(
            NotificationType.PAYMENT_OVERDUE,
            subject, html, text,
            context={'tenant_id': tenant_id, 'days': days_overdue, 'amount': str(amount)},
            tenant_id=tenant_id
        )

    def notify_suspension(self, tenant_name: str, tenant_id: int, reason: str) -> bool:
        """Šalje notifikaciju o suspenziji servisa."""
        subject = f"[BILLING] Servis suspendovan: {tenant_name}"
        html = self._build_billing_email_html(
            title="Servis suspendovan",
            message=f"Servis <strong>{tenant_name}</strong> je suspendovan.",
            details={
                "Servis": tenant_name,
                "Razlog": reason,
                "Vreme": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
            },
            color="#dc2626"
        )
        text = f"Servis suspendovan\n\nServis: {tenant_name}\nRazlog: {reason}"

        return self._send_notification(
            NotificationType.TENANT_SUSPENDED,
            subject, html, text,
            context={'tenant_id': tenant_id, 'reason': reason},
            tenant_id=tenant_id
        )

    # =========================================================================
    # SYSTEM NOTIFICATIONS
    # =========================================================================

    def notify_new_tenant(self, tenant_name: str, tenant_id: int, email: str) -> bool:
        """Šalje notifikaciju o novom servisu."""
        subject = f"[SYSTEM] Novi servis registrovan: {tenant_name}"
        html = self._build_system_email_html(
            title="Novi servis registrovan",
            message=f"Novi servis <strong>{tenant_name}</strong> je kreiran na platformi.",
            details={
                "Naziv servisa": tenant_name,
                "Email": email,
                "Vreme": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
            }
        )
        text = f"Novi servis\n\nNaziv: {tenant_name}\nEmail: {email}"

        return self._send_notification(
            NotificationType.NEW_TENANT_REGISTERED,
            subject, html, text,
            context={'tenant_id': tenant_id, 'email': email},
            tenant_id=tenant_id
        )

    def notify_kyc_submitted(self, tenant_name: str, tenant_id: int, rep_name: str) -> bool:
        """Šalje notifikaciju o novoj KYC verifikaciji."""
        subject = f"[SYSTEM] Nova KYC verifikacija: {tenant_name}"
        html = self._build_system_email_html(
            title="Nova KYC verifikacija",
            message=f"Servis <strong>{tenant_name}</strong> je podneo KYC dokumentaciju.",
            details={
                "Servis": tenant_name,
                "Predstavnik": rep_name,
                "Vreme": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
            }
        )
        text = f"Nova KYC verifikacija\n\nServis: {tenant_name}\nPredstavnik: {rep_name}"

        return self._send_notification(
            NotificationType.KYC_SUBMITTED,
            subject, html, text,
            context={'tenant_id': tenant_id, 'rep_name': rep_name},
            tenant_id=tenant_id
        )

    def send_daily_summary(self) -> bool:
        """
        Šalje dnevni sumarni izveštaj.
        Poziva se iz scheduler-a u 08:00 CET.
        """
        from ..models import Tenant, SubscriptionPayment, TenantStatus

        # Prikupi statistiku za juče
        yesterday = date.today() - timedelta(days=1)

        # Novi servisi
        new_tenants = Tenant.query.filter(
            db.func.date(Tenant.created_at) == yesterday
        ).count()

        # Uplate
        payments = SubscriptionPayment.query.filter(
            db.func.date(SubscriptionPayment.created_at) == yesterday,
            SubscriptionPayment.status == 'PAID'
        ).all()
        total_revenue = sum(p.amount for p in payments) if payments else Decimal('0')

        # Aktivni servisi
        active_count = Tenant.query.filter(
            Tenant.status.in_([TenantStatus.ACTIVE, TenantStatus.TRIAL, TenantStatus.PROMO])
        ).count()

        subject = f"[REPORT] Dnevni izveštaj - {yesterday.strftime('%d.%m.%Y')}"
        html = self._build_report_email_html(
            title=f"Dnevni izveštaj - {yesterday.strftime('%d.%m.%Y')}",
            stats={
                "Novi servisi": str(new_tenants),
                "Ukupne uplate": f"{total_revenue:,.0f} RSD",
                "Broj uplata": str(len(payments)),
                "Aktivni servisi": str(active_count)
            }
        )
        text = f"Dnevni izveštaj - {yesterday}\n\nNovi servisi: {new_tenants}\nUplate: {total_revenue:,.0f} RSD"

        return self._send_notification(
            NotificationType.DAILY_SUMMARY,
            subject, html, text,
            context={'date': yesterday.isoformat()}
        )

    def send_weekly_report(self) -> bool:
        """
        Šalje nedeljni izveštaj.
        Poziva se iz scheduler-a ponedeljkom u 08:00 CET.
        """
        from ..models import Tenant, SubscriptionPayment, TenantStatus

        # Prikupi statistiku za prethodnu nedelju
        today = date.today()
        week_start = today - timedelta(days=today.weekday() + 7)
        week_end = week_start + timedelta(days=6)

        # Novi servisi
        new_tenants = Tenant.query.filter(
            db.func.date(Tenant.created_at) >= week_start,
            db.func.date(Tenant.created_at) <= week_end
        ).count()

        # Uplate
        payments = SubscriptionPayment.query.filter(
            db.func.date(SubscriptionPayment.created_at) >= week_start,
            db.func.date(SubscriptionPayment.created_at) <= week_end,
            SubscriptionPayment.status == 'PAID'
        ).all()
        total_revenue = sum(p.amount for p in payments) if payments else Decimal('0')

        # Aktivni servisi
        active_count = Tenant.query.filter(
            Tenant.status.in_([TenantStatus.ACTIVE, TenantStatus.TRIAL, TenantStatus.PROMO])
        ).count()

        # Suspendovani
        suspended_count = Tenant.query.filter(
            Tenant.status == TenantStatus.SUSPENDED
        ).count()

        subject = f"[REPORT] Nedeljni izveštaj - {week_start.strftime('%d.%m')} - {week_end.strftime('%d.%m.%Y')}"
        html = self._build_report_email_html(
            title=f"Nedeljni izveštaj ({week_start.strftime('%d.%m')} - {week_end.strftime('%d.%m.%Y')})",
            stats={
                "Novi servisi": str(new_tenants),
                "Ukupne uplate": f"{total_revenue:,.0f} RSD",
                "Broj uplata": str(len(payments)),
                "Aktivni servisi": str(active_count),
                "Suspendovani": str(suspended_count)
            }
        )
        text = f"Nedeljni izveštaj\n\nNovi servisi: {new_tenants}\nUplate: {total_revenue:,.0f} RSD"

        return self._send_notification(
            NotificationType.WEEKLY_REPORT,
            subject, html, text,
            context={'week_start': week_start.isoformat(), 'week_end': week_end.isoformat()}
        )

    # =========================================================================
    # EMAIL TEMPLATES
    # =========================================================================

    def _build_security_email_html(self, title: str, message: str,
                                    details: Dict[str, str], severity: str = "warning") -> str:
        """Gradi HTML za security email."""
        color = "#f59e0b" if severity == "warning" else "#667eea"
        detail_rows = '\n'.join([
            f'<tr><td style="padding: 8px 0; color: #6b7280;">{k}:</td><td style="padding: 8px 0; text-align: right;">{v}</td></tr>'
            for k, v in details.items()
        ])
        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: {color}; padding: 20px; border-radius: 10px 10px 0 0; text-align: center;">
                <h1 style="color: white; margin: 0; font-size: 20px;">ServisHub Security</h1>
            </div>
            <div style="background: #f9fafb; padding: 25px; border: 1px solid #e5e7eb;">
                <h2 style="margin-top: 0; font-size: 18px;">{title}</h2>
                <p>{message}</p>
                <table style="width: 100%; border-collapse: collapse; margin-top: 15px;">
                    {detail_rows}
                </table>
            </div>
            <div style="text-align: center; padding: 15px; color: #9ca3af; font-size: 11px;">
                <p>ServisHub Admin Notifications</p>
            </div>
        </body>
        </html>
        """

    def _build_billing_email_html(self, title: str, message: str,
                                   details: Dict[str, str], color: str = "#667eea") -> str:
        """Gradi HTML za billing email."""
        detail_rows = '\n'.join([
            f'<tr><td style="padding: 8px 0; color: #6b7280;">{k}:</td><td style="padding: 8px 0; text-align: right;">{v}</td></tr>'
            for k, v in details.items()
        ])
        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: {color}; padding: 20px; border-radius: 10px 10px 0 0; text-align: center;">
                <h1 style="color: white; margin: 0; font-size: 20px;">ServisHub Billing</h1>
            </div>
            <div style="background: #f9fafb; padding: 25px; border: 1px solid #e5e7eb;">
                <h2 style="margin-top: 0; font-size: 18px;">{title}</h2>
                <p>{message}</p>
                <table style="width: 100%; border-collapse: collapse; margin-top: 15px;">
                    {detail_rows}
                </table>
            </div>
            <div style="text-align: center; padding: 15px; color: #9ca3af; font-size: 11px;">
                <p>ServisHub Admin Notifications</p>
            </div>
        </body>
        </html>
        """

    def _build_system_email_html(self, title: str, message: str,
                                  details: Dict[str, str]) -> str:
        """Gradi HTML za system email."""
        detail_rows = '\n'.join([
            f'<tr><td style="padding: 8px 0; color: #6b7280;">{k}:</td><td style="padding: 8px 0; text-align: right;">{v}</td></tr>'
            for k, v in details.items()
        ])
        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: #667eea; padding: 20px; border-radius: 10px 10px 0 0; text-align: center;">
                <h1 style="color: white; margin: 0; font-size: 20px;">ServisHub System</h1>
            </div>
            <div style="background: #f9fafb; padding: 25px; border: 1px solid #e5e7eb;">
                <h2 style="margin-top: 0; font-size: 18px;">{title}</h2>
                <p>{message}</p>
                <table style="width: 100%; border-collapse: collapse; margin-top: 15px;">
                    {detail_rows}
                </table>
            </div>
            <div style="text-align: center; padding: 15px; color: #9ca3af; font-size: 11px;">
                <p>ServisHub Admin Notifications</p>
            </div>
        </body>
        </html>
        """

    def _build_report_email_html(self, title: str, stats: Dict[str, str]) -> str:
        """Gradi HTML za report email."""
        stat_cards = '\n'.join([
            f'''<div style="background: white; border-radius: 8px; padding: 15px; text-align: center; flex: 1; min-width: 120px; margin: 5px;">
                <div style="font-size: 24px; font-weight: 700; color: #667eea;">{v}</div>
                <div style="font-size: 12px; color: #6b7280; margin-top: 5px;">{k}</div>
            </div>'''
            for k, v in stats.items()
        ])
        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 25px; border-radius: 10px 10px 0 0; text-align: center;">
                <h1 style="color: white; margin: 0; font-size: 22px;">{title}</h1>
            </div>
            <div style="background: #f3f4f6; padding: 25px; border: 1px solid #e5e7eb;">
                <div style="display: flex; flex-wrap: wrap; gap: 10px; justify-content: center;">
                    {stat_cards}
                </div>
            </div>
            <div style="text-align: center; padding: 15px; color: #9ca3af; font-size: 11px;">
                <p>ServisHub Admin Reports</p>
            </div>
        </body>
        </html>
        """


# Singleton instanca servisa
notification_service = NotificationService()
