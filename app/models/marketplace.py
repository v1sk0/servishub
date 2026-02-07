"""
Supplier Marketplace - B2B Delovi

Modeli za marketplace gde dobavljači objavljuju cenovnike,
a tenanti (servisi) mogu naručiti delove.

Workflow:
1. Dobavljač upload-uje cenovnik (CSV/Excel)
2. Tenant vidi matchove dok kreira servisni nalog
3. Tenant naruči → Dobavljač potvrdi → Krediti se skinu
4. Posle potvrde: full kontakt detalji za obe strane
5. Poruke/chat za dogovor oko preuzimanja/dostave

Naplata: 0.5 kredita kupac + 0.5 kredita dobavljač (konfiguriše se)
"""

import enum
from datetime import datetime, date
from decimal import Decimal
from ..extensions import db


# ============================================
# ENUMS
# ============================================

class PriceListStatus(enum.Enum):
    """Status cenovnika."""
    DRAFT = 'DRAFT'       # U pripremi
    ACTIVE = 'ACTIVE'     # Aktivan, vidljiv tenantima
    PAUSED = 'PAUSED'     # Pauziran (privremeno nevidljiv)
    ARCHIVED = 'ARCHIVED' # Arhiviran


class PartOrderStatus(enum.Enum):
    """Status porudžbine dela."""
    PENDING = 'PENDING'           # Tenant poslao, čeka potvrdu dobavljača
    CONFIRMED = 'CONFIRMED'       # Dobavljač potvrdio - krediti skinuti, detalji razmenjeni
    REJECTED = 'REJECTED'         # Dobavljač odbio (nema na stanju, cena se promenila)
    CANCELLED = 'CANCELLED'       # Tenant otkazao pre potvrde
    COMPLETED = 'COMPLETED'       # Roba preuzeta/isporučena
    DISPUTED = 'DISPUTED'         # Problem prijavljen


class RatingType(enum.Enum):
    """Tip ocene."""
    POSITIVE = 'POSITIVE'   # 👍 Pozitivna ocena
    NEGATIVE = 'NEGATIVE'   # 👎 Negativna ocena


# ============================================
# CENOVNICI
# ============================================

class SupplierPriceList(db.Model):
    """
    Cenovnik dobavljača.

    Dobavljač može imati više cenovnika (npr. po kategorijama).
    """
    __tablename__ = 'supplier_price_list'

    id = db.Column(db.Integer, primary_key=True)

    # Dobavljač (tenant koji je registrovan kao dobavljač)
    supplier_tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Osnovni podaci
    name = db.Column(db.String(200), nullable=False)  # "Ekrani za iPhone"
    description = db.Column(db.Text, nullable=True)
    currency = db.Column(db.String(3), default='RSD')

    # Status
    status = db.Column(
        db.Enum(PriceListStatus),
        default=PriceListStatus.DRAFT,
        nullable=False,
        index=True
    )

    # Validnost (opciono)
    valid_from = db.Column(db.Date, nullable=True)
    valid_until = db.Column(db.Date, nullable=True)

    # Statistika
    total_items = db.Column(db.Integer, default=0)
    total_orders = db.Column(db.Integer, default=0)

    # Audit
    created_by_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant_user.id', ondelete='SET NULL'),
        nullable=True
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    last_import_at = db.Column(db.DateTime, nullable=True)

    # Relacije
    items = db.relationship(
        'SupplierPriceListItem',
        backref='price_list',
        cascade='all, delete-orphan',
        lazy='dynamic'
    )
    supplier_tenant = db.relationship('Tenant', backref='price_lists')

    def __repr__(self):
        return f'<SupplierPriceList {self.id}: {self.name}>'

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'currency': self.currency,
            'status': self.status.value,
            'total_items': self.total_items,
            'total_orders': self.total_orders,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_import_at': self.last_import_at.isoformat() if self.last_import_at else None,
        }


