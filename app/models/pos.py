"""
POS/Kasa modeli - sistem za prodaju i račune.

CashRegisterSession - dnevna kasa po lokaciji
Receipt - račun (prodaja/refund)
ReceiptItem - stavka računa
DailyReport - arhivirani dnevni izveštaj
"""

import enum
from datetime import datetime
from ..extensions import db


# ============================================
# ENUMS
# ============================================

class PaymentMethod(enum.Enum):
    """Način plaćanja."""
    CASH = 'CASH'
    CARD = 'CARD'
    TRANSFER = 'TRANSFER'
    MIXED = 'MIXED'


class ReceiptStatus(enum.Enum):
    """Status računa."""
    DRAFT = 'DRAFT'
    ISSUED = 'ISSUED'
    VOIDED = 'VOIDED'
    REFUNDED = 'REFUNDED'


class ReceiptType(enum.Enum):
    """Tip računa."""
    SALE = 'SALE'
    REFUND = 'REFUND'


class CashRegisterStatus(enum.Enum):
    """Status kase."""
    OPEN = 'OPEN'
    CLOSED = 'CLOSED'


class SaleItemType(enum.Enum):
    """Tip stavke na računu."""
    PHONE = 'PHONE'
    SPARE_PART = 'SPARE_PART'
    SERVICE = 'SERVICE'
    TICKET = 'TICKET'
    CUSTOM = 'CUSTOM'


# ============================================
# MODELI
# ============================================

class CashRegisterSession(db.Model):
    """Dnevna kasa po lokaciji."""
    __tablename__ = 'cash_register_session'

    id = db.Column(db.Integer, primary_key=True)

    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    location_id = db.Column(
        db.Integer,
        db.ForeignKey('service_location.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    date = db.Column(db.Date, nullable=False, index=True)

    # Otvaranje
    opened_by_id = db.Column(db.Integer, db.ForeignKey('tenant_user.id', ondelete='SET NULL'))
    opened_at = db.Column(db.DateTime, default=datetime.utcnow)
    opening_cash = db.Column(db.Numeric(10, 2), default=0)

    # Zatvaranje
    closed_by_id = db.Column(db.Integer, db.ForeignKey('tenant_user.id', ondelete='SET NULL'))
    closed_at = db.Column(db.DateTime)
    closing_cash = db.Column(db.Numeric(10, 2))
    expected_cash = db.Column(db.Numeric(10, 2))
    cash_difference = db.Column(db.Numeric(10, 2))

    # Status
    status = db.Column(
        db.Enum(CashRegisterStatus),
        default=CashRegisterStatus.OPEN,
        nullable=False
    )

    # Sumirani totali
    total_revenue = db.Column(db.Numeric(12, 2), default=0)
    total_cost = db.Column(db.Numeric(12, 2), default=0)
    total_profit = db.Column(db.Numeric(12, 2), default=0)
    total_cash = db.Column(db.Numeric(12, 2), default=0)
    total_card = db.Column(db.Numeric(12, 2), default=0)
    total_transfer = db.Column(db.Numeric(12, 2), default=0)
    receipt_count = db.Column(db.Integer, default=0)
    voided_count = db.Column(db.Integer, default=0)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relacije
    receipts = db.relationship('Receipt', backref='session', lazy='dynamic', cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'location_id', 'date', name='uq_session_tenant_location_date'),
    )

    def __repr__(self):
        return f'<CashRegisterSession {self.id}: {self.date} location={self.location_id}>'


class Receipt(db.Model):
    """Račun - prodaja ili refund."""
    __tablename__ = 'receipt'

    id = db.Column(db.BigInteger, primary_key=True)

    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    session_id = db.Column(
        db.Integer,
        db.ForeignKey('cash_register_session.id', ondelete='SET NULL'),
        index=True
    )

    # Broj računa
    receipt_number = db.Column(db.String(50), nullable=False)

    # Tip i status
    receipt_type = db.Column(db.Enum(ReceiptType), default=ReceiptType.SALE, nullable=False)
    original_receipt_id = db.Column(db.BigInteger, db.ForeignKey('receipt.id', ondelete='SET NULL'))
    status = db.Column(
        db.Enum(ReceiptStatus),
        default=ReceiptStatus.DRAFT,
        nullable=False,
        index=True
    )

    # Kupac
    customer_name = db.Column(db.String(200))
    customer_phone = db.Column(db.String(30))
    customer_pib = db.Column(db.String(20))

    # Iznosi
    subtotal = db.Column(db.Numeric(12, 2), default=0)
    discount_amount = db.Column(db.Numeric(10, 2), default=0)
    total_amount = db.Column(db.Numeric(12, 2), default=0)
    total_cost = db.Column(db.Numeric(12, 2), default=0)
    profit = db.Column(db.Numeric(12, 2), default=0)

    # Plaćanje
    payment_method = db.Column(db.Enum(PaymentMethod))
    cash_received = db.Column(db.Numeric(10, 2))
    cash_change = db.Column(db.Numeric(10, 2))
    card_amount = db.Column(db.Numeric(10, 2))
    transfer_amount = db.Column(db.Numeric(10, 2))

    # Veza sa servisnim nalogom
    service_ticket_id = db.Column(db.Integer, db.ForeignKey('service_ticket.id', ondelete='SET NULL'))

    # Izdavanje
    issued_by_id = db.Column(db.Integer, db.ForeignKey('tenant_user.id', ondelete='SET NULL'))
    issued_at = db.Column(db.DateTime)

    # Storniranje
    voided_by_id = db.Column(db.Integer, db.ForeignKey('tenant_user.id', ondelete='SET NULL'))
    voided_at = db.Column(db.DateTime)
    void_reason = db.Column(db.String(300))

    # Fiskalizacija (pripremljeno za buduću integraciju)
    fiscal_invoice_number = db.Column(db.String(100))
    fiscal_signature = db.Column(db.Text)
    fiscal_sent_at = db.Column(db.DateTime)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relacije
    items = db.relationship('ReceiptItem', backref='receipt', lazy='dynamic', cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'receipt_number', name='uq_receipt_tenant_number'),
    )

    def __repr__(self):
        return f'<Receipt {self.id}: {self.receipt_number} {self.receipt_type.value}>'


