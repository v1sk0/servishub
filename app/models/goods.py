"""
Goods & Purchase Invoice modeli — magacin i ulazne fakture.

GoodsItem - artikl robe za maloprodaju
PurchaseInvoice - ulazna faktura od dobavljača
PurchaseInvoiceItem - stavka ulazne fakture
StockAdjustment - korekcija stanja (otpis, inventura, oštećenje)
PosAuditLog - audit trail za POS operacije
"""

import enum
import math
from datetime import datetime
from decimal import Decimal
from ..extensions import db


# ============================================
# ENUMS
# ============================================

class InvoiceStatus(enum.Enum):
    """Status ulazne fakture."""
    DRAFT = 'DRAFT'
    RECEIVED = 'RECEIVED'
    CANCELLED = 'CANCELLED'


class StockAdjustmentType(enum.Enum):
    """Tip korekcije stanja."""
    WRITE_OFF = 'WRITE_OFF'              # Otpis
    CORRECTION = 'CORRECTION'            # Korekcija (inventura)
    DAMAGE = 'DAMAGE'                    # Oštećenje
    RETURN_TO_SUPPLIER = 'RETURN_TO_SUPPLIER'  # Povrat dobavljaču


class SupplierType(enum.Enum):
    """Tip dobavljača."""
    COMPANY = 'COMPANY'       # Pravno lice (firma)
    INDIVIDUAL = 'INDIVIDUAL' # Fizičko lice


class BuybackStatus(enum.Enum):
    """Status otkupnog ugovora."""
    DRAFT = 'DRAFT'         # U pripremi
    SIGNED = 'SIGNED'       # Potpisan, roba primljena
    PAID = 'PAID'           # Isplaćeno prodavcu
    CANCELLED = 'CANCELLED' # Otkazano


# ============================================
# MODELI
# ============================================

class GoodsItem(db.Model):
    """
    Artikl robe za maloprodaju.

    Odvojeno od SparePart — roba se prodaje na kasi, delovi idu u servis.
    """
    __tablename__ = 'goods_item'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    location_id = db.Column(
        db.Integer,
        db.ForeignKey('service_location.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )

    # Osnovni podaci
    name = db.Column(db.String(300), nullable=False)
    barcode = db.Column(db.String(50), nullable=True)
    sku = db.Column(db.String(50), nullable=True)
    category = db.Column(db.String(100), nullable=True)
    description = db.Column(db.Text, nullable=True)

    # Cene i marža
    purchase_price = db.Column(db.Numeric(10, 2), default=0)
    selling_price = db.Column(db.Numeric(10, 2), default=0)
    default_margin_pct = db.Column(db.Numeric(5, 2), nullable=True)
    currency = db.Column(db.String(3), default='RSD')

    # Stanje
    current_stock = db.Column(db.Integer, default=0, nullable=False)
    min_stock_level = db.Column(db.Integer, default=0)

    # Fiskalno
    tax_label = db.Column(db.String(1), default='A')  # A=20%, B=10%, C=0%
    unit_of_measure = db.Column(db.String(20), default='kom')

    # Status
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'barcode', name='uq_goods_tenant_barcode'),
    )

    @property
    def is_low_stock(self):
        return self.current_stock <= self.min_stock_level

    @property
    def is_out_of_stock(self):
        return self.current_stock <= 0

    @property
    def margin_pct(self):
        """Izračunata marža na osnovu trenutnih cena."""
        if self.purchase_price and self.purchase_price > 0 and self.selling_price:
            return float((self.selling_price - self.purchase_price) / self.purchase_price * 100)
        return 0

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'barcode': self.barcode,
            'sku': self.sku,
            'category': self.category,
            'purchase_price': float(self.purchase_price or 0),
            'selling_price': float(self.selling_price or 0),
            'default_margin_pct': float(self.default_margin_pct or 0),
            'current_stock': self.current_stock,
            'min_stock_level': self.min_stock_level,
            'tax_label': self.tax_label,
            'unit_of_measure': self.unit_of_measure,
            'is_active': self.is_active,
            'is_low_stock': self.is_low_stock,
            'currency': self.currency,
        }

    def __repr__(self):
        return f'<GoodsItem {self.id}: {self.name} stock={self.current_stock}>'


