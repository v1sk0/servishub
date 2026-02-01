"""
SMS Management - upravljanje SMS kvotama i praćenje potrošnje po tenantima.

Omogućava platformi da:
- Postavi limite SMS-ova po tenantu
- Prati potrošnju SMS-ova
- Vidi analitiku korišćenja
- Blokira slanje kada je limit dostignut
"""

from datetime import datetime, timedelta
from sqlalchemy import func
from ..extensions import db


class TenantSmsConfig(db.Model):
    """
    Konfiguracija SMS-a za svakog tenanta.

    Definiše limite, da li je SMS omogućen, i mesečne kvote.
    """
    __tablename__ = 'tenant_sms_config'

    id = db.Column(db.Integer, primary_key=True)

    # Veza sa tenantom
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        unique=True,
        index=True
    )

    # Da li je SMS omogućen za ovog tenanta
    sms_enabled = db.Column(db.Boolean, default=True, nullable=False)

    # Mesečni limit SMS-ova (0 = neograničeno)
    monthly_limit = db.Column(db.Integer, default=100, nullable=False)

    # Upozorenje kada ostane X% kvote
    warning_threshold_percent = db.Column(db.Integer, default=20, nullable=False)

    # Da li je tenant primio upozorenje za ovaj mesec
    warning_sent_this_month = db.Column(db.Boolean, default=False)

    # Custom sender ID za tenanta (ako ima)
    custom_sender_id = db.Column(db.String(20))

    # Napomena admina
    admin_notes = db.Column(db.Text)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacije
    tenant = db.relationship('Tenant', backref=db.backref('sms_config', uselist=False))

    def __repr__(self):
        return f'<TenantSmsConfig tenant_id={self.tenant_id} limit={self.monthly_limit}>'

    @classmethod
    def get_or_create(cls, tenant_id: int):
        """Dohvata ili kreira config za tenanta."""
        config = cls.query.filter_by(tenant_id=tenant_id).first()
        if not config:
            config = cls(tenant_id=tenant_id)
            db.session.add(config)
            db.session.commit()
        return config

    def get_current_month_usage(self) -> int:
        """Vraća broj poslanih SMS-ova u tekućem mesecu."""
        now = datetime.utcnow()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return TenantSmsUsage.query.filter(
            TenantSmsUsage.tenant_id == self.tenant_id,
            TenantSmsUsage.created_at >= start_of_month,
            TenantSmsUsage.status == 'sent'
        ).count()

    def get_remaining(self) -> int:
        """Vraća preostali broj SMS-ova. -1 znači neograničeno."""
        if self.monthly_limit == 0:
            return -1
        used = self.get_current_month_usage()
        return max(0, self.monthly_limit - used)

    def can_send(self) -> bool:
        """Proverava da li tenant može poslati SMS."""
        if not self.sms_enabled:
            return False
        if self.monthly_limit == 0:  # Neograničeno
            return True
        return self.get_remaining() > 0

    def should_warn(self) -> bool:
        """Proverava da li treba poslati upozorenje o kvoti."""
        if self.monthly_limit == 0 or self.warning_sent_this_month:
            return False
        remaining = self.get_remaining()
        threshold = self.monthly_limit * (self.warning_threshold_percent / 100)
        return remaining <= threshold

    def reset_monthly_warning(self):
        """Resetuje flag za mesečno upozorenje (poziva se početkom meseca)."""
        self.warning_sent_this_month = False

    def to_dict(self):
        """Pretvara u dict za API response."""
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'sms_enabled': self.sms_enabled,
            'monthly_limit': self.monthly_limit,
            'warning_threshold_percent': self.warning_threshold_percent,
            'warning_sent_this_month': self.warning_sent_this_month,
            'custom_sender_id': self.custom_sender_id,
            'admin_notes': self.admin_notes,
            'current_usage': self.get_current_month_usage(),
            'remaining': self.get_remaining(),
            'can_send': self.can_send(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class TenantSmsUsage(db.Model):
    """
    Log svakog poslatog SMS-a po tenantu.

    Koristi se za:
    - Praćenje potrošnje
    - Analitiku
    - Billing (ako se naplaćuje po SMS-u)
    """
    __tablename__ = 'tenant_sms_usage'

    id = db.Column(db.BigInteger, primary_key=True)

    # Veza sa tenantom
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Tip SMS-a
    sms_type = db.Column(db.String(50), nullable=False, index=True)
    # Tipovi: TICKET_READY, PICKUP_REMINDER_10, PICKUP_REMINDER_30, OTP_VERIFICATION, CUSTOM

    # Primalac (maskirano za privatnost)
    recipient_masked = db.Column(db.String(20))  # +381 60 ***1234

    # Referenca na entitet (opciono)
    reference_type = db.Column(db.String(30))  # 'ticket', 'user', etc.
    reference_id = db.Column(db.BigInteger)

    # Status
    status = db.Column(db.String(20), nullable=False, default='pending')
    # sent, failed, pending

    # Greška ako nije uspelo
    error_message = db.Column(db.Text)

    # D7 Networks message ID (za praćenje)
    provider_message_id = db.Column(db.String(100), index=True)

    # Cena SMS-a (ako se naplaćuje)
    cost = db.Column(db.Numeric(10, 4), default=0)

    # =========================================================================
    # DLR (Delivery Report) polja - ažurira se preko webhook-a
    # =========================================================================
    # Status isporuke: pending, delivered, failed, expired
    delivery_status = db.Column(db.String(30), default='pending')
    # Vreme kada je DLR primljen
    delivery_status_at = db.Column(db.DateTime(timezone=True))
    # Error kod od operatora (ako je failed)
    delivery_error_code = db.Column(db.String(20))

    # Ko je inicirao slanje (ako je manuelno)
    initiated_by_user_id = db.Column(db.Integer, db.ForeignKey('tenant_user.id', ondelete='SET NULL'))

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    sent_at = db.Column(db.DateTime)

    # Relacije
    tenant = db.relationship('Tenant', backref='sms_usage')
    initiated_by = db.relationship('TenantUser', backref='initiated_sms')

    # Indeksi
    __table_args__ = (
        db.Index('ix_sms_usage_tenant_created', 'tenant_id', 'created_at'),
        db.Index('ix_sms_usage_type_status', 'sms_type', 'status'),
    )

    def __repr__(self):
        return f'<TenantSmsUsage {self.id}: {self.sms_type} -> {self.recipient_masked}>'

    @staticmethod
    def mask_phone(phone: str) -> str:
        """Maskira telefon za privatnost: +381601234567 -> +381 60 ***4567"""
        if not phone:
            return None
        # Ukloni sve osim cifara i +
        clean = ''.join(c for c in phone if c.isdigit() or c == '+')
        if len(clean) < 7:
            return '***' + clean[-4:] if len(clean) >= 4 else clean
        return clean[:-4] + '***' + clean[-4:]

    @classmethod
    def log_sms(cls, tenant_id: int, sms_type: str, recipient: str,
                status: str = 'pending', reference_type: str = None,
                reference_id: int = None, error_message: str = None,
                provider_message_id: str = None, user_id: int = None):
        """
        Loguje SMS poruku.

        Args:
            tenant_id: ID tenanta
            sms_type: Tip SMS-a (TICKET_READY, OTP, etc.)
            recipient: Broj telefona (biće maskiran)
            status: Status (sent, failed, pending)
            reference_type: Tip reference (ticket, user)
            reference_id: ID reference
            error_message: Poruka greške
            provider_message_id: ID poruke od provajdera
            user_id: ID korisnika koji je inicirao

        Returns:
            TenantSmsUsage instanca
        """
        usage = cls(
            tenant_id=tenant_id,
            sms_type=sms_type,
            recipient_masked=cls.mask_phone(recipient),
            status=status,
            reference_type=reference_type,
            reference_id=reference_id,
            error_message=error_message,
            provider_message_id=provider_message_id,
            initiated_by_user_id=user_id,
            sent_at=datetime.utcnow() if status == 'sent' else None
        )
        db.session.add(usage)
        return usage

    def mark_sent(self, provider_message_id: str = None):
        """Označava SMS kao poslan."""
        self.status = 'sent'
        self.sent_at = datetime.utcnow()
        if provider_message_id:
            self.provider_message_id = provider_message_id

    def mark_failed(self, error_message: str):
        """Označava SMS kao neuspešan."""
        self.status = 'failed'
        self.error_message = error_message

    def to_dict(self):
        """Pretvara u dict za API response."""
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'sms_type': self.sms_type,
            'recipient_masked': self.recipient_masked,
            'status': self.status,
            'error_message': self.error_message,
            'reference_type': self.reference_type,
            'reference_id': self.reference_id,
            'provider_message_id': self.provider_message_id,
            # DLR polja
            'delivery_status': self.delivery_status,
            'delivery_status_at': self.delivery_status_at.isoformat() if self.delivery_status_at else None,
            'delivery_error_code': self.delivery_error_code,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
        }


