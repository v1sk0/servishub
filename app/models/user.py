"""
User model - korisnici sistema (serviseri, admini, prijem).

TenantUser pripada jednom preduzecu (Tenant) i moze imati pristup
jednoj ili vise lokacija (ServiceLocation).
"""

import enum
from datetime import datetime
import bcrypt
from ..extensions import db


class UserRole(enum.Enum):
    """
    Role korisnika unutar preduzeca.

    OWNER - Vlasnik preduzeca, full access, ne moze se obrisati
    ADMIN - Admin preduzeca, skoro sve osim brisanja OWNER-a
    MANAGER - Menadzer lokacije (vidi samo svoje lokacije)
    TECHNICIAN - Serviser (radi na nalozima)
    RECEPTIONIST - Prijem (kreira naloge, prima telefone)
    """
    OWNER = 'OWNER'
    ADMIN = 'ADMIN'
    MANAGER = 'MANAGER'
    TECHNICIAN = 'TECHNICIAN'
    RECEPTIONIST = 'RECEPTIONIST'


class TipUgovora(enum.Enum):
    """Tip ugovora o radu."""
    NEODREDJENO = 'NEODREDJENO'  # Na neodređeno vreme
    ODREDJENO = 'ODREDJENO'      # Na određeno vreme


class TipPlate(enum.Enum):
    """Tip isplate plate."""
    FIKSNO = 'FIKSNO'        # Fiksna mesečna plata
    DNEVNICA = 'DNEVNICA'    # Rad na dnevnicu


class TenantUser(db.Model):
    """
    Korisnik preduzeca - zaposleni koji koristi platformu.

    Korisnik pripada tacno jednom tenantu (preduzecu) i moze imati
    pristup jednoj ili vise lokacija kroz UserLocation tabelu.
    """
    __tablename__ = 'tenant_user'

    # Primarni kljuc
    id = db.Column(db.Integer, primary_key=True)

    # Veza sa preduzecem - obavezno
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Auth podaci
    username = db.Column(db.String(50), nullable=False)  # Username za login (obavezno)
    email = db.Column(db.String(100), nullable=True)     # Email (opciono)
    password_hash = db.Column(db.String(200))            # Nullable za OAuth korisnike

    # OAuth podaci
    google_id = db.Column(db.String(100), unique=True)  # Google OAuth ID
    auth_provider = db.Column(db.String(20), default='email')  # 'email' ili 'google'

    # SMS verifikacija
    phone_verification_code = db.Column(db.String(6))   # OTP kod za SMS
    phone_verification_expires = db.Column(db.DateTime) # Kada istice OTP
    phone_verified = db.Column(db.Boolean, default=False)  # Da li je telefon verifikovan

    # Profil
    ime = db.Column(db.String(50), nullable=False)      # Ime
    prezime = db.Column(db.String(50), nullable=False)  # Prezime
    phone = db.Column(db.String(30))                    # Kontakt telefon
    adresa = db.Column(db.String(200))                  # Adresa stanovanja

    # Dokumenta
    broj_licne_karte = db.Column(db.String(20))         # Broj lične karte

    # Radni odnos
    pocetak_radnog_odnosa = db.Column(db.Date)          # Datum početka radnog odnosa
    ugovor_tip = db.Column(db.Enum(TipUgovora))         # Tip ugovora (neodređeno/određeno)
    ugovor_trajanje_meseci = db.Column(db.Integer)      # Trajanje ugovora u mesecima (za određeno)

    # Plata
    plata_tip = db.Column(db.Enum(TipPlate))            # Tip plate (fiksno/dnevnica)
    plata_iznos = db.Column(db.Numeric(12, 2))          # Iznos plate/dnevnice

    # Napomena
    napomena = db.Column(db.Text)                       # Interna napomena o zaposlenom

    # Rola u preduzecu
    role = db.Column(
        db.Enum(UserRole),
        default=UserRole.TECHNICIAN,
        nullable=False
    )

    # Status
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # Permissions
    can_view_revenue = db.Column(db.Boolean, default=False, nullable=False)  # Pregled prihoda u widgetima

    # Trenutno izabrana lokacija
    current_location_id = db.Column(
        db.Integer,
        db.ForeignKey('service_location.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    current_location = db.relationship('ServiceLocation', foreign_keys=[current_location_id])

    # Pracenje aktivnosti
    last_login_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relacije
    locations = db.relationship(
        'UserLocation',
        backref='user',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )

    # Unique constraints unutar tenanta
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'email', name='uq_tenant_user_email'),
        db.UniqueConstraint('tenant_id', 'username', name='uq_tenant_user_username'),
    )

    def __repr__(self):
        return f'<TenantUser {self.id}: {self.username}>'

    @property
    def full_name(self):
        """Puno ime korisnika."""
        return f'{self.ime} {self.prezime}'

    def set_password(self, password):
        """
        Hashira i postavlja lozinku korisnika.
        Koristi bcrypt za siguran hash.
        """
        password_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt()
        self.password_hash = bcrypt.hashpw(password_bytes, salt).decode('utf-8')

    def check_password(self, password):
        """
        Proverava da li je lozinka ispravna.
        Vraca True ako je ispravna, False inace.
        """
        password_bytes = password.encode('utf-8')
        hash_bytes = self.password_hash.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hash_bytes)

    def has_location_access(self, location_id):
        """
        Proverava da li korisnik ima pristup odredjenoj lokaciji.
        OWNER i ADMIN imaju pristup svim lokacijama.
        """
        if self.role in (UserRole.OWNER, UserRole.ADMIN):
            return True
        return self.locations.filter_by(location_id=location_id).first() is not None

    def get_accessible_location_ids(self):
        """
        Vraca listu ID-jeva lokacija kojima korisnik ima pristup.
        OWNER i ADMIN vide sve lokacije tenanta.
        """
        if self.role in (UserRole.OWNER, UserRole.ADMIN):
            # Import ovde da izbegnemo circular import
            from .tenant import ServiceLocation
            return [
                loc.id for loc in
                ServiceLocation.query.filter_by(tenant_id=self.tenant_id, is_active=True)
            ]
        return [ul.location_id for ul in self.locations.filter_by(is_active=True)]

    def update_last_login(self):
        """Azurira vreme poslednjeg logina na trenutno vreme."""
        self.last_login_at = datetime.utcnow()


class UserLocation(db.Model):
    """
    Veza korisnika sa lokacijama - many-to-many sa dodatnim podacima.

    Definise kojim lokacijama korisnik ima pristup i da li moze
    da upravlja tom lokacijom (za MANAGER rolu).
    """
    __tablename__ = 'user_location'

    # Kompozitni primarni kljuc
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant_user.id', ondelete='CASCADE'),
        primary_key=True
    )
    location_id = db.Column(
        db.Integer,
        db.ForeignKey('service_location.id', ondelete='CASCADE'),
        primary_key=True
    )

    # Dodatni podaci
    is_primary = db.Column(db.Boolean, default=False)   # Glavna lokacija korisnika
    can_manage = db.Column(db.Boolean, default=False)   # Da li moze upravljati lokacijom
    is_active = db.Column(db.Boolean, default=True)     # Da li je veza aktivna
    role_at_location = db.Column(db.String(30), nullable=True)  # Override user.role per location, NULL = inherit
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Timestamp
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relacija sa lokacijom
    location = db.relationship('ServiceLocation', backref='user_assignments')

    def __repr__(self):
        return f'<UserLocation user={self.user_id} location={self.location_id}>'
