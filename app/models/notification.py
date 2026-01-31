"""
Admin Notification System - sistem notifikacija za platform admine.

Omogucava konfigurisanje koje notifikacije ce se slati (security, billing, system)
i na koje kanale (email, SMS u buducnosti).
"""

import enum
from datetime import datetime, timedelta
from ..extensions import db


class NotificationType(enum.Enum):
    """Tipovi notifikacija."""
    # Security events
    FAILED_LOGIN = 'FAILED_LOGIN'
    NEW_DEVICE_LOGIN = 'NEW_DEVICE_LOGIN'
    ADMIN_PASSWORD_CHANGE = 'ADMIN_PASSWORD_CHANGE'
    TWO_FA_DISABLED = 'TWO_FA_DISABLED'
    SUSPICIOUS_ACTIVITY = 'SUSPICIOUS_ACTIVITY'

    # Billing events
    NEW_PAYMENT = 'NEW_PAYMENT'
    PAYMENT_OVERDUE = 'PAYMENT_OVERDUE'
    TENANT_SUSPENDED = 'TENANT_SUSPENDED'
    SUBSCRIPTION_EXPIRING = 'SUBSCRIPTION_EXPIRING'

    # System events
    NEW_TENANT_REGISTERED = 'NEW_TENANT_REGISTERED'
    KYC_SUBMITTED = 'KYC_SUBMITTED'
    DAILY_SUMMARY = 'DAILY_SUMMARY'
    WEEKLY_REPORT = 'WEEKLY_REPORT'


class NotificationChannel(enum.Enum):
    """Kanali za slanje notifikacija."""
    EMAIL = 'email'
    SMS = 'sms'  # Za buducnost


class NotificationStatus(enum.Enum):
    """Status notifikacije."""
    PENDING = 'pending'
    SENT = 'sent'
    FAILED = 'failed'


