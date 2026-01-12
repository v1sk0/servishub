"""
Order modeli - narudzbine delova od dobavljaca i partnera.

PartOrder - narudzbina
PartOrderItem - stavke narudzbine
PartOrderMessage - komunikacija oko narudzbine
"""

import enum
from datetime import datetime
from ..extensions import db


class OrderStatus(enum.Enum):
    """
    Status narudzbine - workflow od kreiranja do zavrsetka.

    DRAFT - Servis priprema narudzbenicu
    SENT - Poslato dobavljacu, ceka potvrdu
    CONFIRMED - Dobavljac potvrdio, priprema slanje
    REJECTED - Dobavljac odbio
    SHIPPED - Poslato
    DELIVERED - Servis primio
    COMPLETED - Zavrseno, placeno
    CANCELLED - Otkazano
    DISPUTED - Spor
    """
    DRAFT = 'DRAFT'
    SENT = 'SENT'
    CONFIRMED = 'CONFIRMED'
    REJECTED = 'REJECTED'
    SHIPPED = 'SHIPPED'
    DELIVERED = 'DELIVERED'
    COMPLETED = 'COMPLETED'
    CANCELLED = 'CANCELLED'
    DISPUTED = 'DISPUTED'


class SellerType(enum.Enum):
    """Tip prodavca."""
    SUPPLIER = 'SUPPLIER'  # Dobavljac
    TENANT = 'TENANT'      # Partner servis


