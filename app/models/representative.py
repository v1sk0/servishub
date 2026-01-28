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
    prezime = db.Column(db.String(50), nullable=True)   # Opciono
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
        if self.prezime:
            return f'{self.ime} {self.prezime}'
        return self.ime

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


class PaymentStatus(enum.Enum):
    """Status fakture/uplate."""
    PENDING = 'PENDING'       # Ocekuje uplatu
    PAID = 'PAID'             # Placeno i verifikovano
    OVERDUE = 'OVERDUE'       # Kasni sa uplatom
    CANCELLED = 'CANCELLED'   # Otkazano
    REFUNDED = 'REFUNDED'     # Refundirano


class SubscriptionPayment(db.Model):
    """
    Faktura/uplata za pretplatu servisa.

    Svaka faktura pokriva jedan obracunski period (mesec) i sadrzi
    stavke za bazni paket i dodatne lokacije.
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

    # Broj fakture (jedinstven, format: SH-YYYY-NNNNNN)
    invoice_number = db.Column(db.String(50), unique=True, index=True)

    # Period koji pokriva ova faktura
    period_start = db.Column(db.Date)
    period_end = db.Column(db.Date)

    # Stavke fakture (JSON array)
    items_json = db.Column(db.JSON, default=list)

    # Iznosi
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)
    discount_amount = db.Column(db.Numeric(10, 2), default=0)
    discount_reason = db.Column(db.String(200))
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), default='RSD')

    # Status i rokovi
    status = db.Column(db.String(20), default='PENDING', nullable=False, index=True)
    due_date = db.Column(db.Date)  # Rok za placanje

    # Podaci o uplati
    paid_at = db.Column(db.DateTime)
    payment_method = db.Column(db.String(20))  # BANK_TRANSFER, CARD, CASH
    payment_reference = db.Column(db.String(100))
    payment_proof_url = db.Column(db.String(500))
    payment_notes = db.Column(db.Text)

    # Verifikacija
    verified_by_id = db.Column(
        db.Integer,
        db.ForeignKey('platform_admin.id', ondelete='SET NULL'),
        nullable=True
    )
    verified_at = db.Column(db.DateTime)
    verification_notes = db.Column(db.Text)

    # Da li je generisana automatski
    is_auto_generated = db.Column(db.Boolean, default=True)

    # URL generisane PDF fakture
    invoice_url = db.Column(db.String(500))

    # === v303 Billing Enhancement ===
    # Invoice delivery tracking
    invoice_sent_at = db.Column(db.DateTime)
    invoice_sent_to = db.Column(db.String(200))  # Email adresa primaoca

    # Uplatnica PDF
    uplatnica_pdf_url = db.Column(db.String(500))

    # IPS QR data (cached)
    ips_qr_string = db.Column(db.Text)
    ips_qr_generated_at = db.Column(db.DateTime)

    # Poziv na broj - model (sam payment_reference već postoji gore)
    payment_reference_model = db.Column(db.String(5), default='97')

    # Bank reconciliation
    reconciled_at = db.Column(db.DateTime)
    reconciled_via = db.Column(db.String(50))  # BANK_IMPORT, MANUAL, PROOF_UPLOAD
    bank_transaction_id = db.Column(db.BigInteger, db.ForeignKey('bank_transaction.id'))
    # === Kraj v303 ===

    # Timestampovi
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacije
    tenant = db.relationship('Tenant', backref=db.backref('subscription_payments', lazy='dynamic'))
    verified_by = db.relationship('PlatformAdmin', backref='verified_payments')
    bank_transaction = db.relationship('BankTransaction', foreign_keys=[bank_transaction_id])

    # Indeksi
    __table_args__ = (
        db.Index('ix_subscription_payment_tenant_status', 'tenant_id', 'status'),
    )

    def __repr__(self):
        return f'<SubscriptionPayment {self.invoice_number}: {self.total_amount} {self.currency} ({self.status})>'

    @property
    def is_overdue(self):
        """Da li je faktura prekoracila rok za placanje."""
        if self.status == 'PAID':
            return False
        if not self.due_date:
            return False
        from datetime import date
        return self.due_date < date.today()

    @property
    def days_overdue(self):
        """Broj dana kasnjenja."""
        if not self.is_overdue:
            return 0
        from datetime import date
        return (date.today() - self.due_date).days

    def to_dict(self, include_items=True):
        """Pretvara u dict za API response."""
        result = {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'invoice_number': self.invoice_number,
            'period_start': self.period_start.isoformat() if self.period_start else None,
            'period_end': self.period_end.isoformat() if self.period_end else None,
            'subtotal': float(self.subtotal) if self.subtotal else 0,
            'discount_amount': float(self.discount_amount) if self.discount_amount else 0,
            'discount_reason': self.discount_reason,
            'total_amount': float(self.total_amount) if self.total_amount else 0,
            'currency': self.currency,
            'status': self.status,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'is_overdue': self.is_overdue,
            'days_overdue': self.days_overdue,
            'paid_at': self.paid_at.isoformat() if self.paid_at else None,
            'payment_method': self.payment_method,
            'payment_reference': self.payment_reference,
            'payment_proof_url': self.payment_proof_url,
            'verified_at': self.verified_at.isoformat() if self.verified_at else None,
            'verified_by_id': self.verified_by_id,
            'verified_by_name': f"{self.verified_by.ime} {self.verified_by.prezime}" if self.verified_by else None,
            'is_auto_generated': self.is_auto_generated,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            # Reconciliation info
            'reconciled_at': self.reconciled_at.isoformat() if self.reconciled_at else None,
            'reconciled_via': self.reconciled_via,
        }

        # Bank import info za PAID fakture
        if self.bank_transaction and self.bank_transaction.import_batch:
            batch = self.bank_transaction.import_batch
            result['bank_import'] = {
                'import_id': batch.id,
                'filename': batch.filename,
                'statement_date': batch.statement_date.isoformat() if batch.statement_date else None,
                'statement_number': batch.statement_number,
                'bank_code': batch.bank_code,
                'bank_name': batch.bank_name,
                'transaction_date': self.bank_transaction.transaction_date.isoformat() if self.bank_transaction.transaction_date else None,
                'payer_name': self.bank_transaction.payer_name,
            }
        else:
            result['bank_import'] = None

        if include_items:
            result['items'] = self.items_json or []
        return result

    @classmethod
    def generate_invoice_number(cls):
        """
        Generise jedinstven broj fakture.

        DEPRECATED: Koristi app.services.billing_tasks.get_next_invoice_number() direktno.
        Ova metoda je wrapper za backward compatibility.
        """
        from datetime import date
        from ..services.billing_tasks import get_next_invoice_number
        return get_next_invoice_number(date.today().year)
