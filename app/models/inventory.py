"""
Inventory modeli - telefoni i rezervni delovi na lageru.

PhoneListing - telefoni za prodaju
SparePart - rezervni delovi sa visibility opcijama
"""

import enum
from datetime import datetime
from ..extensions import db


class PhoneCondition(enum.Enum):
    """Stanje telefona."""
    NEW = 'NEW'           # Nov, zapakovan
    LIKE_NEW = 'LIKE_NEW' # Kao nov, koriscen minimalno
    GOOD = 'GOOD'         # Dobro stanje, sitni tragovi
    FAIR = 'FAIR'         # Prosecno, vidljivi tragovi
    POOR = 'POOR'         # Lose, ostecenja


class PartVisibility(enum.Enum):
    """
    Vidljivost rezervnog dela.

    PRIVATE - Samo vlasnik vidi (default)
    PARTNER - Partneri mogu videti i naruciti
    PUBLIC - Svi servisi u sistemu mogu videti
    """
    PRIVATE = 'PRIVATE'
    PARTNER = 'PARTNER'
    PUBLIC = 'PUBLIC'


class PartCategory(enum.Enum):
    """Kategorije rezervnih delova."""
    DISPLAY = 'DISPLAY'           # Ekrani
    BATTERY = 'BATTERY'           # Baterije
    CHARGING_PORT = 'CHARGING_PORT'  # Portovi za punjenje
    CAMERA = 'CAMERA'             # Kamere
    SPEAKER = 'SPEAKER'           # Zvucnici
    MICROPHONE = 'MICROPHONE'     # Mikrofoni
    BUTTON = 'BUTTON'             # Dugmad
    FRAME = 'FRAME'               # Ramovi
    BACK_COVER = 'BACK_COVER'     # Zadnje maske
    MOTHERBOARD = 'MOTHERBOARD'   # Maticne ploce
    OTHER = 'OTHER'               # Ostalo


class PhoneListing(db.Model):
    """
    Telefon na lageru - za prodaju.

    Prati telefone od nabavke do prodaje i naplate.
    """
    __tablename__ = 'phone_listing'

    # Primarni kljuc
    id = db.Column(db.BigInteger, primary_key=True)

    # Veza sa preduzecem
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Lokacija gde se telefon nalazi
    location_id = db.Column(
        db.Integer,
        db.ForeignKey('service_location.id', ondelete='SET NULL'),
        nullable=True
    )

    # Podaci o telefonu
    brand = db.Column(db.String(50), nullable=False)    # Apple, Samsung, Xiaomi...
    model = db.Column(db.String(100), nullable=False)   # iPhone 14 Pro Max
    imei = db.Column(db.String(20))                      # IMEI broj
    color = db.Column(db.String(30))                     # Boja
    capacity = db.Column(db.String(20))                  # 128GB, 256GB, itd.
    condition = db.Column(
        db.Enum(PhoneCondition),
        default=PhoneCondition.GOOD,
        nullable=False
    )
    description = db.Column(db.Text)                     # Dodatni opis

    # Nabavka
    purchase_price = db.Column(db.Numeric(10, 2))        # Nabavna cena
    purchase_currency = db.Column(db.String(3), default='RSD')
    supplier_name = db.Column(db.String(100))            # Od koga je nabavljen
    supplier_contact = db.Column(db.String(100))         # Kontakt dobavljaca
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)

    # Prodaja
    sales_price = db.Column(db.Numeric(10, 2))           # Prodajna cena
    sales_currency = db.Column(db.String(3), default='RSD')
    sold = db.Column(db.Boolean, default=False, index=True)
    sold_at = db.Column(db.DateTime)
    sold_to = db.Column(db.String(100))                  # Ime kupca

    # Naplata
    collected = db.Column(db.Boolean, default=False)     # Da li je naplaceno
    collected_at = db.Column(db.DateTime)

    # Timestampovi
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relacije
    tenant = db.relationship('Tenant', backref='phones')
    location = db.relationship('ServiceLocation', backref='phones')

    # Indeksi
    __table_args__ = (
        db.Index('ix_phone_tenant_sold', 'tenant_id', 'sold'),
        db.Index('ix_phone_location_sold', 'location_id', 'sold'),
    )

    def __repr__(self):
        return f'<PhoneListing {self.id}: {self.brand} {self.model}>'

    @property
    def profit(self):
        """Profit od prodaje (ako je prodat)."""
        if self.sold and self.sales_price and self.purchase_price:
            return float(self.sales_price - self.purchase_price)
        return None

    def mark_as_sold(self, buyer_name=None, price=None):
        """Oznacava telefon kao prodat."""
        self.sold = True
        self.sold_at = datetime.utcnow()
        if buyer_name:
            self.sold_to = buyer_name
        if price:
            self.sales_price = price

    def mark_as_collected(self):
        """Oznacava telefon kao naplacen."""
        self.collected = True
        self.collected_at = datetime.utcnow()

    def to_dict(self):
        """Konvertuje u dict za API response."""
        return {
            'id': self.id,
            'brand': self.brand,
            'model': self.model,
            'imei': self.imei,
            'color': self.color,
            'capacity': self.capacity,
            'condition': self.condition.value,
            'description': self.description,
            'purchase_price': float(self.purchase_price) if self.purchase_price else None,
            'purchase_currency': self.purchase_currency,
            'sales_price': float(self.sales_price) if self.sales_price else None,
            'sales_currency': self.sales_currency,
            'sold': self.sold,
            'sold_at': self.sold_at.isoformat() if self.sold_at else None,
            'collected': self.collected,
            'profit': self.profit,
            'created_at': self.created_at.isoformat(),
        }


