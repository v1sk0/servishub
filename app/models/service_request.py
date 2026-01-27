"""
ServiceRequest i ServiceBid modeli - B2C marketplace zahtevi i ponude.
"""

import enum
from datetime import datetime
from ..extensions import db


class ServiceRequestStatus(enum.Enum):
    """Status zahteva za servis."""
    OPEN = 'OPEN'
    IN_BIDDING = 'IN_BIDDING'
    ACCEPTED = 'ACCEPTED'
    IN_PROGRESS = 'IN_PROGRESS'
    COMPLETED = 'COMPLETED'
    CANCELLED = 'CANCELLED'
    EXPIRED = 'EXPIRED'


class ServiceRequestCategory(enum.Enum):
    """Kategorija servisnog zahteva."""
    SCREEN_REPAIR = 'SCREEN_REPAIR'
    BATTERY = 'BATTERY'
    CHARGING_PORT = 'CHARGING_PORT'
    WATER_DAMAGE = 'WATER_DAMAGE'
    SOFTWARE = 'SOFTWARE'
    CAMERA = 'CAMERA'
    SPEAKER = 'SPEAKER'
    UNLOCKING = 'UNLOCKING'
    DATA_RECOVERY = 'DATA_RECOVERY'
    GENERAL = 'GENERAL'
    OTHER = 'OTHER'


class ServiceBidStatus(enum.Enum):
    """Status ponude servisa."""
    PENDING = 'PENDING'
    ACCEPTED = 'ACCEPTED'
    REJECTED = 'REJECTED'
    WITHDRAWN = 'WITHDRAWN'


class ServiceRequest(db.Model):
    """Zahtev za servis od fizičkog lica."""
    __tablename__ = 'service_request'

    id = db.Column(db.BigInteger, primary_key=True)

    public_user_id = db.Column(
        db.BigInteger,
        db.ForeignKey('public_user.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Kategorija i opis
    category = db.Column(db.Enum(ServiceRequestCategory), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)

    # Uređaj
    device_type = db.Column(db.String(50))   # 'phone', 'tablet', 'laptop'
    device_brand = db.Column(db.String(50))
    device_model = db.Column(db.String(100))

    # Lokacija
    city = db.Column(db.String(100), index=True)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

    # Budžet
    budget_min = db.Column(db.Numeric(10, 2))
    budget_max = db.Column(db.Numeric(10, 2))
    currency = db.Column(db.String(3), default='RSD')

    # Hitnost: 1=nisko, 2=srednje, 3=hitno
    urgency = db.Column(db.Integer, default=2)

    # Status
    status = db.Column(
        db.Enum(ServiceRequestStatus),
        default=ServiceRequestStatus.OPEN,
        nullable=False,
        index=True
    )
    expires_at = db.Column(db.DateTime)

    # Statistika
    bid_count = db.Column(db.Integer, default=0)
    view_count = db.Column(db.Integer, default=0)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacije
    bids = db.relationship('ServiceBid', backref='service_request', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<ServiceRequest {self.id}: {self.title}>'


class ServiceBid(db.Model):
    """Ponuda servisa za zahtev."""
    __tablename__ = 'service_bid'

    id = db.Column(db.BigInteger, primary_key=True)

    service_request_id = db.Column(
        db.BigInteger,
        db.ForeignKey('service_request.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    location_id = db.Column(
        db.Integer,
        db.ForeignKey('service_location.id', ondelete='SET NULL')
    )

    # Ponuda
    price = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), default='RSD')
    estimated_days = db.Column(db.Integer)
    warranty_days = db.Column(db.Integer, default=45)
    description = db.Column(db.Text)

    # Status
    status = db.Column(
        db.Enum(ServiceBidStatus),
        default=ServiceBidStatus.PENDING,
        nullable=False
    )

    # Kredit transakcija za bid
    credit_transaction_id = db.Column(db.BigInteger, db.ForeignKey('credit_transaction.id', ondelete='SET NULL'))

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    accepted_at = db.Column(db.DateTime)

    __table_args__ = (
        db.UniqueConstraint('service_request_id', 'tenant_id', name='uq_bid_request_tenant'),
    )

    def __repr__(self):
        return f'<ServiceBid {self.id}: request={self.service_request_id} tenant={self.tenant_id}>'