class SupplierPriceListItem(db.Model):
    """
    Stavka u cenovniku dobavljača.

    Matchuje se sa servisnim nalozima po brand/model/part_category.
    """
    __tablename__ = 'supplier_price_list_item'

    id = db.Column(db.BigInteger, primary_key=True)
    price_list_id = db.Column(
        db.Integer,
        db.ForeignKey('supplier_price_list.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Podaci za matching
    brand = db.Column(db.String(100), nullable=False, index=True)  # Apple, Samsung
    model = db.Column(db.String(100), nullable=True, index=True)  # iPhone 12 Pro, Galaxy S21
    part_category = db.Column(db.String(50), nullable=True, index=True)  # DISPLAY, BATTERY, CAMERA
    part_name = db.Column(db.String(200), nullable=False)  # "Ekran iPhone 12 Pro OLED Original"

    # Kvalitet/tip
    quality_grade = db.Column(db.String(20), nullable=True)  # Original, OEM, AAA, AA
    is_original = db.Column(db.Boolean, default=False)

    # Cena (ovo tenant vidi)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), default='RSD')

    # Dostupnost (informativno, dobavljač potvrđuje pre finalizacije)
    in_stock = db.Column(db.Boolean, default=True)
    stock_quantity = db.Column(db.Integer, nullable=True)  # Opciono
    lead_time_days = db.Column(db.Integer, nullable=True)  # "Dostava za X dana"

    # Za pretragu - konkatenirani tekst
    search_text = db.Column(db.Text, nullable=True)  # brand + model + part_name + quality

    # Status
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    __table_args__ = (
        db.Index('ix_price_item_brand_model', 'brand', 'model'),
        db.Index('ix_price_item_active_stock', 'is_active', 'in_stock'),
    )

    def __repr__(self):
        return f'<SupplierPriceListItem {self.id}: {self.part_name}>'

    def to_public_dict(self):
        """Za prikaz tenantu - SAMO ime i cena, bez detalja o dobavljaču!"""
        return {
            'id': self.id,
            'part_name': self.part_name,
            'brand': self.brand,
            'model': self.model,
            'part_category': self.part_category,
            'quality_grade': self.quality_grade,
            'is_original': self.is_original,
            'price': float(self.price) if self.price else 0,
            'currency': self.currency,
            'in_stock': self.in_stock,
            'lead_time_days': self.lead_time_days,
            # NE uključuje: supplier info, kontakt, itd.
        }

    def to_full_dict(self):
        """Za dobavljača - svi podaci."""
        data = self.to_public_dict()
        data.update({
            'price_list_id': self.price_list_id,
            'stock_quantity': self.stock_quantity,
            'is_active': self.is_active,
            'search_text': self.search_text,
        })
        return data


# ============================================
# PORUDŽBINE
# ============================================

class PartOrderRequest(db.Model):
    """
    Porudžbina rezervnog dela iz marketplace-a.

    Tenant naručuje → Dobavljač potvrđuje → Krediti se skidaju → Razmena detalja.
    """
    __tablename__ = 'part_order_request'

    id = db.Column(db.Integer, primary_key=True)

    # Broj porudžbine: MKT-2026-00001
    order_number = db.Column(db.String(20), unique=True, nullable=False)
    order_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Ko naručuje (servis)
    buyer_tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='RESTRICT'),
        nullable=False,
        index=True
    )

    # Od koga naručuje (dobavljač)
    supplier_tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='RESTRICT'),
        nullable=False,
        index=True
    )

    # Šta naručuje
    price_list_item_id = db.Column(
        db.BigInteger,
        db.ForeignKey('supplier_price_list_item.id', ondelete='RESTRICT'),
        nullable=False
    )

    # Opciono: veza sa servisnim nalogom
    service_ticket_id = db.Column(
        db.BigInteger,
        db.ForeignKey('service_ticket.id', ondelete='SET NULL'),
        nullable=True
    )

    # Količina i cena (snapshot u trenutku narudžbine)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), default='RSD')
    total_amount = db.Column(db.Numeric(12, 2), nullable=False)

    # Status
    status = db.Column(
        db.Enum(PartOrderStatus),
        default=PartOrderStatus.PENDING,
        nullable=False,
        index=True
    )

    # Napomene
    buyer_notes = db.Column(db.Text, nullable=True)      # "Treba mi hitno"
    supplier_notes = db.Column(db.Text, nullable=True)   # "Šaljemo u sledećoj turi"
    reject_reason = db.Column(db.String(255), nullable=True)

    # Naplata kredita
    credit_charged = db.Column(db.Boolean, default=False)
    credit_amount_buyer = db.Column(db.Numeric(5, 2), nullable=True)   # 0.5 default
    credit_amount_supplier = db.Column(db.Numeric(5, 2), nullable=True)  # 0.5 default
    credit_charged_at = db.Column(db.DateTime, nullable=True)

    # Dostava
    delivery_option_id = db.Column(
        db.Integer,
        db.ForeignKey('supplier_delivery_option.id', ondelete='SET NULL'),
        nullable=True
    )
    delivery_option_name = db.Column(db.String(100), nullable=True)  # Snapshot naziva
    delivery_cost = db.Column(db.Numeric(10, 2), default=0)
    estimated_delivery_date = db.Column(db.Date, nullable=True)  # Procenjeni datum isporuke
    actual_delivery_date = db.Column(db.Date, nullable=True)  # Stvarni datum isporuke

    # Audit
    created_by_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant_user.id', ondelete='SET NULL'),
        nullable=False
    )
    confirmed_by_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant_user.id', ondelete='SET NULL'),
        nullable=True
    )
    confirmed_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacije
    buyer_tenant = db.relationship('Tenant', foreign_keys=[buyer_tenant_id], backref='marketplace_orders_as_buyer')
    supplier_tenant = db.relationship('Tenant', foreign_keys=[supplier_tenant_id], backref='marketplace_orders_as_supplier')
    price_list_item = db.relationship('SupplierPriceListItem', backref='orders')
    service_ticket = db.relationship('ServiceTicket', backref='marketplace_orders')
    messages = db.relationship(
        'PartOrderMessage',
        backref='order',
        cascade='all, delete-orphan',
        order_by='PartOrderMessage.created_at'
    )
    delivery_option = db.relationship('SupplierDeliveryOption')

    @staticmethod
    def generate_order_number() -> str:
        """Generiše sledeći broj porudžbine: MKT-2026-00001"""
        year = datetime.now().year
        prefix = f"MKT-{year}-"
        last = PartOrderRequest.query.filter(
            PartOrderRequest.order_number.like(f"{prefix}%")
        ).order_by(PartOrderRequest.order_number.desc()).first()
        next_num = 1
        if last:
            try:
                next_num = int(last.order_number.split('-')[-1]) + 1
            except ValueError:
                pass
        return f"{prefix}{next_num:05d}"

    def __repr__(self):
        return f'<PartOrderRequest {self.order_number}: {self.status.value}>'

    def to_buyer_dict(self):
        """Za kupca - prikazuje detalje dobavljača samo ako je CONFIRMED."""
        data = {
            'id': self.id,
            'order_number': self.order_number,
            'order_date': self.order_date.isoformat() if self.order_date else None,
            'status': self.status.value,
            'quantity': self.quantity,
            'unit_price': float(self.unit_price) if self.unit_price else 0,
            'total_amount': float(self.total_amount) if self.total_amount else 0,
            'currency': self.currency,
            'item': self.price_list_item.to_public_dict() if self.price_list_item else None,
            'buyer_notes': self.buyer_notes,
            'supplier_notes': self.supplier_notes,
            'messages_count': len(self.messages) if self.messages else 0,
            'delivery_option_name': self.delivery_option_name,
            'delivery_cost': float(self.delivery_cost) if self.delivery_cost else 0,
            'estimated_delivery_date': self.estimated_delivery_date.isoformat() if self.estimated_delivery_date else None,
        }

        # Prikaži detalje dobavljača SAMO nakon potvrde
        if self.status in (PartOrderStatus.CONFIRMED, PartOrderStatus.COMPLETED):
            data['supplier'] = {
                'name': self.supplier_tenant.name,
                'company_name': self.supplier_tenant.company_name if hasattr(self.supplier_tenant, 'company_name') else None,
                'address': self.supplier_tenant.address if hasattr(self.supplier_tenant, 'address') else None,
                'city': self.supplier_tenant.city if hasattr(self.supplier_tenant, 'city') else None,
                'phone': self.supplier_tenant.phone if hasattr(self.supplier_tenant, 'phone') else None,
                'email': self.supplier_tenant.email if hasattr(self.supplier_tenant, 'email') else None,
            }

        return data

    def to_supplier_dict(self):
        """Za dobavljača - prikazuje detalje kupca samo ako je CONFIRMED."""
        data = {
            'id': self.id,
            'order_number': self.order_number,
            'order_date': self.order_date.isoformat() if self.order_date else None,
            'status': self.status.value,
            'quantity': self.quantity,
            'unit_price': float(self.unit_price) if self.unit_price else 0,
            'total_amount': float(self.total_amount) if self.total_amount else 0,
            'currency': self.currency,
            'item': self.price_list_item.to_full_dict() if self.price_list_item else None,
            'buyer_notes': self.buyer_notes,
            'supplier_notes': self.supplier_notes,
            'messages_count': len(self.messages) if self.messages else 0,
        }

        # UVEK prikaži rating kupca (i pre potvrde!)
        data['buyer_rating'] = {
            'score': self.buyer_tenant.buyer_rating_score if hasattr(self.buyer_tenant, 'buyer_rating_score') else None,
            'positive': self.buyer_tenant.buyer_positive_ratings if hasattr(self.buyer_tenant, 'buyer_positive_ratings') else 0,
            'negative': self.buyer_tenant.buyer_negative_ratings if hasattr(self.buyer_tenant, 'buyer_negative_ratings') else 0,
        }

        # Prikaži kontakt detalje kupca SAMO nakon potvrde
        if self.status in (PartOrderStatus.CONFIRMED, PartOrderStatus.COMPLETED):
            data['buyer'] = {
                'name': self.buyer_tenant.name,
                'company_name': self.buyer_tenant.company_name if hasattr(self.buyer_tenant, 'company_name') else None,
                'address': self.buyer_tenant.address if hasattr(self.buyer_tenant, 'address') else None,
                'city': self.buyer_tenant.city if hasattr(self.buyer_tenant, 'city') else None,
                'phone': self.buyer_tenant.phone if hasattr(self.buyer_tenant, 'phone') else None,
                'email': self.buyer_tenant.email if hasattr(self.buyer_tenant, 'email') else None,
            }

        return data