class SparePart(db.Model):
    """
    Rezervni deo na lageru.

    Delovi mogu biti PRIVATE (samo za vlasnika), PARTNER (deljeni sa
    partnerskim servisima) ili PUBLIC (vidljivi svim servisima).
    """
    __tablename__ = 'spare_part'

    # Primarni kljuc
    id = db.Column(db.BigInteger, primary_key=True)

    # Veza sa preduzecem
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Lokacija (NULL = deljeni inventar za celo preduzece)
    location_id = db.Column(
        db.Integer,
        db.ForeignKey('service_location.id', ondelete='SET NULL'),
        nullable=True
    )

    # Podaci o delu
    brand = db.Column(db.String(50))                     # Za koji brand uredjaja
    model = db.Column(db.String(100))                    # Za koji model uredjaja
    part_name = db.Column(db.String(100), nullable=False)  # Naziv dela
    part_category = db.Column(
        db.Enum(PartCategory),
        default=PartCategory.OTHER,
        nullable=False
    )
    part_number = db.Column(db.String(50))               # SKU/Part number
    description = db.Column(db.Text)
    is_original = db.Column(db.Boolean, default=False)   # Original ili aftermarket
    quality_grade = db.Column(db.String(20))             # AAA, AA, A, OEM, Original

    # Kolicina
    quantity = db.Column(db.Integer, default=0, nullable=False)
    min_stock_level = db.Column(db.Integer, default=0)   # Alert kad padne ispod

    # Cene
    purchase_price = db.Column(db.Numeric(10, 2))        # Nabavna cena
    selling_price = db.Column(db.Numeric(10, 2))         # Prodajna cena (za nase naloge)
    public_price = db.Column(db.Numeric(10, 2))          # Cena za partnere/javnost
    currency = db.Column(db.String(3), default='RSD')

    # Vidljivost
    visibility = db.Column(
        db.Enum(PartVisibility),
        default=PartVisibility.PRIVATE,
        nullable=False,
        index=True
    )

    # Status
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # Timestampovi
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relacije
    tenant = db.relationship('Tenant', backref='spare_parts')
    location = db.relationship('ServiceLocation', backref='spare_parts')

    # Indeksi
    __table_args__ = (
        db.Index('ix_part_tenant_visibility', 'tenant_id', 'visibility'),
        db.Index('ix_part_brand_model', 'brand', 'model'),
        db.Index('ix_part_visibility_category', 'visibility', 'part_category'),
    )

    def __repr__(self):
        return f'<SparePart {self.id}: {self.part_name}>'

    @property
    def is_low_stock(self):
        """Da li je kolicina ispod minimalnog nivoa."""
        return self.quantity <= self.min_stock_level

    @property
    def is_out_of_stock(self):
        """Da li je nestalo na stanju."""
        return self.quantity <= 0

    def adjust_quantity(self, delta):
        """
        Menja kolicinu za delta (pozitivno = dodaj, negativno = oduzmi).
        Vraca True ako je uspesno, False ako nema dovoljno.
        """
        new_qty = self.quantity + delta
        if new_qty < 0:
            return False
        self.quantity = new_qty
        return True

    def to_dict(self, include_prices=True):
        """Konvertuje u dict za API response."""
        data = {
            'id': self.id,
            'brand': self.brand,
            'model': self.model,
            'part_name': self.part_name,
            'part_category': self.part_category.value,
            'part_number': self.part_number,
            'description': self.description,
            'is_original': self.is_original,
            'quality_grade': self.quality_grade,
            'quantity': self.quantity,
            'is_low_stock': self.is_low_stock,
            'is_out_of_stock': self.is_out_of_stock,
            'visibility': self.visibility.value,
            'is_active': self.is_active,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

        if include_prices:
            data['selling_price'] = float(self.selling_price) if self.selling_price else None
            data['public_price'] = float(self.public_price) if self.public_price else None
            data['currency'] = self.currency

        return data


class StockActionType(enum.Enum):
    """Tip akcije nad zalihom."""
    CREATE = 'CREATE'
    UPDATE = 'UPDATE'
    DELETE = 'DELETE'
    RECEIVE = 'RECEIVE'
    USE_TICKET = 'USE_TICKET'
    RETURN = 'RETURN'
    ADJUST = 'ADJUST'
    DAMAGE = 'DAMAGE'
    TRANSFER = 'TRANSFER'


class SparePartUsage(db.Model):
    """Utrošeni deo na servisnom nalogu."""
    __tablename__ = 'spare_part_usage'

    id = db.Column(db.BigInteger, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    service_ticket_id = db.Column(
        db.BigInteger,
        db.ForeignKey('service_ticket.id', ondelete='CASCADE'),
        nullable=False
    )
    spare_part_id = db.Column(
        db.BigInteger,
        db.ForeignKey('spare_part.id', ondelete='RESTRICT'),
        nullable=False
    )
    quantity_used = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Numeric(10, 2))
    currency = db.Column(db.String(3), default='RSD')
    added_by_id = db.Column(db.Integer, db.ForeignKey('tenant_user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relacije
    tenant = db.relationship('Tenant')
    ticket = db.relationship('ServiceTicket', backref='used_parts')
    spare_part = db.relationship('SparePart')
    added_by = db.relationship('TenantUser')

    __table_args__ = (
        db.UniqueConstraint('service_ticket_id', 'spare_part_id', name='uq_usage_ticket_part'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'spare_part_id': self.spare_part_id,
            'part_name': self.spare_part.part_name if self.spare_part else None,
            'quantity_used': self.quantity_used,
            'unit_price': float(self.unit_price) if self.unit_price else None,
            'currency': self.currency,
            'total': float(self.unit_price * self.quantity_used) if self.unit_price else None,
            'created_at': self.created_at.isoformat(),
        }


class SparePartLog(db.Model):
    """Audit trail za promene zaliha."""
    __tablename__ = 'spare_part_log'

    id = db.Column(db.BigInteger, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    spare_part_id = db.Column(
        db.BigInteger,
        db.ForeignKey('spare_part.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    action_type = db.Column(db.Enum(StockActionType), nullable=False)
    quantity_before = db.Column(db.Integer, nullable=False)
    quantity_after = db.Column(db.Integer, nullable=False)
    quantity_change = db.Column(db.Integer, nullable=False)
    description = db.Column(db.String(255))
    reference_type = db.Column(db.String(50))  # 'ticket', 'pos_receipt', etc.
    reference_id = db.Column(db.BigInteger)
    user_id = db.Column(db.Integer, db.ForeignKey('tenant_user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relacije
    spare_part = db.relationship('SparePart', backref='stock_logs')
    user = db.relationship('TenantUser')

    __table_args__ = (
        db.Index('ix_part_log_part_created', 'spare_part_id', 'created_at'),
    )
