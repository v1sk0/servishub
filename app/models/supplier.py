"""
Supplier modeli - dobavljaci rezervnih delova.

Supplier - dobavljac koji nudi delove servisima
SupplierListing - artikli dobavljaca u katalogu
SupplierUser - korisnici dobavljaca
"""

import enum
from datetime import datetime
import bcrypt
from ..extensions import db


class SupplierStatus(enum.Enum):
    """Status dobavljaca."""
    PENDING = 'PENDING'      # Ceka verifikaciju
    ACTIVE = 'ACTIVE'        # Aktivan, moze da prodaje
    SUSPENDED = 'SUSPENDED'  # Suspendovan
    CANCELLED = 'CANCELLED'  # Otkazan nalog


class Supplier(db.Model):
    """
    Dobavljac rezervnih delova.

    Dobavljaci nude delove servisima kroz platformu.
    Provizija 5% na svaku prodaju.
    """
    __tablename__ = 'supplier'

    # Primarni kljuc
    id = db.Column(db.Integer, primary_key=True)

    # Osnovni podaci
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    pib = db.Column(db.String(20), unique=True)
    maticni_broj = db.Column(db.String(20))
    address = db.Column(db.String(300))
    city = db.Column(db.String(100))
    email = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(30))
    website = db.Column(db.String(200))

    # Status
    status = db.Column(
        db.Enum(SupplierStatus),
        default=SupplierStatus.PENDING,
        nullable=False,
        index=True
    )
    is_verified = db.Column(db.Boolean, default=False)
    verified_at = db.Column(db.DateTime)

    # Finansije
    commission_rate = db.Column(db.Numeric(4, 2), default=0.05)  # 5% default
    total_sales = db.Column(db.Numeric(12, 2), default=0)
    total_commission = db.Column(db.Numeric(12, 2), default=0)

    # Rejting
    rating = db.Column(db.Numeric(2, 1))  # 1-5 prosek
    rating_count = db.Column(db.Integer, default=0)

    # Valutni kurs (EUR -> RSD) po dobavljacu
    eur_rate = db.Column(db.Numeric(8, 4), default=117.5)

    # Delivery konfiguracija
    delivery_cities = db.Column(db.JSON, default=list)         # ["Beograd", "Novi Sad", "Nis"]
    delivery_rounds = db.Column(db.JSON, default=dict)          # {"weekday": [...], "saturday": [...], "sunday": []}
    courier_services_config = db.Column(db.JSON, default=list)  # ["d_express", "aks", "post_express"]
    allows_pickup = db.Column(db.Boolean, default=False)        # Licno preuzimanje
    delivery_notes = db.Column(db.Text)                         # Napomene o dostavi

    # Timestampovi
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relacije
    listings = db.relationship(
        'SupplierListing',
        backref='supplier',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    users = db.relationship(
        'SupplierUser',
        backref='supplier',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f'<Supplier {self.id}: {self.name}>'

    @property
    def is_active(self):
        """Da li dobavljac moze da prodaje."""
        return self.status == SupplierStatus.ACTIVE and self.is_verified

    def to_dict(self):
        """Konvertuje u dict za API response."""
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'city': self.city,
            'status': self.status.value,
            'is_verified': self.is_verified,
            'rating': float(self.rating) if self.rating else None,
            'rating_count': self.rating_count,
        }

    def to_anonymous_dict(self):
        """Anonimni prikaz - bez kontakt podataka."""
        return {
            'id': self.id,
            'city': self.city,
            'is_verified': self.is_verified,
            'rating': float(self.rating) if self.rating else None,
            'rating_count': self.rating_count,
            'is_revealed': False,
        }

    def to_revealed_dict(self):
        """Potpuni prikaz - sa svim kontakt podacima."""
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'city': self.city,
            'address': self.address,
            'phone': self.phone,
            'email': self.email,
            'website': self.website,
            'pib': self.pib,
            'is_verified': self.is_verified,
            'rating': float(self.rating) if self.rating else None,
            'rating_count': self.rating_count,
            'is_revealed': True,
        }


