"""
Security Event Model - Cuva bezbednosne dogadjaje u bazi.

Omogucava pregled svih sigurnosnih aktivnosti u admin panelu:
- Login pokusaji (uspesni i neuspesni)
- OAuth aktivnosti
- Rate limit prekoracenja
- 2FA eventi
- Sumnjive aktivnosti
"""

import enum
from datetime import datetime, timezone
from ..extensions import db


class SecurityEventType(enum.Enum):
    """Tipovi bezbednosnih dogadjaja."""

    # Auth events
    LOGIN_SUCCESS = 'login_success'
    LOGIN_FAILED = 'login_failed'
    LOGIN_LOCKED = 'login_locked'
    LOGOUT = 'logout'

    # OAuth events
    OAUTH_STARTED = 'oauth_started'
    OAUTH_SUCCESS = 'oauth_success'
    OAUTH_FAILED = 'oauth_failed'
    OAUTH_CSRF_INVALID = 'oauth_csrf_invalid'
    OAUTH_PKCE_INVALID = 'oauth_pkce_invalid'

    # Token events
    TOKEN_REFRESH = 'token_refresh'
    TOKEN_INVALID = 'token_invalid'
    TOKEN_EXPIRED = 'token_expired'

    # Rate limiting
    RATE_LIMIT_EXCEEDED = 'rate_limit_exceeded'

    # 2FA events
    TWO_FA_SETUP = '2fa_setup'
    TWO_FA_ENABLED = '2fa_enabled'
    TWO_FA_DISABLED = '2fa_disabled'
    TWO_FA_VERIFIED = '2fa_verified'
    TWO_FA_FAILED = '2fa_failed'
    TWO_FA_BACKUP_USED = '2fa_backup_used'

    # Suspicious activity
    SUSPICIOUS_IP = 'suspicious_ip'
    BRUTE_FORCE_DETECTED = 'brute_force_detected'

    # Admin events
    ADMIN_LOGIN_SUCCESS = 'admin_login_success'
    ADMIN_LOGIN_FAILED = 'admin_login_failed'
    ADMIN_ACTION = 'admin_action'

    # Networking events (T2T)
    INVITE_CREATED = 'invite_created'
    INVITE_ACCEPTED = 'invite_accepted'
    INVITE_REVOKED = 'invite_revoked'
    INVITE_INVALID = 'invite_invalid'
    CONNECTION_CREATED = 'connection_created'
    CONNECTION_BLOCKED = 'connection_blocked'
    CONNECTION_UNBLOCKED = 'connection_unblocked'
    CONNECTION_DELETED = 'connection_deleted'
    CONNECTION_PERMISSIONS_CHANGED = 'connection_permissions_changed'

    # Messaging events
    MESSAGE_SENT = 'message_sent'
    MESSAGE_EDITED = 'message_edited'
    MESSAGE_HIDDEN = 'message_hidden'
    THREAD_CREATED = 'thread_created'
    THREAD_STATUS_CHANGED = 'thread_status_changed'


class SecurityEventSeverity(enum.Enum):
    """Ozbiljnost dogadjaja."""
    INFO = 'info'
    WARNING = 'warning'
    ERROR = 'error'
    CRITICAL = 'critical'


