"""
OrderRating model - ocene transakcija izmedju tenanta i dobavljaca.

Obe strane mogu da ocene transakciju nakon COMPLETED statusa.
Tenant ocenjuje supplier-a (BUYER), supplier ocenjuje tenant-a (SELLER).
"""

import enum
from datetime import datetime
from ..extensions import db


class RaterType(enum.Enum):
    """Ko ocenjuje."""
    BUYER = 'BUYER'      # Tenant ocenjuje supplier-a
    SELLER = 'SELLER'    # Supplier ocenjuje tenant-a


class OrderRatingType(enum.Enum):
    """Tip ocene."""
    POSITIVE = 'POSITIVE'
    NEGATIVE = 'NEGATIVE'


class OrderRating(db.Model):
    """
    Ocena transakcije - POSITIVE ili NEGATIVE sa opcionalnim komentarom.

    Unique constraint: jedan rater moze oceniti jednu narudzbinu samo jednom.
    """
    __tablename__ = 'order_rating'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(
        db.BigInteger,
        db.ForeignKey('part_order.id', ondelete='CASCADE'),
        nullable=False
    )
    rater_type = db.Column(db.Enum(RaterType), nullable=False)
    rater_id = db.Column(db.Integer, nullable=False)
    rated_id = db.Column(db.Integer, nullable=False)
    rating = db.Column(db.Enum(OrderRatingType), nullable=False)
    comment = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacija
    order = db.relationship('PartOrder', backref='ratings')

    __table_args__ = (
        db.UniqueConstraint('order_id', 'rater_type', 'rater_id',
                           name='uq_order_rating_unique'),
        db.Index('ix_order_rating_rated', 'rated_id', 'rater_type'),
    )

    def __repr__(self):
        return f'<OrderRating {self.id}: {self.rater_type.value} on order {self.order_id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'rater_type': self.rater_type.value,
            'rating': self.rating.value,
            'comment': self.comment,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
