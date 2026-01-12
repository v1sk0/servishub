"""
ServiceRepresentative model - KYC predstavnici servisa.

Svaki servis mora imati minimum jednog verifikovanog predstavnika
za B2C funkcije (prodaja krajnjim kupcima).
"""

import enum
from datetime import datetime
from ..extensions import db


class RepresentativeStatus(enum.Enum):
    """Status verifikacije predstavnika."""
    PENDING = 'PENDING'      # Ceka verifikaciju
    VERIFIED = 'VERIFIED'    # Verifikovan
    REJECTED = 'REJECTED'    # Odbijen


class ServiceRepresentative(db.Model):
    """
    Predstavnik servisa - fizicko lice koje predstavlja servis.

    Za B2C prodaju, servisi nastupaju kao fizicka lica (predstavnici).
    Potrebna je KYC verifikacija sa slikom licne karte.
    """
    __tablename__ = 'service_representative'

    # Primarni kljuc
    id = db.Column(db.Integer, primary_key=True)

    # Veza sa preduzecem
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Licni podaci
    ime = db.Column(db.String(50), nullable=False)
    prezime = db.Column(db.String(50), nullable=False)
    jmbg = db.Column(db.String(13))                      # Enkriptovati u produkciji!
    broj_licne_karte = db.Column(db.String(20))
    datum_rodjenja = db.Column(db.Date)

    # Kontakt
    adresa = db.Column(db.String(300))
    grad = db.Column(db.String(100))
    telefon = db.Column(db.String(30))
    email = db.Column(db.String(100))

    # Slike licne karte (Cloudinary URL)
    lk_front_url = db.Column(db.String(500))             # Prednja strana
    lk_back_url = db.Column(db.String(500))              # Zadnja strana

    # Status
    is_primary = db.Column(db.Boolean, default=False)    # Glavni predstavnik
    status = db.Column(
        db.Enum(RepresentativeStatus),
        default=RepresentativeStatus.PENDING,
        nullable=False,
        index=True
    )

    # Verifikacija
    verified_at = db.Column(db.DateTime)
    verified_by_id = db.Column(
        db.Integer,
        db.ForeignKey('platform_admin.id', ondelete='SET NULL'),
        nullable=True
    )
    rejection_reason = db.Column(db.Text)

    # Timestampovi
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relacije
    tenant = db.relationship('Tenant', backref='representatives')
    verified_by = db.relationship('PlatformAdmin', backref='verified_representatives')

    def __repr__(self):
        return f'<ServiceRepresentative {self.id}: {self.full_name}>'

    @property
    def full_name(self):
        """Puno ime predstavnika."""
        return f'{self.ime} {self.prezime}'

    @property
    def is_verified(self):
        """Da li je verifikovan."""
        return self.status == RepresentativeStatus.VERIFIED

    def verify(self, admin_id):
        """Verifikuje predstavnika."""
        self.status = RepresentativeStatus.VERIFIED
        self.verified_at = datetime.utcnow()
        self.verified_by_id = admin_id
        self.rejection_reason = None

    def reject(self, admin_id, reason):
        """Odbija verifikaciju sa razlogom."""
        self.status = RepresentativeStatus.REJECTED
        self.verified_at = datetime.utcnow()
        self.verified_by_id = admin_id
        self.rejection_reason = reason

    def to_dict(self, include_sensitive=False):
        """Konvertuje u dict za API response."""
        data = {
            'id': self.id,
            'ime': self.ime,
            'prezime': self.prezime,
            'full_name': self.full_name,
            'telefon': self.telefon,
            'email': self.email,
            'grad': self.grad,
            'is_primary': self.is_primary,
            'status': self.status.value,
            'is_verified': self.is_verified,
            'created_at': self.created_at.isoformat(),
        }

        if include_sensitive:
            data['jmbg'] = self.jmbg
            data['broj_licne_karte'] = self.broj_licne_karte
            data['adresa'] = self.adresa
            data['lk_front_url'] = self.lk_front_url
            data['lk_back_url'] = self.lk_back_url

        return data


class SubscriptionPayment(db.Model):
    """
    Uplata pretplate - pracenje uplata servisa.
    """
    __tablename__ = 'subscription_payment'

    # Primarni kljuc
    id = db.Column(db.BigInteger, primary_key=True)

    # Veza sa preduzecem
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Period
    period_start = db.Column(db.DateTime, nullable=False)
    period_end = db.Column(db.DateTime, nullable=False)

    # Stavke (JSON)
    # [{"type": "BASE", "description": "Bazni paket", "amount": 3600}, ...]
    items_json = db.Column(db.JSON)

    # Iznosi
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)
    discount_amount = db.Column(db.Numeric(10, 2), default=0)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), default='RSD')

    # Status
    status = db.Column(db.String(20), default='PENDING', nullable=False, index=True)
    # PENDING, PAID, FAILED, REFUNDED

    # Dokaz uplate
    payment_method = db.Column(db.String(20))  # BANK_TRANSFER, CARD, CASH
    payment_reference = db.Column(db.String(100))
    payment_proof_url = db.Column(db.String(500))

    # Verifikacija
    verified_by_id = db.Column(
        db.Integer,
        db.ForeignKey('platform_admin.id', ondelete='SET NULL'),
        nullable=True
    )
    verified_at = db.Column(db.DateTime)
    verification_notes = db.Column(db.Text)

    # Invoice
    invoice_number = db.Column(db.String(50))
    invoice_url = db.Column(db.String(500))

    # Timestampovi
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relacije
    tenant = db.relationship('Tenant', backref='payments')
    verified_by = db.relationship('PlatformAdmin', backref='verified_payments')

    def __repr__(self):
        return f'<SubscriptionPayment {self.id}: {self.total_amount} {self.currency}>'

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'period_start': self.period_start.isoformat(),
            'period_end': self.period_end.isoformat(),
            'items': self.items_json,
            'subtotal': float(self.subtotal),
            'discount_amount': float(self.discount_amount) if self.discount_amount else 0,
            'total_amount': float(self.total_amount),
            'currency': self.currency,
            'status': self.status,
            'payment_method': self.payment_method,
            'verified_at': self.verified_at.isoformat() if self.verified_at else None,
            'created_at': self.created_at.isoformat(),
        }