class SecurityEvent(db.Model):
    """
    Security Event - bezbednosni dogadjaj sacuvan u bazi.

    Omogucava pregled i analizu svih sigurnosnih aktivnosti.
    """
    __tablename__ = 'security_event'

    id = db.Column(db.Integer, primary_key=True)

    # Tip i ozbiljnost dogadjaja
    event_type = db.Column(db.String(50), nullable=False, index=True)
    severity = db.Column(db.String(20), nullable=False, default='info')

    # Ko je izvrsio akciju (opciono)
    user_id = db.Column(db.Integer, nullable=True, index=True)
    user_type = db.Column(db.String(20), nullable=True)  # 'tenant_user', 'admin', 'guest'
    email_hash = db.Column(db.String(64), nullable=True)  # SHA256 hash za privatnost

    # Tenant ID - za pracenje security eventova po servisu
    tenant_id = db.Column(db.Integer, nullable=True, index=True)

    # IP i User Agent
    ip_address = db.Column(db.String(45), nullable=True, index=True)  # IPv6 max 45 chars
    user_agent = db.Column(db.String(500), nullable=True)

    # Request info
    endpoint = db.Column(db.String(200), nullable=True)
    method = db.Column(db.String(10), nullable=True)

    # Detalji dogadjaja (JSON)
    details = db.Column(db.Text, nullable=True)  # JSON string

    # Timestamp
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True
    )

    def __repr__(self):
        return f'<SecurityEvent {self.id}: {self.event_type} at {self.created_at}>'

    @classmethod
    def log(cls, event_type: str, severity: str = 'info',
            user_id: int = None, user_type: str = None, email_hash: str = None,
            tenant_id: int = None,
            ip_address: str = None, user_agent: str = None,
            endpoint: str = None, method: str = None,
            details: dict = None) -> 'SecurityEvent':
        """
        Kreira novi security event.

        Args:
            event_type: Tip dogadjaja (iz SecurityEventType)
            severity: Ozbiljnost (info, warning, error, critical)
            user_id: ID korisnika (opciono)
            user_type: Tip korisnika (tenant_user, admin, guest)
            email_hash: Hash email adrese za privatnost
            tenant_id: ID tenanta (servisa) - za pracenje po tenantima
            ip_address: IP adresa klijenta
            user_agent: User Agent string
            endpoint: API endpoint
            method: HTTP metoda
            details: Dodatni detalji (dict)

        Returns:
            Kreirani SecurityEvent objekat
        """
        import json

        event = cls(
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            user_type=user_type,
            email_hash=email_hash,
            tenant_id=tenant_id,
            ip_address=ip_address,
            user_agent=user_agent[:500] if user_agent else None,
            endpoint=endpoint,
            method=method,
            details=json.dumps(details) if details else None
        )

        db.session.add(event)
        # Ne radimo commit ovde - pozivalac treba da uradi commit
        return event

    def to_dict(self) -> dict:
        """Konvertuje event u dict za API response."""
        import json

        return {
            'id': self.id,
            'event_type': self.event_type,
            'severity': self.severity,
            'user_id': self.user_id,
            'user_type': self.user_type,
            'tenant_id': self.tenant_id,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent[:100] + '...' if self.user_agent and len(self.user_agent) > 100 else self.user_agent,
            'endpoint': self.endpoint,
            'method': self.method,
            'details': json.loads(self.details) if self.details else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    @classmethod
    def get_stats(cls, hours: int = 24) -> dict:
        """
        Vraca statistiku security eventova za zadati period.

        Args:
            hours: Broj sati unazad (default 24h)

        Returns:
            Dict sa statistikom
        """
        from sqlalchemy import func
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        # Ukupno eventova
        total = cls.query.filter(cls.created_at >= cutoff).count()

        # Po tipu
        by_type = db.session.query(
            cls.event_type,
            func.count(cls.id)
        ).filter(
            cls.created_at >= cutoff
        ).group_by(cls.event_type).all()

        # Po ozbiljnosti
        by_severity = db.session.query(
            cls.severity,
            func.count(cls.id)
        ).filter(
            cls.created_at >= cutoff
        ).group_by(cls.severity).all()

        # Unique IP adrese
        unique_ips = db.session.query(
            func.count(func.distinct(cls.ip_address))
        ).filter(
            cls.created_at >= cutoff
        ).scalar()

        # Failed logins
        failed_logins = cls.query.filter(
            cls.created_at >= cutoff,
            cls.event_type.in_(['login_failed', 'admin_login_failed'])
        ).count()

        # Rate limits
        rate_limits = cls.query.filter(
            cls.created_at >= cutoff,
            cls.event_type == 'rate_limit_exceeded'
        ).count()

        return {
            'total': total,
            'by_type': {t: c for t, c in by_type},
            'by_severity': {s: c for s, c in by_severity},
            'unique_ips': unique_ips,
            'failed_logins': failed_logins,
            'rate_limits': rate_limits,
            'period_hours': hours
        }

    @classmethod
    def get_top_ips(cls, hours: int = 24, limit: int = 10) -> list:
        """
        Vraca top IP adrese po broju eventova.

        Args:
            hours: Broj sati unazad
            limit: Maksimalan broj rezultata

        Returns:
            Lista dict-ova sa IP i count
        """
        from sqlalchemy import func
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        results = db.session.query(
            cls.ip_address,
            func.count(cls.id).label('count')
        ).filter(
            cls.created_at >= cutoff,
            cls.ip_address.isnot(None)
        ).group_by(
            cls.ip_address
        ).order_by(
            func.count(cls.id).desc()
        ).limit(limit).all()

        return [{'ip': ip, 'count': count} for ip, count in results]

    @classmethod
    def cleanup_old_events(cls, days: int = 90) -> int:
        """
        Brise stare evente (starije od X dana).

        Args:
            days: Broj dana nakon kojih se brisu eventi

        Returns:
            Broj obrisanih eventa
        """
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        deleted = cls.query.filter(cls.created_at < cutoff).delete()
        db.session.commit()

        return deleted