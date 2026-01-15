"""
Tenant model - predstavlja preduzece (servis) u sistemu.

Tenant je glavni entitet za multi-tenancy. Svaki servis koji se registruje
dobija svoj tenant sa jednom ili vise lokacija.
"""

import enum
from datetime import datetime, timedelta
from sqlalchemy import event
from slugify import slugify
from ..extensions import db


class TenantStatus(enum.Enum):
    """
    Mogući statusi tenanta (preduzeca).

    DEMO - Automatski 7 dana nakon registracije, pun pristup
    TRIAL - 60 dana FREE, aktivira admin nakon kontakta
    ACTIVE - Aktivna pretplata
    EXPIRED - Istekla pretplata (grace period 7 dana)
    SUSPENDED - Suspendovan (neplacanje ili krsenje pravila)
    CANCELLED - Otkazan nalog
    """
    DEMO = 'DEMO'
    TRIAL = 'TRIAL'
    ACTIVE = 'ACTIVE'
    EXPIRED = 'EXPIRED'
    SUSPENDED = 'SUSPENDED'
    CANCELLED = 'CANCELLED'


class Tenant(db.Model):
    """
    Tenant - preduzece koje koristi platformu.

    Sadrzi osnovne podatke o preduzecu, status pretplate i podesavanja.
    Svaki tenant moze imati vise lokacija (ServiceLocation).
    """
    __tablename__ = 'tenant'

    # Primarni kljuc
    id = db.Column(db.Integer, primary_key=True)

    # Jedinstveni slug za URL-ove (npr. "mobilni-doktor-beograd")
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)

    # Osnovni podaci preduzeca
    name = db.Column(db.String(200), nullable=False)  # Naziv preduzeca
    pib = db.Column(db.String(20), unique=True)       # Poreski identifikacioni broj
    maticni_broj = db.Column(db.String(20))           # Maticni broj preduzeca
    adresa_sedista = db.Column(db.String(300))        # Adresa sedista (pravna)
    email = db.Column(db.String(100), nullable=False) # Kontakt email
    telefon = db.Column(db.String(30))                # Kontakt telefon
    bank_account = db.Column(db.String(50))           # Bankovni racun (XXX-XXXXXXXXX-XX)

    # Status i pretplata
    status = db.Column(
        db.Enum(TenantStatus),
        default=TenantStatus.DEMO,
        nullable=False,
        index=True
    )
    demo_ends_at = db.Column(db.DateTime)            # Kada istice demo period (7 dana)
    trial_ends_at = db.Column(db.DateTime)           # Kada istice trial period (60 dana)
    subscription_ends_at = db.Column(db.DateTime)    # Kada istice pretplata

    # Podesavanja (JSON) - warranty defaults, currency, itd.
    # Primer: {"warranty_defaults": {"phone_repair": 45}, "currency": "RSD"}
    settings_json = db.Column(db.JSON, default=dict)

    # Timestampovi
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Relacije
    locations = db.relationship(
        'ServiceLocation',
        backref='tenant',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    users = db.relationship(
        'TenantUser',
        backref='tenant',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f'<Tenant {self.id}: {self.name}>'

    @property
    def is_active(self):
        """Da li tenant ima aktivan pristup platformi (DEMO, TRIAL ili ACTIVE)."""
        return self.status in (TenantStatus.DEMO, TenantStatus.TRIAL, TenantStatus.ACTIVE)

    @property
    def default_warranty_days(self):
        """Vraca default warranty dane iz podesavanja ili globalni default."""
        settings = self.settings_json or {}
        warranty_defaults = settings.get('warranty_defaults', {})
        return warranty_defaults.get('default', 45)

    def set_demo(self, demo_days=7):
        """
        Postavlja DEMO status sa istekom.
        Poziva se automatski pri registraciji.
        """
        self.status = TenantStatus.DEMO
        self.demo_ends_at = datetime.utcnow() + timedelta(days=demo_days)

    def activate_trial(self, trial_days=60):
        """
        Aktivira trial period za tenant.
        Poziva se kada platform admin odobri nakon kontakta.
        Menja DEMO -> TRIAL.
        """
        self.status = TenantStatus.TRIAL
        self.trial_ends_at = datetime.utcnow() + timedelta(days=trial_days)

    def activate_subscription(self, months=1):
        """
        Aktivira ili produzuje pretplatu.
        """
        self.status = TenantStatus.ACTIVE
        if self.subscription_ends_at and self.subscription_ends_at > datetime.utcnow():
            # Produzenje postojece pretplate
            base_date = self.subscription_ends_at
        else:
            # Nova pretplata
            base_date = datetime.utcnow()
        self.subscription_ends_at = base_date + timedelta(days=30 * months)

    @property
    def days_remaining(self):
        """Vraca broj preostalih dana za trenutni status."""
        now = datetime.utcnow()
        if self.status == TenantStatus.DEMO and self.demo_ends_at:
            delta = self.demo_ends_at - now
            return max(0, delta.days)
        elif self.status == TenantStatus.TRIAL and self.trial_ends_at:
            delta = self.trial_ends_at - now
            return max(0, delta.days)
        elif self.status == TenantStatus.ACTIVE and self.subscription_ends_at:
            delta = self.subscription_ends_at - now
            return max(0, delta.days)
        return None


class ServiceLocation(db.Model):
    """
    Lokacija servisa - fizicka lokacija gde servis radi.

    Preduzece moze imati vise lokacija. Prva lokacija je ukljucena
    u bazni paket, svaka dodatna kosta ekstra.
    """
    __tablename__ = 'service_location'

    # Primarni kljuc
    id = db.Column(db.Integer, primary_key=True)

    # Veza sa preduzecem
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Podaci lokacije
    name = db.Column(db.String(100), nullable=False)  # "Servis Centar Zemun"
    address = db.Column(db.String(300))                # Ulica i broj
    city = db.Column(db.String(100), index=True)       # Grad
    postal_code = db.Column(db.String(20))             # Postanski broj
    phone = db.Column(db.String(30))                   # Telefon lokacije
    email = db.Column(db.String(100))                  # Email lokacije

    # Radno vreme (JSON) - {"mon": "09-17", "tue": "09-17", ...}
    working_hours_json = db.Column(db.JSON, default=dict)

    # Geografija (za B2C matching po regionu)
    latitude = db.Column(db.Float)                     # Geografska sirina
    longitude = db.Column(db.Float)                    # Geografska duzina
    coverage_radius_km = db.Column(db.Integer)         # Radius pokrivenosti u km

    # Subscription podesavanja
    is_primary = db.Column(db.Boolean, default=False)  # Prva lokacija (ukljucena u bazni)

    # Inventar podesavanje
    has_separate_inventory = db.Column(db.Boolean, default=False)  # Poseban inventar?

    # Status
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # Timestampovi
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<ServiceLocation {self.id}: {self.name}>'


# Event listener: automatski generiši slug iz naziva preduzeca
@event.listens_for(Tenant, 'before_insert')
def generate_tenant_slug(mapper, connection, target):
    """Generiše slug iz naziva preduzeca pre insert-a."""
    if not target.slug:
        base_slug = slugify(target.name, lowercase=True)
        # Proveri jedinstvenost i dodaj broj ako treba
        # TODO: Ovo treba refaktorisati da radi sa db sessionom
        target.slug = base_slug
