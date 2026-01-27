"""
ContentReport model - prijava sadržaja.
"""

import enum
from datetime import datetime
from ..extensions import db


class ReportReason(enum.Enum):
    """Razlog prijave."""
    SPAM = 'spam'
    OFFENSIVE = 'offensive'
    FAKE = 'fake'
    FRAUD = 'fraud'


class ReportStatus(enum.Enum):
    """Status prijave."""
    PENDING = 'pending'
    REVIEWED = 'reviewed'
    ACTION_TAKEN = 'action_taken'
    DISMISSED = 'dismissed'


class ContentReport(db.Model):
    """Prijava sadržaja."""
    __tablename__ = 'content_report'

    id = db.Column(db.BigInteger, primary_key=True)

    # Ko prijavljuje (polimorfno)
    reporter_type = db.Column(db.String(20), nullable=False)  # 'tenant', 'supplier', 'public_user'
    reporter_id = db.Column(db.Integer, nullable=False)

    # Šta se prijavljuje (polimorfno)
    entity_type = db.Column(db.String(50), nullable=False)  # 'service_request', 'service_bid', 'rating', etc.
    entity_id = db.Column(db.BigInteger, nullable=False)

    # Detalji
    reason = db.Column(db.Enum(ReportReason), nullable=False)
    description = db.Column(db.Text)

    # Status
    status = db.Column(
        db.Enum(ReportStatus),
        default=ReportStatus.PENDING,
        nullable=False,
        index=True
    )
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('platform_admin.id', ondelete='SET NULL'))
    reviewed_at = db.Column(db.DateTime)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<ContentReport {self.id}: {self.entity_type}#{self.entity_id}>'