class PartOrderMessage(db.Model):
    """Poruka vezana za porudžbinu - omogućava komunikaciju pre/posle potvrde."""
    __tablename__ = 'part_order_message'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(
        db.Integer,
        db.ForeignKey('part_order_request.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Ko šalje
    sender_tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='SET NULL'),
        nullable=False
    )
    sender_user_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant_user.id', ondelete='SET NULL'),
        nullable=True
    )

    # Poruka
    message = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(20), default='text')  # text, status_change, system

    # Read status
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relacije
    sender_tenant = db.relationship('Tenant')
    sender_user = db.relationship('TenantUser')

    def __repr__(self):
        return f'<PartOrderMessage {self.id}: order={self.order_id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'sender_tenant_id': self.sender_tenant_id,
            'message': self.message,
            'message_type': self.message_type,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ============================================
# PODEŠAVANJA
# ============================================

class MarketplaceSettings(db.Model):
    """Sistemska podešavanja za marketplace."""
    __tablename__ = 'marketplace_settings'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    updated_by_id = db.Column(db.Integer, nullable=True)

    def __repr__(self):
        return f'<MarketplaceSettings {self.key}={self.value}>'

    @staticmethod
    def get_value(key: str, default: str = None) -> str:
        """Dohvati vrednost podešavanja."""
        setting = MarketplaceSettings.query.filter_by(key=key).first()
        return setting.value if setting else default

    @staticmethod
    def get_credit_costs() -> tuple:
        """Vraća (buyer_cost, supplier_cost) kao Decimal."""
        buyer = Decimal(MarketplaceSettings.get_value('part_order_credit_buyer', '0.5'))
        supplier = Decimal(MarketplaceSettings.get_value('part_order_credit_supplier', '0.5'))
        return (buyer, supplier)


