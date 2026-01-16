"""
Tenant Message model - sistem poruka za servise.

Omogucava:
- Sistemske poruke (automatska obavestenja o fakturama, kasnjenjima, itd.)
- Admin poruke (direktna komunikacija admin -> servis)
- Buduce: komunikacija izmedju servisa i sa dobavljacima
"""

import enum
from datetime import datetime
from ..extensions import db


class MessageType(enum.Enum):
    """
    Tip poruke po poreklu.
    """
    SYSTEM = 'SYSTEM'       # Automatska sistemska poruka
    ADMIN = 'ADMIN'         # Od platform admina
    TENANT = 'TENANT'       # Od drugog servisa (buduce)
    SUPPLIER = 'SUPPLIER'   # Od dobavljaca (buduce)


class MessagePriority(enum.Enum):
    """
    Prioritet poruke.
    """
    LOW = 'LOW'
    NORMAL = 'NORMAL'
    HIGH = 'HIGH'
    URGENT = 'URGENT'


class MessageCategory(enum.Enum):
    """
    Kategorija poruke.
    """
    BILLING = 'BILLING'               # Fakture, uplate, pretplate
    PACKAGE_CHANGE = 'PACKAGE_CHANGE' # Promene cena, paketa
    SYSTEM = 'SYSTEM'                 # Sistemska obavestenja
    SUPPORT = 'SUPPORT'               # Podrska
    ANNOUNCEMENT = 'ANNOUNCEMENT'     # Obavestenja platforme
    OTHER = 'OTHER'


class TenantMessage(db.Model):
    """
    Poruka za servis (tenant).

    Koristi se za sistemska obavestenja i komunikaciju sa adminima.
    """
    __tablename__ = 'tenant_message'

    # Primarni kljuc
    id = db.Column(db.Integer, primary_key=True)

    # Primalac (servis)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Tip poruke
    message_type = db.Column(
        db.Enum(MessageType),
        nullable=False,
        default=MessageType.SYSTEM
    )

    # Posiljalac (opciono, zavisi od tipa)
    sender_admin_id = db.Column(
        db.Integer,
        db.ForeignKey('platform_admin.id', ondelete='SET NULL'),
        nullable=True
    )
    sender_tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='SET NULL'),
        nullable=True
    )

    # Sadrzaj poruke
    subject = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)

    # Akcija (opciono - link na relevantnu stranicu)
    action_url = db.Column(db.String(500))  # npr. "/subscription"
    action_label = db.Column(db.String(100))  # npr. "Pogledaj fakturu"

    # Prioritet i kategorija
    priority = db.Column(
        db.Enum(MessagePriority),
        default=MessagePriority.NORMAL,
        nullable=False
    )
    category = db.Column(
        db.Enum(MessageCategory),
        default=MessageCategory.SYSTEM,
        nullable=False,
        index=True
    )

    # Status citanja
    is_read = db.Column(db.Boolean, default=False, nullable=False, index=True)
    read_at = db.Column(db.DateTime)
    read_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant_user.id', ondelete='SET NULL'),
        nullable=True
    )

    # Povezana faktura (ako je BILLING kategorija)
    related_payment_id = db.Column(
        db.Integer,
        db.ForeignKey('subscription_payment.id', ondelete='SET NULL'),
        nullable=True
    )

    # Da li je obrisana (soft delete)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime)

    # Timestamp
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True
    )

    # Relacije
    tenant = db.relationship(
        'Tenant',
        foreign_keys=[tenant_id],
        backref=db.backref('messages', lazy='dynamic')
    )
    sender_admin = db.relationship('PlatformAdmin')
    sender_tenant = db.relationship('Tenant', foreign_keys=[sender_tenant_id])
    related_payment = db.relationship('SubscriptionPayment')

    # Indeksi
    __table_args__ = (
        db.Index('ix_tenant_message_unread', 'tenant_id', 'is_read', 'is_deleted'),
        db.Index('ix_tenant_message_created', 'tenant_id', 'created_at'),
    )

    def __repr__(self):
        return f'<TenantMessage {self.id}: {self.subject[:30]}>'

    def mark_as_read(self, user_id=None):
        """Oznacava poruku kao procitanu."""
        if not self.is_read:
            self.is_read = True
            self.read_at = datetime.utcnow()
            self.read_by_user_id = user_id

    def soft_delete(self):
        """Soft delete poruke."""
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()

    def to_dict(self):
        """Pretvara u dict za API response."""
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'message_type': self.message_type.value,
            'sender_admin_id': self.sender_admin_id,
            'subject': self.subject,
            'body': self.body,
            'action_url': self.action_url,
            'action_label': self.action_label,
            'priority': self.priority.value,
            'category': self.category.value,
            'is_read': self.is_read,
            'read_at': self.read_at.isoformat() if self.read_at else None,
            'related_payment_id': self.related_payment_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def create_system_message(cls, tenant_id, subject, body, category=MessageCategory.SYSTEM,
                               priority=MessagePriority.NORMAL, action_url=None, action_label=None,
                               related_payment_id=None):
        """
        Helper za kreiranje sistemske poruke.

        Args:
            tenant_id: ID servisa koji prima poruku
            subject: Naslov poruke
            body: Tekst poruke
            category: Kategorija (default SYSTEM)
            priority: Prioritet (default NORMAL)
            action_url: Link na akciju (opciono)
            action_label: Label za akciju (opciono)
            related_payment_id: ID povezane fakture (opciono)

        Returns:
            Kreirana TenantMessage instanca (NIJE UPISANA U BAZU - commit uraditi naknadno)
        """
        message = cls(
            tenant_id=tenant_id,
            message_type=MessageType.SYSTEM,
            subject=subject,
            body=body,
            category=category,
            priority=priority,
            action_url=action_url,
            action_label=action_label,
            related_payment_id=related_payment_id
        )
        db.session.add(message)
        return message

    @classmethod
    def create_admin_message(cls, tenant_id, admin_id, subject, body,
                              category=MessageCategory.SUPPORT, priority=MessagePriority.NORMAL):
        """
        Helper za kreiranje admin poruke.

        Args:
            tenant_id: ID servisa koji prima poruku
            admin_id: ID admina koji salje
            subject: Naslov poruke
            body: Tekst poruke
            category: Kategorija (default SUPPORT)
            priority: Prioritet (default NORMAL)

        Returns:
            Kreirana TenantMessage instanca
        """
        message = cls(
            tenant_id=tenant_id,
            message_type=MessageType.ADMIN,
            sender_admin_id=admin_id,
            subject=subject,
            body=body,
            category=category,
            priority=priority
        )
        db.session.add(message)
        return message

    @classmethod
    def get_unread_count(cls, tenant_id):
        """Vraca broj neprocitanih poruka za servis."""
        return cls.query.filter(
            cls.tenant_id == tenant_id,
            cls.is_read == False,
            cls.is_deleted == False
        ).count()