class PurchaseInvoice(db.Model):
    """
    Ulazna faktura od dobavljača.

    Svaki prijem robe se evidentira kroz fakturu.
    """
    __tablename__ = 'purchase_invoice'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    location_id = db.Column(
        db.Integer,
        db.ForeignKey('service_location.id', ondelete='SET NULL'),
        nullable=True
    )

    # Dobavljač
    supplier_name = db.Column(db.String(200), nullable=False)
    supplier_pib = db.Column(db.String(20), nullable=True)
    supplier_id = db.Column(
        db.Integer,
        db.ForeignKey('simple_supplier.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    invoice_number = db.Column(db.String(100), nullable=False)

    # Datumi
    invoice_date = db.Column(db.Date, nullable=False)
    received_date = db.Column(db.Date, nullable=True)

    # Iznosi
    total_amount = db.Column(db.Numeric(12, 2), default=0)
    currency = db.Column(db.String(3), default='RSD')
    notes = db.Column(db.Text, nullable=True)

    # Ko je primio
    received_by_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant_user.id', ondelete='SET NULL'),
        nullable=True
    )

    # Status
    status = db.Column(
        db.Enum(InvoiceStatus),
        default=InvoiceStatus.DRAFT,
        nullable=False
    )

    # Timestamp
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relacije
    items = db.relationship(
        'PurchaseInvoiceItem',
        backref='invoice',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f'<PurchaseInvoice {self.id}: {self.supplier_name} #{self.invoice_number}>'


class PurchaseInvoiceItem(db.Model):
    """Stavka ulazne fakture."""
    __tablename__ = 'purchase_invoice_item'

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(
        db.Integer,
        db.ForeignKey('purchase_invoice.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Šta je primljeno (jedno od dva)
    goods_item_id = db.Column(
        db.Integer,
        db.ForeignKey('goods_item.id', ondelete='SET NULL'),
        nullable=True
    )
    spare_part_id = db.Column(
        db.BigInteger,
        db.ForeignKey('spare_part.id', ondelete='SET NULL'),
        nullable=True
    )

    # Podaci sa fakture
    item_name = db.Column(db.String(300), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    purchase_price = db.Column(db.Numeric(10, 2), nullable=False)
    selling_price = db.Column(db.Numeric(10, 2), nullable=True)
    margin_pct = db.Column(db.Numeric(5, 2), nullable=True)
    line_total = db.Column(db.Numeric(12, 2), nullable=False)

    def __repr__(self):
        return f'<PurchaseInvoiceItem {self.id}: {self.item_name} x{self.quantity}>'


class StockAdjustment(db.Model):
    """
    Korekcija stanja — otpis, inventura, oštećenje, povrat dobavljaču.
    """
    __tablename__ = 'stock_adjustment'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Šta se koriguje (jedno od dva)
    goods_item_id = db.Column(
        db.Integer,
        db.ForeignKey('goods_item.id', ondelete='SET NULL'),
        nullable=True
    )
    spare_part_id = db.Column(
        db.BigInteger,
        db.ForeignKey('spare_part.id', ondelete='SET NULL'),
        nullable=True
    )

    # Korekcija
    adjustment_type = db.Column(db.Enum(StockAdjustmentType), nullable=False)
    quantity_change = db.Column(db.Integer, nullable=False)
    stock_before = db.Column(db.Integer, nullable=False)
    stock_after = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(500), nullable=True)

    # Ko je korigovao
    adjusted_by_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant_user.id', ondelete='SET NULL'),
        nullable=True
    )

    # Timestamp
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<StockAdjustment {self.id}: {self.adjustment_type.value} {self.quantity_change:+d}>'


class PosAuditLog(db.Model):
    """
    Audit trail za POS operacije.

    Beleži: otvaranje/zatvaranje kase, izdavanje/storno/refund računa,
    price override, stock korekcije.
    """
    __tablename__ = 'pos_audit_log'

    id = db.Column(db.BigInteger, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant_user.id', ondelete='SET NULL'),
        nullable=True
    )

    # Akcija
    action = db.Column(db.String(50), nullable=False, index=True)
    # Vrednosti: OPEN_REGISTER, CLOSE_REGISTER, ISSUE_RECEIPT,
    #            VOID_RECEIPT, REFUND, PRICE_OVERRIDE, STOCK_ADJUST

    # Entitet
    entity_type = db.Column(db.String(50), nullable=False)
    entity_id = db.Column(db.BigInteger, nullable=True)

    # Detalji
    details_json = db.Column(db.JSON, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)

    # Timestamp
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    @classmethod
    def log_action(cls, tenant_id, user_id, action, entity_type, entity_id=None,
                   details=None, ip_address=None):
        """Helper za kreiranje audit log zapisa."""
        log = cls(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details_json=details,
            ip_address=ip_address,
        )
        db.session.add(log)
        return log

    def __repr__(self):
        return f'<PosAuditLog {self.id}: {self.action} {self.entity_type}#{self.entity_id}>'


class SimpleSupplier(db.Model):
    """
    Jednostavan dobavljač za prijem robe.

    Razlika od Supplier modela (marketplace):
    - Ovaj je za interne ulazne fakture i otkup
    - Nema commission, ratings, listings
    """
    __tablename__ = 'simple_supplier'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Tip dobavljača
    supplier_type = db.Column(
        db.Enum(SupplierType),
        nullable=False,
        default=SupplierType.COMPANY
    )

    # Osnovni podaci (oba tipa)
    name = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(50))
    email = db.Column(db.String(100))
    address = db.Column(db.Text)
    city = db.Column(db.String(100))

    # Za COMPANY (pravno lice)
    company_name = db.Column(db.String(200))  # Pun pravni naziv
    pib = db.Column(db.String(20))            # PIB (9 cifara)
    maticni_broj = db.Column(db.String(20))   # Matični broj (8 cifara)
    bank_account = db.Column(db.String(50))   # Žiro račun

    # Za INDIVIDUAL (fizičko lice)
    jmbg = db.Column(db.String(13))           # JMBG (13 cifara)
    id_card_number = db.Column(db.String(20)) # Broj lične karte
    id_card_issued_by = db.Column(db.String(100))  # Izdata od (MUP)
    id_card_issue_date = db.Column(db.Date)   # Datum izdavanja

    # Status
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Relacije
    tenant = db.relationship('Tenant', backref='simple_suppliers')

    __table_args__ = (
        db.Index('ix_simple_supplier_tenant_type', 'tenant_id', 'supplier_type'),
    )

    def __repr__(self):
        return f'<SimpleSupplier {self.id}: {self.name}>'

    def to_dict(self):
        data = {
            'id': self.id,
            'supplier_type': self.supplier_type.value,
            'name': self.name,
            'phone': self.phone,
            'email': self.email,
            'address': self.address,
            'city': self.city,
            'is_active': self.is_active,
        }
        if self.supplier_type == SupplierType.COMPANY:
            data.update({
                'company_name': self.company_name,
                'pib': self.pib,
                'maticni_broj': self.maticni_broj,
                'bank_account': self.bank_account,
            })
        else:
            data.update({
                'jmbg': self.jmbg,
                'id_card_number': self.id_card_number,
            })
        return data


class BuybackContract(db.Model):
    """
    Otkupni ugovor za fizička lica.

    Po zakonu RS otkupni ugovor mora sadržati:
    - Podatke o kupcu (firma koja otkupljuje)
    - Podatke o prodavcu (fizičko lice) - ime, JMBG, LK, adresa
    - Opis robe/artikala
    - Cenu
    - Datum i mesto
    - Potpise obe strane
    """
    __tablename__ = 'buyback_contract'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    location_id = db.Column(
        db.Integer,
        db.ForeignKey('service_location.id', ondelete='SET NULL'),
        nullable=True
    )

    # Broj ugovora: OTK-2026-00001
    contract_number = db.Column(db.String(20), unique=True, nullable=False)
    contract_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)

    # Podaci o prodavcu (fizičko lice)
    seller_name = db.Column(db.String(200), nullable=False)
    seller_jmbg = db.Column(db.String(13), nullable=False)
    seller_id_card = db.Column(db.String(20), nullable=False)
    seller_id_issued_by = db.Column(db.String(100))
    seller_address = db.Column(db.Text, nullable=False)
    seller_city = db.Column(db.String(100))
    seller_phone = db.Column(db.String(50))

    # Opciono - veza ka SimpleSupplier za ponovne otkupe
    supplier_id = db.Column(db.Integer, db.ForeignKey('simple_supplier.id'))

    # Ukupan iznos
    total_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    currency = db.Column(db.String(3), default='RSD')

    # Način isplate
    payment_method = db.Column(db.String(20), default='CASH')  # CASH, BANK_TRANSFER
    bank_account = db.Column(db.String(50))  # Ako je BANK_TRANSFER

    # Status workflow
    status = db.Column(
        db.Enum(BuybackStatus),
        default=BuybackStatus.DRAFT,
        nullable=False,
        index=True
    )

    # Datumi promene statusa
    signed_at = db.Column(db.DateTime)
    paid_at = db.Column(db.DateTime)
    cancelled_at = db.Column(db.DateTime)
    cancel_reason = db.Column(db.String(255))

    # Audit
    created_by_id = db.Column(db.Integer, db.ForeignKey('tenant_user.id'), nullable=False)
    signed_by_id = db.Column(db.Integer, db.ForeignKey('tenant_user.id'))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Napomena
    notes = db.Column(db.Text)

    # Relacije
    tenant = db.relationship('Tenant', backref='buyback_contracts')
    location = db.relationship('ServiceLocation')
    supplier = db.relationship('SimpleSupplier')
    created_by = db.relationship('TenantUser', foreign_keys=[created_by_id])
    signed_by = db.relationship('TenantUser', foreign_keys=[signed_by_id])
    items = db.relationship(
        'BuybackContractItem',
        backref='contract',
        cascade='all, delete-orphan',
        lazy='dynamic'
    )

    def __repr__(self):
        return f'<BuybackContract {self.contract_number}>'

    @staticmethod
    def generate_contract_number(tenant_id: int) -> str:
        """Generiše sledeći broj ugovora: OTK-2026-00001"""
        year = datetime.now().year
        prefix = f"OTK-{year}-"

        last = BuybackContract.query.filter(
            BuybackContract.tenant_id == tenant_id,
            BuybackContract.contract_number.like(f"{prefix}%")
        ).order_by(BuybackContract.contract_number.desc()).first()

        next_num = 1
        if last:
            try:
                next_num = int(last.contract_number.split('-')[-1]) + 1
            except ValueError:
                pass
        return f"{prefix}{next_num:05d}"

    def to_dict(self):
        return {
            'id': self.id,
            'contract_number': self.contract_number,
            'contract_date': self.contract_date.isoformat() if self.contract_date else None,
            'seller_name': self.seller_name,
            'seller_jmbg': self.seller_jmbg,
            'seller_id_card': self.seller_id_card,
            'seller_address': self.seller_address,
            'seller_phone': self.seller_phone,
            'total_amount': float(self.total_amount) if self.total_amount else 0,
            'currency': self.currency,
            'payment_method': self.payment_method,
            'status': self.status.value,
            'items_count': self.items.count(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class BuybackContractItem(db.Model):
    """Stavka otkupnog ugovora."""
    __tablename__ = 'buyback_contract_item'

    id = db.Column(db.Integer, primary_key=True)
    contract_id = db.Column(
        db.Integer,
        db.ForeignKey('buyback_contract.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Opis artikla
    item_description = db.Column(db.String(300), nullable=False)
    brand = db.Column(db.String(100))
    model = db.Column(db.String(100))

    # Identifikatori (opciono)
    imei = db.Column(db.String(20))
    serial_number = db.Column(db.String(50))

    # Količina i cena
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    line_total = db.Column(db.Numeric(12, 2), nullable=False)

    # Stanje artikla
    condition = db.Column(db.String(20), default='USED')  # NEW, USED, DAMAGED

    # Kategorija (za automatsko kreiranje SparePart/GoodsItem)
    item_type = db.Column(db.String(20), default='SPARE_PART')  # SPARE_PART, GOODS, PHONE
    part_category = db.Column(db.String(30))  # DISPLAY, BATTERY, etc.

    # Link ka kreiranom artiklu posle potpisivanja
    spare_part_id = db.Column(db.BigInteger, db.ForeignKey('spare_part.id'))
    goods_item_id = db.Column(db.Integer, db.ForeignKey('goods_item.id'))
    phone_listing_id = db.Column(db.BigInteger, db.ForeignKey('phone_listing.id'))

    def __repr__(self):
        return f'<BuybackContractItem {self.id}: {self.item_description}>'

    def to_dict(self):
        return {
            'id': self.id,
            'item_description': self.item_description,
            'brand': self.brand,
            'model': self.model,
            'imei': self.imei,
            'serial_number': self.serial_number,
            'quantity': self.quantity,
            'unit_price': float(self.unit_price) if self.unit_price else 0,
            'line_total': float(self.line_total) if self.line_total else 0,
            'condition': self.condition,
            'item_type': self.item_type,
        }


# ============================================
# HELPER FUNKCIJE
# ============================================

def suggest_selling_price(purchase_price, margin_pct):
    """
    Predloži prodajnu cenu sa maržom, zaokruženu na okrugao broj.

    Pravilo zaokruživanja:
    - Do 500 RSD → zaokruži na 10
    - 500-2000 RSD → zaokruži na 50
    - Preko 2000 RSD → zaokruži na 100
    """
    purchase = float(purchase_price)
    margin = float(margin_pct)
    raw = purchase * (1 + margin / 100)

    if raw <= 500:
        round_to = 10
    elif raw <= 2000:
        round_to = 50
    else:
        round_to = 100

    return int(math.ceil(raw / round_to) * round_to)