# Početne vrednosti za MarketplaceSettings:
# | key                        | value | description                          |
# |----------------------------|-------|--------------------------------------|
# | part_order_credit_buyer    | 0.5   | Krediti koji se skidaju kupcu        |
# | part_order_credit_supplier | 0.5   | Krediti koji se skidaju dobavljaču   |
# | min_credits_to_order       | 1.0   | Min kredita za kreiranje porudžbine  |


# ============================================
# OCENE
# ============================================

class MarketplaceRating(db.Model):
    """
    Obostrane ocene nakon marketplace transakcije.

    - Tenant ocenjuje dobavljača
    - Dobavljač ocenjuje tenanta
    - Ocene su javne i utiču na prikaz u rezultatima
    """
    __tablename__ = 'marketplace_rating'

    id = db.Column(db.Integer, primary_key=True)

    # Porudžbina za koju se daje ocena
    order_id = db.Column(
        db.Integer,
        db.ForeignKey('part_order_request.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Ko ocenjuje
    rater_tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    rater_user_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant_user.id', ondelete='SET NULL'),
        nullable=True
    )

    # Koga ocenjuje
    rated_tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Tip ocene: da li je ocenjivač kupac ili dobavljač
    rating_role = db.Column(db.String(20), nullable=False)  # 'buyer', 'supplier'

    # Ocena
    rating_type = db.Column(
        db.Enum(RatingType),
        nullable=False
    )

    # Komentar (opciono)
    comment = db.Column(db.Text, nullable=True)

    # Timestamp
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relacije
    order = db.relationship('PartOrderRequest', backref='ratings')
    rater_tenant = db.relationship('Tenant', foreign_keys=[rater_tenant_id])
    rated_tenant = db.relationship('Tenant', foreign_keys=[rated_tenant_id])

    __table_args__ = (
        # Jedna ocena po ulozi po porudžbini
        db.UniqueConstraint('order_id', 'rater_tenant_id', name='uq_rating_order_rater'),
    )

    def __repr__(self):
        return f'<MarketplaceRating {self.id}: {self.rating_role} {self.rating_type.value}>'

    def to_dict(self):
        return {
            'id': self.id,
            'order_number': self.order.order_number if self.order else None,
            'rating_role': self.rating_role,
            'rating_type': self.rating_type.value,
            'comment': self.comment,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ============================================
# FAVORITI
# ============================================

class TenantFavoriteSupplier(db.Model):
    """Omiljeni dobavljači tenanta - prioritet u prikazu."""
    __tablename__ = 'tenant_favorite_supplier'

    id = db.Column(db.Integer, primary_key=True)

    # Ko ima favorita
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Ko je favorit (dobavljač)
    supplier_tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Kada dodat
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant_user.id', ondelete='SET NULL'),
        nullable=True
    )

    # Relacije
    tenant = db.relationship('Tenant', foreign_keys=[tenant_id], backref='favorite_suppliers')
    supplier_tenant = db.relationship('Tenant', foreign_keys=[supplier_tenant_id])

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'supplier_tenant_id', name='uq_tenant_favorite_supplier'),
    )

    def __repr__(self):
        return f'<TenantFavoriteSupplier {self.tenant_id} -> {self.supplier_tenant_id}>'