class SmsDlrLog(db.Model):
    """
    Log primljenih DLR (Delivery Report) poruka.

    Koristi se za:
    - Idempotency check - sprečava dupliranje obrade istog DLR-a
    - Audit trail - praćenje svih primljenih DLR poruka
    """
    __tablename__ = 'sms_dlr_log'

    id = db.Column(db.BigInteger, primary_key=True)

    # D7 message ID - jedinstven identifikator poruke
    message_id = db.Column(db.String(100), nullable=False, unique=True, index=True)

    # Status iz DLR-a: delivered, failed, expired
    status = db.Column(db.String(30), nullable=False)

    # Raw payload od D7 (za debug)
    raw_payload = db.Column(db.Text)

    # Error kod od operatora (ako postoji)
    error_code = db.Column(db.String(20))

    # Timestamps
    received_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<SmsDlrLog {self.message_id}: {self.status}>'


# ===== Helper funkcije za statistiku =====

def get_sms_stats_for_tenant(tenant_id: int, days: int = 30) -> dict:
    """
    Dohvata SMS statistiku za tenanta za poslednjih N dana.

    Returns:
        dict sa statistikama: total, sent, failed, by_type
    """
    since = datetime.utcnow() - timedelta(days=days)

    # Ukupno
    total_query = TenantSmsUsage.query.filter(
        TenantSmsUsage.tenant_id == tenant_id,
        TenantSmsUsage.created_at >= since
    )
    total = total_query.count()

    # Po statusu
    sent = total_query.filter(TenantSmsUsage.status == 'sent').count()
    failed = total_query.filter(TenantSmsUsage.status == 'failed').count()

    # Po tipu
    by_type = db.session.query(
        TenantSmsUsage.sms_type,
        func.count(TenantSmsUsage.id)
    ).filter(
        TenantSmsUsage.tenant_id == tenant_id,
        TenantSmsUsage.created_at >= since
    ).group_by(TenantSmsUsage.sms_type).all()

    return {
        'total': total,
        'sent': sent,
        'failed': failed,
        'pending': total - sent - failed,
        'by_type': {stype: count for stype, count in by_type},
        'days': days
    }


