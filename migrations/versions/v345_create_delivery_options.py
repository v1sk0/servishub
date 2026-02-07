"""Create SupplierDeliveryOption table

Revision ID: v345_delivery_options
Revises: v343_tenant_rating_cache
Create Date: 2026-02-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v345_delivery_options'
down_revision = 'v343_tenant_rating_cache'
branch_labels = None
depends_on = None


def upgrade():
    """Create supplier_delivery_option table."""

    op.create_table(
        'supplier_delivery_option',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('supplier_tenant_id', sa.Integer(), sa.ForeignKey('tenant.id', ondelete='CASCADE'), nullable=False),
        # Option details
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text()),
        # Timing
        sa.Column('estimated_days_min', sa.Integer(), server_default='1'),
        sa.Column('estimated_days_max', sa.Integer(), server_default='3'),
        # Cost
        sa.Column('delivery_cost', sa.Numeric(10, 2), server_default='0'),
        sa.Column('currency', sa.String(3), server_default='RSD'),
        # Conditions
        sa.Column('is_free_above', sa.Numeric(10, 2)),
        sa.Column('min_order_amount', sa.Numeric(10, 2)),
        # Status
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('is_default', sa.Boolean(), server_default='false'),
        sa.Column('sort_order', sa.Integer(), server_default='0'),
        # Timestamps
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime()),
    )

    op.create_index('ix_delivery_supplier', 'supplier_delivery_option', ['supplier_tenant_id'])
    op.create_index('ix_delivery_supplier_active', 'supplier_delivery_option', ['supplier_tenant_id', 'is_active'])


def downgrade():
    """Drop supplier_delivery_option table."""
    op.drop_index('ix_delivery_supplier_active', 'supplier_delivery_option')
    op.drop_index('ix_delivery_supplier', 'supplier_delivery_option')
    op.drop_table('supplier_delivery_option')