# ============================================
# DOSTAVA
# ============================================

class SupplierDeliveryOption(db.Model):
    """Načini dostave koje nudi dobavljač."""
    __tablename__ = 'supplier_delivery_option'

    id = db.Column(db.Integer, primary_key=True)

    # Dobavljač
    supplier_tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Naziv opcije
    name = db.Column(db.String(100), nullable=False)  # "Lična dostava", "Kurirska služba", "Preuzimanje"
    description = db.Column(db.Text, nullable=True)  # Dodatni opis

    # Procenjeno vreme (u danima)
    estimated_days_min = db.Column(db.Integer, default=1)  # Minimum
    estimated_days_max = db.Column(db.Integer, default=3)  # Maximum

    # Cena dostave (opciono)
    delivery_cost = db.Column(db.Numeric(10, 2), default=0)
    currency = db.Column(db.String(3), default='RSD')

    # Uslovi
    is_free_above = db.Column(db.Numeric(10, 2), nullable=True)  # Besplatna dostava iznad X RSD
    min_order_amount = db.Column(db.Numeric(10, 2), nullable=True)  # Min iznos za ovu opciju

    # Status
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_default = db.Column(db.Boolean, default=False)  # Default opcija

    # Redosled prikaza
    sort_order = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Relacije
    supplier_tenant = db.relationship('Tenant', backref='delivery_options')

    __table_args__ = (
        db.Index('ix_delivery_supplier_active', 'supplier_tenant_id', 'is_active'),
    )

    def __repr__(self):
        return f'<SupplierDeliveryOption {self.id}: {self.name}>'

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'estimated_days': f"{self.estimated_days_min}-{self.estimated_days_max}" if self.estimated_days_min != self.estimated_days_max else str(self.estimated_days_min),
            'estimated_days_min': self.estimated_days_min,
            'estimated_days_max': self.estimated_days_max,
            'delivery_cost': float(self.delivery_cost) if self.delivery_cost else 0,
            'currency': self.currency,
            'is_free_above': float(self.is_free_above) if self.is_free_above else None,
            'min_order_amount': float(self.min_order_amount) if self.min_order_amount else None,
            'is_default': self.is_default,
            'is_active': self.is_active,
        }
