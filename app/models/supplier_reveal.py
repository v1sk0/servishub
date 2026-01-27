"""
SupplierReveal model - audit zapis otkrivanja dobavljača.

Beleži koji tenant je otkrio kog dobavljača i kada, uz vezu na kreditnu transakciju.
"""

from datetime import datetime
from ..extensions import db


class SupplierReveal(db.Model):
    """Audit zapis: koji tenant je otkrio kog dobavljača i kada."""
    __tablename__ = 'supplier_reveal'

    id = db.Column(db.BigInteger, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id', ondelete='CASCADE'), nullable=False, index=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id', ondelete='CASCADE'), nullable=False, index=True)
    credit_transaction_id = db.Column(db.BigInteger, db.ForeignKey('credit_transaction.id', ondelete='SET NULL'))
    revealed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'supplier_id', name='uq_tenant_supplier_reveal'),
    )

    def __repr__(self):
        return f'<SupplierReveal tenant={self.tenant_id} supplier={self.supplier_id}>'