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