"""Create TenantFavoriteSupplier table

Revision ID: v342_tenant_favorites
Revises: v341_marketplace_rating
Create Date: 2026-02-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v342_tenant_favorites'
down_revision = 'v341_marketplace_rating'
branch_labels = None
depends_on = None


def upgrade():
    """Create tenant_favorite_supplier table."""

    op.create_table(
        'tenant_favorite_supplier',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenant.id', ondelete='CASCADE'), nullable=False),
        sa.Column('supplier_tenant_id', sa.Integer(), sa.ForeignKey('tenant.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('tenant_user.id', ondelete='SET NULL')),
    )

    # One favorite per tenant-supplier pair
    op.create_unique_constraint('uq_tenant_favorite_supplier', 'tenant_favorite_supplier', ['tenant_id', 'supplier_tenant_id'])

    op.create_index('ix_tenant_favorite_tenant', 'tenant_favorite_supplier', ['tenant_id'])
    op.create_index('ix_tenant_favorite_supplier', 'tenant_favorite_supplier', ['supplier_tenant_id'])


def downgrade():
    """Drop tenant_favorite_supplier table."""
    op.drop_index('ix_tenant_favorite_supplier', 'tenant_favorite_supplier')
    op.drop_index('ix_tenant_favorite_tenant', 'tenant_favorite_supplier')
    op.drop_constraint('uq_tenant_favorite_supplier', 'tenant_favorite_supplier', type_='unique')
    op.drop_table('tenant_favorite_supplier')