class SupplierListing(db.Model):
    """
    Artikl dobavljaca - deo u katalogu.

    Servisi mogu da pregledaju i narucuju ove delove.
    """
    __tablename__ = 'supplier_listing'

    # Primarni kljuc
    id = db.Column(db.BigInteger, primary_key=True)

    # Veza sa dobavljacem
    supplier_id = db.Column(
        db.Integer,
        db.ForeignKey('supplier.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Podaci o delu
    name = db.Column(db.String(200), nullable=False)
    brand = db.Column(db.String(50))                     # Za koji brand
    model_compatibility = db.Column(db.Text)              # JSON lista modela
    part_category = db.Column(db.String(50))
    part_number = db.Column(db.String(50))
    description = db.Column(db.Text)
    is_original = db.Column(db.Boolean, default=False)
    quality_grade = db.Column(db.String(20))

    # Cena i kolicina - dual pricing (RSD + EUR)
    price = db.Column(db.Numeric(10, 2))  # Legacy - ne koristi se vise
    currency = db.Column(db.String(3), default='RSD')  # Legacy
    price_rsd = db.Column(db.Numeric(10, 2))
    price_eur = db.Column(db.Numeric(10, 2))
    min_order_qty = db.Column(db.Integer, default=1)
    stock_quantity = db.Column(db.Integer)               # NULL = neograniceno
    stock_status = db.Column(db.String(20), default='IN_STOCK')  # IN_STOCK, LOW, OUT_OF_STOCK

    # Dostava
    delivery_days = db.Column(db.Integer)                # Procenjeni dani dostave

    # Status
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)

    # Timestampovi
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Indeksi
    __table_args__ = (
        db.Index('ix_listing_supplier_active', 'supplier_id', 'is_active'),
        db.Index('ix_listing_brand_category', 'brand', 'part_category'),
    )

    def __repr__(self):
        return f'<SupplierListing {self.id}: {self.name}>'

    def to_dict(self):
        """Konvertuje u dict za API response."""
        return {
            'id': self.id,
            'supplier_id': self.supplier_id,
            'name': self.name,
            'brand': self.brand,
            'model_compatibility': self.model_compatibility,
            'part_category': self.part_category,
            'part_number': self.part_number,
            'description': self.description,
            'is_original': self.is_original,
            'quality_grade': self.quality_grade,
            'price_rsd': float(self.price_rsd) if self.price_rsd else None,
            'price_eur': float(self.price_eur) if self.price_eur else None,
            'min_order_qty': self.min_order_qty,
            'stock_quantity': self.stock_quantity,
            'stock_status': self.stock_status,
            'delivery_days': self.delivery_days,
            'is_active': self.is_active,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class SupplierUser(db.Model):
    """
    Korisnik dobavljaca - za pristup supplier panelu.
    """
    __tablename__ = 'supplier_user'

    # Primarni kljuc
    id = db.Column(db.Integer, primary_key=True)

    # Veza sa dobavljacem
    supplier_id = db.Column(
        db.Integer,
        db.ForeignKey('supplier.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Auth
    email = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    # Profil
    ime = db.Column(db.String(50), nullable=False)
    prezime = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(30))

    # Rola
    is_admin = db.Column(db.Boolean, default=False)  # Admin dobavljaca

    # Status
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    last_login_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Unique constraint
    __table_args__ = (
        db.UniqueConstraint('supplier_id', 'email', name='uq_supplier_user_email'),
    )

    def __repr__(self):
        return f'<SupplierUser {self.id}: {self.email}>'

    @property
    def full_name(self):
        return f'{self.ime} {self.prezime}'

    def set_password(self, password):
        password_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt()
        self.password_hash = bcrypt.hashpw(password_bytes, salt).decode('utf-8')

    def check_password(self, password):
        password_bytes = password.encode('utf-8')
        hash_bytes = self.password_hash.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hash_bytes)
