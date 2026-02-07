"""Link PurchaseInvoice to SimpleSupplier

Revision ID: v333_link_invoice_supplier
Revises: v332_buyback_contract
Create Date: 2026-02-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v333_link_invoice_supplier'
down_revision = 'v332_buyback_contract'
branch_labels = None
depends_on = None


def upgrade():
    """Add supplier_id FK to purchase_invoice."""
    op.add_column(
        'purchase_invoice',
        sa.Column('supplier_id', sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        'fk_purchase_invoice_supplier',
        'purchase_invoice', 'simple_supplier',
        ['supplier_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_index('ix_purchase_invoice_supplier', 'purchase_invoice', ['supplier_id'])


def downgrade():
    """Remove supplier_id from purchase_invoice."""
    op.drop_index('ix_purchase_invoice_supplier', 'purchase_invoice')
    op.drop_constraint('fk_purchase_invoice_supplier', 'purchase_invoice', type_='foreignkey')
    op.drop_column('purchase_invoice', 'supplier_id')