class AdminNotificationSettings(db.Model):
    """
    Globalna podesavanja notifikacija za platformu.

    Singleton pattern - uvek postoji samo jedan red (id=1).
    Svi admini dele ista podesavanja.
    """
    __tablename__ = 'admin_notification_settings'

    id = db.Column(db.Integer, primary_key=True)

    # ===== Primaoci =====
    # Lista email adresa za primanje notifikacija
    email_recipients = db.Column(db.JSON, default=list)
    # Lista telefona za SMS (buducnost)
    sms_recipients = db.Column(db.JSON, default=list)

    # ===== Security Events =====
    notify_failed_login = db.Column(db.Boolean, default=True, nullable=False)
    notify_new_device = db.Column(db.Boolean, default=True, nullable=False)
    notify_password_change = db.Column(db.Boolean, default=True, nullable=False)
    notify_2fa_disabled = db.Column(db.Boolean, default=True, nullable=False)
    notify_suspicious = db.Column(db.Boolean, default=True, nullable=False)

    # ===== Billing Events =====
    notify_new_payment = db.Column(db.Boolean, default=False, nullable=False)
    notify_payment_overdue = db.Column(db.Boolean, default=True, nullable=False)
    notify_suspension = db.Column(db.Boolean, default=True, nullable=False)
    notify_expiring = db.Column(db.Boolean, default=True, nullable=False)

    # ===== System Events =====
    notify_new_tenant = db.Column(db.Boolean, default=True, nullable=False)
    notify_kyc_submitted = db.Column(db.Boolean, default=True, nullable=False)
    notify_daily_summary = db.Column(db.Boolean, default=False, nullable=False)
    notify_weekly_report = db.Column(db.Boolean, default=True, nullable=False)

    # ===== Thresholds =====
    failed_login_threshold = db.Column(db.Integer, default=3, nullable=False)
    overdue_days_threshold = db.Column(db.Integer, default=7, nullable=False)

    # ===== Timestamps =====
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<AdminNotificationSettings id={self.id}>'

    @classmethod
    def get_settings(cls):
        """
        Dohvata singleton instancu podesavanja.
        Kreira default ako ne postoji.
        """
        settings = cls.query.first()
        if not settings:
            settings = cls(id=1, email_recipients=[], sms_recipients=[])
            db.session.add(settings)
            db.session.commit()
        return settings

    def should_notify(self, notification_type: NotificationType) -> bool:
        """Proverava da li treba slati notifikaciju za dati tip."""
        mapping = {
            NotificationType.FAILED_LOGIN: self.notify_failed_login,
            NotificationType.NEW_DEVICE_LOGIN: self.notify_new_device,
            NotificationType.ADMIN_PASSWORD_CHANGE: self.notify_password_change,
            NotificationType.TWO_FA_DISABLED: self.notify_2fa_disabled,
            NotificationType.SUSPICIOUS_ACTIVITY: self.notify_suspicious,
            NotificationType.NEW_PAYMENT: self.notify_new_payment,
            NotificationType.PAYMENT_OVERDUE: self.notify_payment_overdue,
            NotificationType.TENANT_SUSPENDED: self.notify_suspension,
            NotificationType.SUBSCRIPTION_EXPIRING: self.notify_expiring,
            NotificationType.NEW_TENANT_REGISTERED: self.notify_new_tenant,
            NotificationType.KYC_SUBMITTED: self.notify_kyc_submitted,
            NotificationType.DAILY_SUMMARY: self.notify_daily_summary,
            NotificationType.WEEKLY_REPORT: self.notify_weekly_report,
        }
        return mapping.get(notification_type, False)

    def get_recipients(self, channel: str = 'email') -> list:
        """Vraca listu primalaca za dati kanal."""
        if channel == 'email':
            return self.email_recipients or []
        elif channel == 'sms':
            return self.sms_recipients or []
        return []

    def to_dict(self):
        """Pretvara u dict za API response."""
        return {
            'email_recipients': self.email_recipients or [],
            'sms_recipients': self.sms_recipients or [],
            # Security
            'notify_failed_login': self.notify_failed_login,
            'notify_new_device': self.notify_new_device,
            'notify_password_change': self.notify_password_change,
            'notify_2fa_disabled': self.notify_2fa_disabled,
            'notify_suspicious': self.notify_suspicious,
            # Billing
            'notify_new_payment': self.notify_new_payment,
            'notify_payment_overdue': self.notify_payment_overdue,
            'notify_suspension': self.notify_suspension,
            'notify_expiring': self.notify_expiring,
            # System
            'notify_new_tenant': self.notify_new_tenant,
            'notify_kyc_submitted': self.notify_kyc_submitted,
            'notify_daily_summary': self.notify_daily_summary,
            'notify_weekly_report': self.notify_weekly_report,
            # Thresholds
            'failed_login_threshold': self.failed_login_threshold,
            'overdue_days_threshold': self.overdue_days_threshold,
            # Meta
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class NotificationLog(db.Model):
    """
    Log svih poslanih notifikacija.

    Cuva istoriju notifikacija sa statusom, payload-om i event_key za idempotency.
    """
    __tablename__ = 'notification_log'

    id = db.Column(db.BigInteger, primary_key=True)

    # ===== Tip i kanal =====
    notification_type = db.Column(db.String(50), nullable=False, index=True)
    channel = db.Column(db.String(20), nullable=False, default='email')

    # ===== Primalac i sadrzaj =====
    recipient = db.Column(db.String(200), nullable=False)
    subject = db.Column(db.String(300))
    content = db.Column(db.Text)

    # ===== Status =====
    status = db.Column(db.String(20), nullable=False, default='pending', index=True)
    error_message = db.Column(db.Text)

    # ===== Payload za debugging =====
    payload = db.Column(db.JSON, default=dict)

    # ===== Idempotency =====
    event_key = db.Column(db.String(200), index=True)

    # ===== Reference =====
    related_tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    related_admin_id = db.Column(
        db.Integer,
        db.ForeignKey('platform_admin.id', ondelete='SET NULL'),
        nullable=True
    )

    # ===== Request context =====
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(500))

    # ===== Timestamps =====
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    sent_at = db.Column(db.DateTime)

    # Indeksi
    __table_args__ = (
        db.Index('ix_notification_log_type_created', 'notification_type', 'created_at'),
        db.Index('ix_notification_log_event_key_status', 'event_key', 'status'),
    )

    def __repr__(self):
        return f'<NotificationLog {self.id}: {self.notification_type} -> {self.recipient}>'

    @classmethod
    def already_sent(cls, event_key: str) -> bool:
        """
        Proverava da li je notifikacija sa datim event_key vec uspesno poslata.
        Koristi se za idempotency - sprecavanje duplikata.
        """
        if not event_key:
            return False
        exists = cls.query.filter_by(
            event_key=event_key,
            status='sent'
        ).first()
        return exists is not None

    @classmethod
    def count_in_window(cls, notification_type: str, window_hours: int = 1) -> int:
        """
        Broji koliko je notifikacija datog tipa poslato u poslednjih N sati.
        Koristi se za rate limiting.
        """
        since = datetime.utcnow() - timedelta(hours=window_hours)
        return cls.query.filter(
            cls.notification_type == notification_type,
            cls.created_at >= since,
            cls.status == 'sent'
        ).count()

    @classmethod
    def check_rate_limit(cls, notification_type: str, max_count: int, window_hours: int = 1) -> bool:
        """
        Proverava da li je dozvoljeno slanje notifikacije (rate limit).
        Vraca True ako je OK da se posalje, False ako je limit dostignut.
        """
        count = cls.count_in_window(notification_type, window_hours)
        return count < max_count

    def mark_sent(self):
        """Oznacava notifikaciju kao uspesno poslatu."""
        self.status = 'sent'
        self.sent_at = datetime.utcnow()

    def mark_failed(self, error_message: str):
        """Oznacava notifikaciju kao neuspesnu."""
        self.status = 'failed'
        self.error_message = error_message

    def to_dict(self):
        """Pretvara u dict za API response."""
        return {
            'id': self.id,
            'notification_type': self.notification_type,
            'channel': self.channel,
            'recipient': self.recipient,
            'subject': self.subject,
            'status': self.status,
            'error_message': self.error_message,
            'payload': self.payload,
            'event_key': self.event_key,
            'related_tenant_id': self.related_tenant_id,
            'related_admin_id': self.related_admin_id,
            'ip_address': self.ip_address,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
        }


# ===== Rate Limit Config =====
RATE_LIMITS = {
    'FAILED_LOGIN': {'max_count': 10, 'window_hours': 1},
    'NEW_DEVICE_LOGIN': {'max_count': 5, 'window_hours': 1},
    'SUSPICIOUS_ACTIVITY': {'max_count': 3, 'window_hours': 1},
    'DAILY_SUMMARY': {'max_count': 1, 'window_hours': 24},
    'WEEKLY_REPORT': {'max_count': 1, 'window_hours': 168},  # 7 dana
    # Ostali tipovi nemaju limit
}
