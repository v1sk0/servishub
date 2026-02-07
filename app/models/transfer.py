"""
TransferRequest - Zahtevi za transfer robe između lokacija istog tenanta.

Workflow:
1. Radnik na lokaciji A vidi da mu treba deo sa lokacije B
2. Kreira TransferRequest
3. Menadžer lokacije B odobrava ili odbija
4. Ako odobren: TRANSFER_OUT movement na B, TRANSFER_IN na A
5. Potvrda prijema

Status workflow:
    PENDING -> APPROVED -> SHIPPED -> RECEIVED
         |         |
         +-> REJECTED
         +-> CANCELLED
"""

import enum
from datetime import datetime, date
from ..extensions import db


class TransferRequestStatus(enum.Enum):
    """Status zahteva za transfer."""
    PENDING = 'PENDING'       # Čeka odobrenje
    APPROVED = 'APPROVED'     # Odobren, čeka slanje
    REJECTED = 'REJECTED'     # Odbijen
    SHIPPED = 'SHIPPED'       # Poslato
    RECEIVED = 'RECEIVED'     # Primljeno
    CANCELLED = 'CANCELLED'   # Otkazano


class TransferRequest(db.Model):
    """Zahtev za transfer robe između lokacija istog tenanta."""
    __tablename__ = 'transfer_request'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Request number: TR-2026-00001
    request_number = db.Column(db.String(20), unique=True, nullable=False)
    request_date = db.Column(db.Date, nullable=False, default=date.today)

    # Ko traži i od koga
    from_location_id = db.Column(
        db.Integer,
        db.ForeignKey('service_location.id', ondelete='RESTRICT'),
        nullable=False,
        index=True
    )
    to_location_id = db.Column(
        db.Integer,
        db.ForeignKey('service_location.id', ondelete='RESTRICT'),
        nullable=False,
        index=True
    )

    # Status
    status = db.Column(
        db.Enum(TransferRequestStatus),
        default=TransferRequestStatus.PENDING,
        nullable=False,
        index=True
    )

    # Razlog zahteva
    reason = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    # Audit - ko je tražio
    requested_by_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant_user.id', ondelete='SET NULL'),
        nullable=False
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Odobrenje
    approved_by_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant_user.id', ondelete='SET NULL'),
        nullable=True
    )
    approved_at = db.Column(db.DateTime, nullable=True)
    rejected_reason = db.Column(db.String(255), nullable=True)

    # Slanje
    shipped_at = db.Column(db.DateTime, nullable=True)
    shipped_by_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant_user.id', ondelete='SET NULL'),
        nullable=True
    )

    # Prijem
    received_at = db.Column(db.DateTime, nullable=True)
    received_by_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant_user.id', ondelete='SET NULL'),
        nullable=True
    )

    # Relacije
    items = db.relationship(
        'TransferRequestItem',
        backref='request',
        cascade='all, delete-orphan',
        lazy='dynamic'
    )
    from_location = db.relationship('ServiceLocation', foreign_keys=[from_location_id])
    to_location = db.relationship('ServiceLocation', foreign_keys=[to_location_id])
    requested_by = db.relationship('TenantUser', foreign_keys=[requested_by_id])
    approved_by = db.relationship('TenantUser', foreign_keys=[approved_by_id])

    __table_args__ = (
        db.CheckConstraint(
            'from_location_id != to_location_id',
            name='ck_transfer_diff_locations'
        ),
    )

    @staticmethod
    def generate_request_number(tenant_id: int) -> str:
        """Generiše sledeći broj zahteva: TR-2026-00001"""
        year = datetime.now().year
        prefix = f"TR-{year}-"

        last = TransferRequest.query.filter(
            TransferRequest.tenant_id == tenant_id,
            TransferRequest.request_number.like(f"{prefix}%")
        ).order_by(TransferRequest.request_number.desc()).first()

        next_num = 1
        if last:
            try:
                next_num = int(last.request_number.split('-')[-1]) + 1
            except ValueError:
                pass
        return f"{prefix}{next_num:05d}"

    def __repr__(self):
        return f'<TransferRequest {self.request_number}: {self.status.value}>'

    def to_dict(self):
        return {
            'id': self.id,
            'request_number': self.request_number,
            'request_date': self.request_date.isoformat() if self.request_date else None,
            'from_location_id': self.from_location_id,
            'from_location_name': self.from_location.name if self.from_location else None,
            'to_location_id': self.to_location_id,
            'to_location_name': self.to_location.name if self.to_location else None,
            'status': self.status.value,
            'reason': self.reason,
            'items_count': self.items.count(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'approved_at': self.approved_at.isoformat() if self.approved_at else None,
            'shipped_at': self.shipped_at.isoformat() if self.shipped_at else None,
            'received_at': self.received_at.isoformat() if self.received_at else None,
        }


class TransferRequestItem(db.Model):
    """Stavka zahteva za transfer."""
    __tablename__ = 'transfer_request_item'

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(
        db.Integer,
        db.ForeignKey('transfer_request.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Šta se traži (jedno od dva)
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

    # Količine
    quantity_requested = db.Column(db.Integer, nullable=False)
    quantity_approved = db.Column(db.Integer, nullable=True)  # Može biti manje od traženog
    quantity_received = db.Column(db.Integer, nullable=True)

    # Napomena za stavku
    notes = db.Column(db.String(255), nullable=True)

    # Relacije
    goods_item = db.relationship('GoodsItem')
    spare_part = db.relationship('SparePart')

    __table_args__ = (
        db.CheckConstraint(
            '(goods_item_id IS NOT NULL AND spare_part_id IS NULL) OR '
            '(goods_item_id IS NULL AND spare_part_id IS NOT NULL)',
            name='ck_transfer_item_one'
        ),
    )

    def __repr__(self):
        item = f"goods:{self.goods_item_id}" if self.goods_item_id else f"part:{self.spare_part_id}"
        return f'<TransferRequestItem {self.id}: {item} qty={self.quantity_requested}>'

    def to_dict(self):
        item_name = None
        if self.goods_item:
            item_name = self.goods_item.name
        elif self.spare_part:
            item_name = self.spare_part.part_name

        return {
            'id': self.id,
            'goods_item_id': self.goods_item_id,
            'spare_part_id': self.spare_part_id,
            'item_name': item_name,
            'quantity_requested': self.quantity_requested,
            'quantity_approved': self.quantity_approved,
            'quantity_received': self.quantity_received,
            'notes': self.notes,
        }