def get_platform_sms_stats(days: int = 30) -> dict:
    """
    Dohvata SMS statistiku za celu platformu.

    Returns:
        dict sa ukupnim statistikama i top 10 tenanata
    """
    since = datetime.utcnow() - timedelta(days=days)

    # Ukupno za platformu
    total = TenantSmsUsage.query.filter(
        TenantSmsUsage.created_at >= since
    ).count()

    sent = TenantSmsUsage.query.filter(
        TenantSmsUsage.created_at >= since,
        TenantSmsUsage.status == 'sent'
    ).count()

    failed = TenantSmsUsage.query.filter(
        TenantSmsUsage.created_at >= since,
        TenantSmsUsage.status == 'failed'
    ).count()

    # Top 10 tenanata po potrošnji
    top_tenants = db.session.query(
        TenantSmsUsage.tenant_id,
        func.count(TenantSmsUsage.id).label('count')
    ).filter(
        TenantSmsUsage.created_at >= since,
        TenantSmsUsage.status == 'sent'
    ).group_by(TenantSmsUsage.tenant_id).order_by(
        func.count(TenantSmsUsage.id).desc()
    ).limit(10).all()

    # Po tipu SMS-a
    by_type = db.session.query(
        TenantSmsUsage.sms_type,
        func.count(TenantSmsUsage.id)
    ).filter(
        TenantSmsUsage.created_at >= since
    ).group_by(TenantSmsUsage.sms_type).all()

    return {
        'total': total,
        'sent': sent,
        'failed': failed,
        'pending': total - sent - failed,
        'success_rate': round(sent / total * 100, 1) if total > 0 else 0,
        'top_tenants': [{'tenant_id': tid, 'count': cnt} for tid, cnt in top_tenants],
        'by_type': {stype: count for stype, count in by_type},
        'days': days
    }
