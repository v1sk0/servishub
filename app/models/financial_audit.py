"""
Financial Audit Log - log za sve novčane transakcije platforme.
"""

import enum
from datetime import datetime
from ..extensions import db


class FinancialCategory(enum.Enum):
    CREDIT = 'CREDIT'
    INVOICE = 'INVOICE'
    SUBSCRIPTION = 'SUBSCRIPTION'
    CONNECTION = 'CONNECTION'
    REFUND = 'REFUND'
    POS_SALE = 'POS_SALE'
    POS_VOID = 'POS_VOID'


class FinancialAuditLog(db.Model):
    """Log za SVE novčane transakcije platforme."""
    __tablename__ = 'financial_audit_log'

    id = db.Column(db.BigInteger, primary_key=True)

    category = db.Column(db.Enum(FinancialCategory), nullable=False, index=True)
    event_type = db.Column(db.String(50), nullable=False)  # e.g. 'credit_purchase', 'pos_receipt_issued'

    # Ko je izvršio akciju
    actor_type = db.Column(db.String(30), nullable=False)  # 'tenant_user', 'supplier_user', 'public_user', 'system'
    actor_id = db.Column(db.Integer)

    # Vlasnik transakcije
    owner_type = db.Column(db.String(30))  # 'tenant', 'supplier', 'public_user'
    owner_id = db.Column(db.Integer)

    # Finansijski podaci
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(3), default='RSD', nullable=False)
    description = db.Column(db.String(500))
    details_json = db.Column(db.JSON)

    # Referenca na izvorni objekat
    reference_type = db.Column(db.String(50))
    reference_id = db.Column(db.BigInteger)

    # Metadata
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        db.Index('ix_fin_audit_owner', 'owner_type', 'owner_id'),
        db.Index('ix_fin_audit_category_created', 'category', 'created_at'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'category': self.category.value,
            'event_type': self.event_type,
            'actor_type': self.actor_type,
            'actor_id': self.actor_id,
            'owner_type': self.owner_type,
            'owner_id': self.owner_id,
            'amount': float(self.amount),
            'currency': self.currency,
            'description': self.description,
            'details_json': self.details_json,
            'created_at': self.created_at.isoformat(),
        }