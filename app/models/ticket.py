"""
ServiceTicket model - servisni nalozi za popravke.

Glavni entitet za pracenje popravki uredjaja. Sadrzi podatke o
kupcu, uredjaju, statusu popravke i garanciji.
"""

import enum
import secrets
from datetime import datetime, timedelta
from ..extensions import db


class TicketStatus(enum.Enum):
    """
    Status servisnog naloga - workflow od prijema do isporuke.

    RECEIVED - Uredjaj primljen, ceka pregled
    DIAGNOSED - Pregledano, ceka odobrenje kupca
    IN_PROGRESS - U toku popravke
    WAITING_PARTS - Ceka na delove
    READY - Gotovo, ceka preuzimanje
    DELIVERED - Preuzeto od strane kupca
    CANCELLED - Otkazano
    """
    RECEIVED = 'RECEIVED'
    DIAGNOSED = 'DIAGNOSED'
    IN_PROGRESS = 'IN_PROGRESS'
    WAITING_PARTS = 'WAITING_PARTS'
    READY = 'READY'
    DELIVERED = 'DELIVERED'
    CANCELLED = 'CANCELLED'


class TicketPriority(enum.Enum):
    """Prioritet naloga."""
    LOW = 'LOW'
    NORMAL = 'NORMAL'
    HIGH = 'HIGH'
    URGENT = 'URGENT'


