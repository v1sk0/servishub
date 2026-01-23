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
    grad = db.Column(db.String(100))                  # Grad sedista
    postanski_broj = db.Column(db.String(10))         # Postanski broj
    latitude = db.Column(db.Float)                    # Geografska sirina sedista
    longitude = db.Column(db.Float)                   # Geografska duzina sedista
    email = db.Column(db.String(100), nullable=False) # Kontakt email
    telefon = db.Column(db.String(30))                # Kontakt telefon
    bank_account = db.Column(db.String(50))           # Bankovni racun (XXX-XXXXXXXXX-XX)

    # Login za zaposlene - tajni URL segment
    login_secret = db.Column(db.String(32), unique=True, nullable=False)  # Tajni kod za login stranicu

    # Status i pretplata
    status = db.Column(
        db.Enum(TenantStatus),
        default=TenantStatus.TRIAL,
        nullable=False,
        index=True
    )
    demo_ends_at = db.Column(db.DateTime)            # DEPRECATED - koristimo trial_ends_at
    trial_ends_at = db.Column(db.DateTime)           # Kada istice trial period (60 dana)
    subscription_ends_at = db.Column(db.DateTime)    # Kada istice pretplata

    # ============================================
    # BILLING - Dugovanje i placanje
    # ============================================
    current_debt = db.Column(db.Numeric(10, 2), default=0)  # Trenutno dugovanje u RSD
    last_payment_at = db.Column(db.DateTime)                 # Poslednja uspesna uplata
    days_overdue = db.Column(db.Integer, default=0)          # Broj dana kasnjenja

    # ============================================
    # BLOKADA
    # ============================================
    blocked_at = db.Column(db.DateTime)              # Kada je blokiran
    block_reason = db.Column(db.String(200))         # Razlog blokade

    # ============================================
    # TRUST SCORE - Sistem poverenja
    # ============================================
    trust_score = db.Column(db.Integer, default=100)           # 0-100, visi = bolji
    trust_activated_at = db.Column(db.DateTime)                # Kada je aktivirao "na rec"
    trust_activation_count = db.Column(db.Integer, default=0)  # Ukupan broj aktivacija
    last_trust_activation_period = db.Column(db.String(7))     # "2026-01" - mesec poslednje aktivacije
    consecutive_on_time_payments = db.Column(db.Integer, default=0)  # Uzastopne uplate na vreme

    # ============================================
    # CUSTOM CENE - Popusti po servisu
    # ============================================
    custom_base_price = db.Column(db.Numeric(10, 2))           # NULL = koristi platformsku cenu
    custom_location_price = db.Column(db.Numeric(10, 2))       # NULL = koristi platformsku cenu
    custom_price_reason = db.Column(db.String(200))            # Razlog za custom cenu
    custom_price_valid_from = db.Column(db.Date)               # Od kad vazi custom cena

    # Podesavanja (JSON) - warranty defaults, currency, itd.
    # Primer: {"warranty_defaults": {"phone_repair": 45}, "currency": "RSD"}
    settings_json = db.Column(db.JSON, default=dict)

    # ============================================
    # PRINT SETTINGS - Podešavanja za štampu
    # ============================================
    print_clause = db.Column(
        db.Text,
        default='Predajom uređaja u servis prihvatam da sam odgovoran za svoje podatke i backup; '
                'servis ne odgovara za gubitak podataka, kartica i opreme, niti za kvar uređaja koji je posledica '
                'prethodnih oštećenja, vlage ili samog otvaranja uređaja, kao ni za gubitak vodootpornosti. '
                'Korisnik se obavezuje da preuzme uređaj najkasnije u roku od 30 dana od obaveštenja da je uređaj '
                'spreman za preuzimanje. Nakon isteka tog roka, servis ima pravo da obračuna naknadu za čuvanje uređaja, '
                'a dalje postupanje sa uređajem vršiće se u skladu sa važećim propisima. Garancija važi od datuma završetka popravke. '
                'Servis ne odgovara za ranije prisutna estetska oštećenja (ogrebotine, udubljenja, naprsline) koja su evidentirana '
                'pri prijemu uređaja ili su usled prljavštine i oštećenja bila prikrivena. U slučaju da popravka nije moguća ili '
                'korisnik odustane nakon postavljene ponude, servis ima pravo da naplati izvršenu dijagnostiku u iznosu od 2000 RSD.'
    )

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
        """Da li tenant ima aktivan pristup platformi (TRIAL ili ACTIVE)."""
        return self.status in (TenantStatus.TRIAL, TenantStatus.ACTIVE)

    @property
    def default_warranty_days(self):
        """Vraca default warranty dane iz podesavanja ili globalni default."""
        settings = self.settings_json or {}
        warranty_defaults = settings.get('warranty_defaults', {})
        return warranty_defaults.get('default', 45)

    def set_trial(self, trial_days=60):
        """
        Postavlja TRIAL status sa istekom.
        Poziva se automatski pri registraciji - 60 dana besplatno.
        """
        self.status = TenantStatus.TRIAL
        self.trial_ends_at = datetime.utcnow() + timedelta(days=trial_days)

    # DEPRECATED - koristimo set_trial
    def set_demo(self, demo_days=7):
        """DEPRECATED: Koristi set_trial() umesto toga."""
        self.set_trial(trial_days=60)

    def activate_trial(self, trial_days=60):
        """
        Aktivira/produzuje trial period za tenant.
        Moze se koristiti i za produljivanje trial-a od strane admina.
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
        if self.status == TenantStatus.TRIAL and self.trial_ends_at:
            delta = self.trial_ends_at - now
            return max(0, delta.days)
        elif self.status == TenantStatus.ACTIVE and self.subscription_ends_at:
            delta = self.subscription_ends_at - now
            return max(0, delta.days)
        return None

    # ============================================
    # BILLING PROPERTIES I METODE
    # ============================================

    @property
    def has_debt(self):
        """Da li ima dugovanje."""
        return self.current_debt and float(self.current_debt) > 0

    @property
    def is_blocked(self):
        """Da li je blokiran (SUSPENDED sa dugom)."""
        return self.status == TenantStatus.SUSPENDED and self.has_debt

    @property
    def trust_level(self):
        """Vraca nivo poverenja kao string."""
        if self.trust_score >= 80:
            return 'EXCELLENT'
        elif self.trust_score >= 60:
            return 'GOOD'
        elif self.trust_score >= 40:
            return 'WARNING'
        elif self.trust_score >= 20:
            return 'RISKY'
        else:
            return 'CRITICAL'

    @property
    def can_activate_trust(self):
        """Da li moze da aktivira 'na rec' (samo iz SUSPENDED, 1x mesecno)."""
        if self.status != TenantStatus.SUSPENDED:
            return False

        # Proveri da li je vec koristio ovaj mesec
        current_period = datetime.utcnow().strftime('%Y-%m')
        if self.last_trust_activation_period == current_period:
            return False

        return True

    @property
    def is_trust_active(self):
        """Da li je trenutno aktivan 'na rec' period (48h)."""
        if not self.trust_activated_at:
            return False
        elapsed = datetime.utcnow() - self.trust_activated_at
        return elapsed.total_seconds() < 48 * 3600  # 48 sati

    @property
    def trust_hours_remaining(self):
        """Preostalo sati za 'na rec' period."""
        if not self.is_trust_active:
            return 0
        elapsed = datetime.utcnow() - self.trust_activated_at
        remaining_seconds = (48 * 3600) - elapsed.total_seconds()
        return max(0, int(remaining_seconds / 3600))

    def activate_trust(self):
        """
        Aktivira 'ukljucenje na rec' za 48h.
        NAPOMENA: Pozivalac mora proveriti can_activate_trust pre poziva!
        """
        self.trust_activated_at = datetime.utcnow()
        self.trust_activation_count = (self.trust_activation_count or 0) + 1
        self.last_trust_activation_period = datetime.utcnow().strftime('%Y-%m')
        # Status ostaje SUSPENDED, ali is_trust_active postaje True

    def update_trust_score(self, change, reason=None):
        """
        Azurira trust score sa ogranicenjem 0-100.

        Args:
            change: Promena (+10, -30, itd.)
            reason: Razlog promene (za log)
        """
        new_score = (self.trust_score or 100) + change
        self.trust_score = max(0, min(100, new_score))

    def block(self, reason):
        """Blokira servis zbog neplacanja."""
        self.status = TenantStatus.SUSPENDED
        self.blocked_at = datetime.utcnow()
        self.block_reason = reason

    def unblock(self):
        """Deblokira servis (obicno nakon placanja)."""
        self.status = TenantStatus.ACTIVE
        self.blocked_at = None
        self.block_reason = None
        self.trust_activated_at = None
        self.days_overdue = 0

    def get_subscription_info(self):
        """Vraca kompletan info o pretplati za API/UI."""
        return {
            'status': self.status.value,
            'days_remaining': self.days_remaining,
            'current_debt': float(self.current_debt) if self.current_debt else 0,
            'days_overdue': self.days_overdue or 0,
            'has_debt': self.has_debt,
            'is_blocked': self.is_blocked,
            'blocked_at': self.blocked_at.isoformat() if self.blocked_at else None,
            'block_reason': self.block_reason,
            'trust_score': self.trust_score or 100,
            'trust_level': self.trust_level,
            'can_activate_trust': self.can_activate_trust,
            'is_trust_active': self.is_trust_active,
            'trust_hours_remaining': self.trust_hours_remaining,
            'expires_at': self._get_expiry_date(),
            'custom_pricing': self._get_custom_pricing()
        }

    def _get_expiry_date(self):
        """Vraca datum isteka za trenutni status."""
        if self.status == TenantStatus.TRIAL and self.trial_ends_at:
            return self.trial_ends_at.isoformat()
        elif self.status == TenantStatus.ACTIVE and self.subscription_ends_at:
            return self.subscription_ends_at.isoformat()
        return None

    def _get_custom_pricing(self):
        """Vraca custom cene ako postoje."""
        if not self.custom_base_price and not self.custom_location_price:
            return None
        return {
            'base_price': float(self.custom_base_price) if self.custom_base_price else None,
            'location_price': float(self.custom_location_price) if self.custom_location_price else None,
            'reason': self.custom_price_reason,
            'valid_from': self.custom_price_valid_from.isoformat() if self.custom_price_valid_from else None
        }


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


# Event listener: automatski generiši slug i login_secret
@event.listens_for(Tenant, 'before_insert')
def generate_tenant_defaults(mapper, connection, target):
    """Generiše slug i login_secret pre insert-a."""
    import secrets as sec

    # Generiši slug iz naziva
    if not target.slug:
        base_slug = slugify(target.name, lowercase=True)
        # Proveri jedinstvenost i dodaj broj ako treba
        # TODO: Ovo treba refaktorisati da radi sa db sessionom
        target.slug = base_slug

    # Generiši login_secret (tajni URL za prijavu zaposlenih)
    if not target.login_secret:
        target.login_secret = sec.token_urlsafe(16)  # 22 karaktera