class PartOrder(db.Model):
    """
    Narudzbina delova - od dobavljaca ili partnera.

    Prati ceo workflow od kreiranja do zavrsetka,
    ukljucujuci proviziju za dobavljace.
    """
    __tablename__ = 'part_order'

    # Primarni kljuc
    id = db.Column(db.BigInteger, primary_key=True)

    # Ko narucuje (kupac)
    buyer_tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    buyer_location_id = db.Column(
        db.Integer,
        db.ForeignKey('service_location.id', ondelete='SET NULL'),
        nullable=True
    )
    buyer_user_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant_user.id', ondelete='SET NULL'),
        nullable=True
    )

    # Od koga (prodavac)
    seller_type = db.Column(
        db.Enum(SellerType),
        nullable=False
    )
    seller_supplier_id = db.Column(
        db.Integer,
        db.ForeignKey('supplier.id', ondelete='SET NULL'),
        nullable=True
    )
    seller_tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='SET NULL'),
        nullable=True
    )

    # Veza sa servisnim nalogom (opciono)
    service_ticket_id = db.Column(
        db.BigInteger,
        db.ForeignKey('service_ticket.id', ondelete='SET NULL'),
        nullable=True
    )

    # Broj narudzbine
    order_number = db.Column(db.String(20), unique=True, nullable=False, index=True)

    # Status
    status = db.Column(
        db.Enum(OrderStatus),
        default=OrderStatus.DRAFT,
        nullable=False,
        index=True
    )

    # Vrednost
    subtotal = db.Column(db.Numeric(12, 2), default=0)
    commission_amount = db.Column(db.Numeric(10, 2), default=0)  # 5% za dobavljace
    total_amount = db.Column(db.Numeric(12, 2), default=0)
    currency = db.Column(db.String(3), default='RSD')

    # Napomene
    buyer_notes = db.Column(db.Text)
    seller_notes = db.Column(db.Text)

    # Tracking
    tracking_number = db.Column(db.String(100))
    tracking_url = db.Column(db.String(500))

    # Timestampovi za svaki status
    sent_at = db.Column(db.DateTime)
    confirmed_at = db.Column(db.DateTime)
    rejected_at = db.Column(db.DateTime)
    rejection_reason = db.Column(db.Text)
    shipped_at = db.Column(db.DateTime)
    delivered_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    cancelled_at = db.Column(db.DateTime)
    cancellation_reason = db.Column(db.Text)
    cancelled_by = db.Column(db.String(10))  # BUYER / SELLER

    # Timestampovi
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relacije
    buyer_tenant = db.relationship(
        'Tenant',
        foreign_keys=[buyer_tenant_id],
        backref='orders_as_buyer'
    )
    seller_tenant = db.relationship(
        'Tenant',
        foreign_keys=[seller_tenant_id],
        backref='orders_as_seller'
    )
    seller_supplier = db.relationship('Supplier', backref='orders')
    buyer_user = db.relationship('TenantUser', backref='orders')
    service_ticket = db.relationship('ServiceTicket', backref='part_orders')

    items = db.relationship(
        'PartOrderItem',
        backref='order',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    messages = db.relationship(
        'PartOrderMessage',
        backref='order',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )

    # Indeksi
    __table_args__ = (
        db.Index('ix_order_buyer_status', 'buyer_tenant_id', 'status'),
        db.Index('ix_order_seller_supplier', 'seller_supplier_id', 'status'),
        db.Index('ix_order_seller_tenant', 'seller_tenant_id', 'status'),
    )

    def __repr__(self):
        return f'<PartOrder {self.order_number}>'

    def calculate_totals(self):
        """Racuna subtotal, proviziju i total."""
        self.subtotal = sum(item.total_price for item in self.items)
        # Provizija samo za dobavljace, ne za partnere
        if self.seller_type == SellerType.SUPPLIER:
            self.commission_amount = self.subtotal * 0.05  # 5%
        else:
            self.commission_amount = 0
        self.total_amount = self.subtotal

    def to_dict(self):
        """Konvertuje u dict za API response."""
        return {
            'id': self.id,
            'order_number': self.order_number,
            'status': self.status.value,
            'seller_type': self.seller_type.value,
            'subtotal': float(self.subtotal) if self.subtotal else 0,
            'commission_amount': float(self.commission_amount) if self.commission_amount else 0,
            'total_amount': float(self.total_amount) if self.total_amount else 0,
            'currency': self.currency,
            'buyer_notes': self.buyer_notes,
            'tracking_number': self.tracking_number,
            'created_at': self.created_at.isoformat(),
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'confirmed_at': self.confirmed_at.isoformat() if self.confirmed_at else None,
            'shipped_at': self.shipped_at.isoformat() if self.shipped_at else None,
            'delivered_at': self.delivered_at.isoformat() if self.delivered_at else None,
        }


class PartOrderItem(db.Model):
    """
    Stavka narudzbine - jedan deo u narudzbini.

    Cuva snapshot podataka u trenutku narudzbine jer se cene menjaju.
    """
    __tablename__ = 'part_order_item'

    # Primarni kljuc
    id = db.Column(db.BigInteger, primary_key=True)

    # Veza sa narudzbinom
    order_id = db.Column(
        db.BigInteger,
        db.ForeignKey('part_order.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Referenca na listing (moze biti NULL ako je obrisan)
    supplier_listing_id = db.Column(
        db.BigInteger,
        db.ForeignKey('supplier_listing.id', ondelete='SET NULL'),
        nullable=True
    )
    spare_part_id = db.Column(
        db.BigInteger,
        db.ForeignKey('spare_part.id', ondelete='SET NULL'),
        nullable=True
    )

    # Snapshot podataka u trenutku narudzbine
    part_name = db.Column(db.String(200), nullable=False)
    part_number = db.Column(db.String(50))
    brand = db.Column(db.String(50))
    model = db.Column(db.String(100))

    # Kolicina i cena
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    total_price = db.Column(db.Numeric(12, 2), nullable=False)

    # Timestamp
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relacije
    supplier_listing = db.relationship('SupplierListing', backref='order_items')
    spare_part = db.relationship('SparePart', backref='order_items')

    def __repr__(self):
        return f'<PartOrderItem {self.id}: {self.part_name} x{self.quantity}>'

    def to_dict(self):
        return {
            'id': self.id,
            'part_name': self.part_name,
            'part_number': self.part_number,
            'brand': self.brand,
            'model': self.model,
            'quantity': self.quantity,
            'unit_price': float(self.unit_price),
            'total_price': float(self.total_price),
        }


class PartOrderMessage(db.Model):
    """
    Poruka u vezi narudzbine - komunikacija izmedju kupca i prodavca.
    """
    __tablename__ = 'part_order_message'

    # Primarni kljuc
    id = db.Column(db.BigInteger, primary_key=True)

    # Veza sa narudzbinom
    order_id = db.Column(
        db.BigInteger,
        db.ForeignKey('part_order.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Ko salje
    sender_type = db.Column(db.String(10), nullable=False)  # BUYER / SELLER
    sender_user_id = db.Column(db.Integer)  # TenantUser.id ili SupplierUser.id

    # Sadrzaj
    message_text = db.Column(db.Text, nullable=False)
    attachments_json = db.Column(db.JSON)  # [{filename, url, size}, ...]

    # Citanje
    read_at = db.Column(db.DateTime)
    read_by_user_id = db.Column(db.Integer)

    # Timestamp
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Indeks
    __table_args__ = (
        db.Index('ix_message_order_created', 'order_id', 'created_at'),
    )

    def __repr__(self):
        return f'<PartOrderMessage {self.id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'sender_type': self.sender_type,
            'message_text': self.message_text,
            'attachments': self.attachments_json,
            'read_at': self.read_at.isoformat() if self.read_at else None,
            'created_at': self.created_at.isoformat(),
        }


def generate_order_number():
    """Generise jedinstveni broj narudzbine: ORD-2026-00001"""
    from sqlalchemy import func

    year = datetime.utcnow().year
    prefix = f'ORD-{year}-'

    # Nadji poslednji broj za ovu godinu
    last_order = db.session.query(PartOrder).filter(
        PartOrder.order_number.like(f'{prefix}%')
    ).order_by(PartOrder.id.desc()).first()

    if last_order:
        last_num = int(last_order.order_number.split('-')[-1])
        next_num = last_num + 1
    else:
        next_num = 1

    return f'{prefix}{next_num:05d}'
