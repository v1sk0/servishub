"""
Rating model - univerzalni polimorfni rating sistem.
"""

import enum
from datetime import datetime
from ..extensions import db


class RatingType(enum.Enum):
    """Tip rejtinga."""
    SERVICE_TO_USER = 'SERVICE_TO_USER'
    USER_TO_SERVICE = 'USER_TO_SERVICE'
    SUPPLIER_TO_TENANT = 'SUPPLIER_TO_TENANT'
    TENANT_TO_SUPPLIER = 'TENANT_TO_SUPPLIER'


class Rating(db.Model):
    """Univerzalni polimorfni rating."""
    __tablename__ = 'rating'

    id = db.Column(db.BigInteger, primary_key=True)

    rating_type = db.Column(db.Enum(RatingType), nullable=False, index=True)

    # Polimorfni rater
    rater_type = db.Column(db.String(20), nullable=False)  # 'tenant', 'supplier', 'public_user'
    rater_id = db.Column(db.Integer, nullable=False)

    # Polimorfni rated
    rated_type = db.Column(db.String(20), nullable=False)
    rated_id = db.Column(db.Integer, nullable=False)

    # Ocena
    score = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)

    # Referenca na zahtev/narudžbinu
    service_request_id = db.Column(db.BigInteger, db.ForeignKey('service_request.id', ondelete='SET NULL'))
    part_order_id = db.Column(db.Integer, db.ForeignKey('part_order.id', ondelete='SET NULL'))

    # Vidljivost
    is_visible = db.Column(db.Boolean, default=True, nullable=False)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.CheckConstraint('score >= 1 AND score <= 5', name='check_rating_score_range'),
        db.UniqueConstraint(
            'rater_type', 'rater_id', 'service_request_id',
            name='uq_rating_per_request'
        ),
    )

    def __repr__(self):
        return f'<Rating {self.id}: {self.rating_type.value} score={self.score}>'