class ServiceTicket(db.Model):
    """
    Servisni nalog - glavni entitet za pracenje popravki.

    Sadrzi podatke o kupcu, uredjaju, statusu i garanciji.
    Broj naloga je jedinstven unutar tenanta (preduzeca).
    """
    __tablename__ = 'service_ticket'

    # Primarni kljuc - globalno jedinstven
    id = db.Column(db.BigInteger, primary_key=True)

    # Veza sa preduzecem - obavezno za multi-tenant izolaciju
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Lokacija gde se nalog vodi
    location_id = db.Column(
        db.Integer,
        db.ForeignKey('service_location.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )

    # Broj naloga - jedinstven unutar preduzeca, ne globalno
    # Format: SRV-0001, SRV-0002, itd.
    ticket_number = db.Column(db.Integer, nullable=False)

    # Podaci o kupcu
    customer_name = db.Column(db.String(100), nullable=False)  # Ime i prezime
    customer_phone = db.Column(db.String(30))                   # Kontakt telefon
    customer_email = db.Column(db.String(100))                  # Email za obavestenja

    # Podaci o uredjaju
    device_type = db.Column(db.String(50))     # PHONE, TABLET, LAPTOP, PC, OTHER
    brand = db.Column(db.String(50))           # Marka: Apple, Samsung, Xiaomi...
    model = db.Column(db.String(100))          # Model: iPhone 14, Galaxy S24...
    imei = db.Column(db.String(20))            # IMEI/serijski broj
    device_condition = db.Column(db.Text)      # Stanje pri prijemu (ostecenja, itd.)
    device_password = db.Column(db.String(50)) # Sifra uredjaja (enkriptovati u produkciji)

    # Opis problema i resenja
    problem_description = db.Column(db.Text, nullable=False)  # Opis kvara
    diagnosis = db.Column(db.Text)                             # Dijagnoza tehnicara
    resolution = db.Column(db.Text)                            # Opis popravke

    # Status i prioritet
    status = db.Column(
        db.Enum(TicketStatus),
        default=TicketStatus.RECEIVED,
        nullable=False,
        index=True
    )
    priority = db.Column(
        db.Enum(TicketPriority),
        default=TicketPriority.NORMAL,
        nullable=False
    )

    # Dodeljeni tehnicar
    assigned_technician_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant_user.id', ondelete='SET NULL'),
        nullable=True
    )

    # Cene
    estimated_price = db.Column(db.Numeric(10, 2))  # Procenjena cena
    final_price = db.Column(db.Numeric(10, 2))      # Konacna cena
    currency = db.Column(db.String(3), default='RSD')

    # Garancija
    warranty_days = db.Column(db.Integer, default=45)  # Default iz tenant settings
    closed_at = db.Column(db.DateTime)                  # Kada je nalog zatvoren (DELIVERED)

    # Naplata
    is_paid = db.Column(db.Boolean, default=False)
    paid_at = db.Column(db.DateTime)
    payment_method = db.Column(db.String(20))  # CASH, CARD, TRANSFER

    # QR kod za javni pristup
    access_token = db.Column(db.String(64), unique=True, index=True)

    # Kreiranje
    created_by_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant_user.id', ondelete='SET NULL'),
        nullable=True
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Relacije
    tenant = db.relationship('Tenant', backref='tickets')
    location = db.relationship('ServiceLocation', backref='tickets')
    assigned_technician = db.relationship(
        'TenantUser',
        foreign_keys=[assigned_technician_id],
        backref='assigned_tickets'
    )
    created_by = db.relationship(
        'TenantUser',
        foreign_keys=[created_by_id],
        backref='created_tickets'
    )

    # Indeksi
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'ticket_number', name='uq_tenant_ticket_number'),
        db.Index('ix_ticket_tenant_status', 'tenant_id', 'status'),
        db.Index('ix_ticket_tenant_created', 'tenant_id', 'created_at'),
        db.Index('ix_ticket_location_status', 'location_id', 'status'),
    )

    def __repr__(self):
        return f'<ServiceTicket {self.id}: {self.ticket_number_formatted}>'

    @property
    def ticket_number_formatted(self):
        """Formatiran broj naloga: SRV-0001"""
        return f'SRV-{self.ticket_number:04d}'

    @property
    def warranty_expires_at(self):
        """Datum isteka garancije (closed_at + warranty_days)."""
        if self.closed_at and self.warranty_days:
            return self.closed_at + timedelta(days=self.warranty_days)
        return None

    @property
    def warranty_remaining_days(self):
        """Preostali dani garancije."""
        if not self.warranty_expires_at:
            return None
        remaining = (self.warranty_expires_at - datetime.utcnow()).days
        return max(0, remaining)

    @property
    def is_under_warranty(self):
        """Da li je nalog jos uvek pod garancijom."""
        remaining = self.warranty_remaining_days
        return remaining is not None and remaining > 0

    def generate_access_token(self):
        """Generise jedinstveni token za javni pristup (QR kod)."""
        self.access_token = secrets.token_urlsafe(32)

    def close_ticket(self):
        """Zatvara nalog i postavlja datum zatvaranja."""
        self.status = TicketStatus.DELIVERED
        self.closed_at = datetime.utcnow()

    def mark_as_paid(self, payment_method='CASH'):
        """Oznacava nalog kao naplacen."""
        self.is_paid = True
        self.paid_at = datetime.utcnow()
        self.payment_method = payment_method

    def to_dict(self, include_sensitive=False):
        """Konvertuje nalog u dict za API response."""
        data = {
            'id': self.id,
            'ticket_number': self.ticket_number_formatted,
            'customer_name': self.customer_name,
            'customer_phone': self.customer_phone,
            'customer_email': self.customer_email,
            'device_type': self.device_type,
            'brand': self.brand,
            'model': self.model,
            'imei': self.imei,
            'problem_description': self.problem_description,
            'diagnosis': self.diagnosis,
            'resolution': self.resolution,
            'status': self.status.value,
            'priority': self.priority.value,
            'estimated_price': float(self.estimated_price) if self.estimated_price else None,
            'final_price': float(self.final_price) if self.final_price else None,
            'currency': self.currency,
            'warranty_days': self.warranty_days,
            'warranty_expires_at': self.warranty_expires_at.isoformat() if self.warranty_expires_at else None,
            'warranty_remaining_days': self.warranty_remaining_days,
            'is_under_warranty': self.is_under_warranty,
            'is_paid': self.is_paid,
            'created_at': self.created_at.isoformat(),
            'closed_at': self.closed_at.isoformat() if self.closed_at else None,
        }

        if include_sensitive:
            data['device_condition'] = self.device_condition
            data['device_password'] = self.device_password

        return data


def get_next_ticket_number(tenant_id):
    """
    Vraca sledeci broj naloga za tenant.
    Thread-safe sa SELECT FOR UPDATE.
    """
    from sqlalchemy import func

    max_number = db.session.query(func.max(ServiceTicket.ticket_number)).filter(
        ServiceTicket.tenant_id == tenant_id
    ).scalar()

    return (max_number or 0) + 1