class ReceiptItem(db.Model):
    """Stavka računa."""
    __tablename__ = 'receipt_item'

    id = db.Column(db.BigInteger, primary_key=True)

    receipt_id = db.Column(
        db.BigInteger,
        db.ForeignKey('receipt.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Tip stavke
    item_type = db.Column(db.Enum(SaleItemType), nullable=False)
    item_name = db.Column(db.String(300), nullable=False)
    quantity = db.Column(db.Integer, default=1, nullable=False)

    # FK-ovi na izvor stavke
    phone_listing_id = db.Column(db.Integer, db.ForeignKey('phone_listing.id', ondelete='SET NULL'))
    spare_part_id = db.Column(db.Integer, db.ForeignKey('spare_part.id', ondelete='SET NULL'))
    service_item_id = db.Column(db.Integer, db.ForeignKey('service_item.id', ondelete='SET NULL'))
    service_ticket_id = db.Column(db.Integer, db.ForeignKey('service_ticket.id', ondelete='SET NULL'))

    # Cene
    purchase_price = db.Column(db.Numeric(10, 2), default=0)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    discount_pct = db.Column(db.Numeric(5, 2), default=0)
    line_total = db.Column(db.Numeric(12, 2), nullable=False)
    line_cost = db.Column(db.Numeric(12, 2), default=0)
    line_profit = db.Column(db.Numeric(12, 2), default=0)

    def __repr__(self):
        return f'<ReceiptItem {self.id}: {self.item_name} x{self.quantity}>'


class DailyReport(db.Model):
    """Arhivirani dnevni izveštaj."""
    __tablename__ = 'daily_report'

    id = db.Column(db.Integer, primary_key=True)

    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    location_id = db.Column(
        db.Integer,
        db.ForeignKey('service_location.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    session_id = db.Column(
        db.Integer,
        db.ForeignKey('cash_register_session.id', ondelete='SET NULL')
    )
    date = db.Column(db.Date, nullable=False, index=True)

    # Finansije
    total_revenue = db.Column(db.Numeric(12, 2), default=0)
    total_cost = db.Column(db.Numeric(12, 2), default=0)
    total_profit = db.Column(db.Numeric(12, 2), default=0)
    profit_margin_pct = db.Column(db.Numeric(5, 2))

    # Plaćanja
    total_cash = db.Column(db.Numeric(12, 2), default=0)
    total_card = db.Column(db.Numeric(12, 2), default=0)
    total_transfer = db.Column(db.Numeric(12, 2), default=0)

    # Kasa
    opening_cash = db.Column(db.Numeric(10, 2))
    closing_cash = db.Column(db.Numeric(10, 2))
    cash_difference = db.Column(db.Numeric(10, 2))

    # Statistika
    receipt_count = db.Column(db.Integer, default=0)
    voided_count = db.Column(db.Integer, default=0)
    items_sold = db.Column(db.Integer, default=0)
    phones_sold = db.Column(db.Integer, default=0)
    parts_sold = db.Column(db.Integer, default=0)
    services_sold = db.Column(db.Integer, default=0)

    # Snapshot
    top_items_json = db.Column(db.JSON)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'location_id', 'date', name='uq_daily_report_tenant_location_date'),
    )

    def __repr__(self):
        return f'<DailyReport {self.id}: {self.date} location={self.location_id}>'