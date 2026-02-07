"""Create StockMovement and LocationStock tables

Revision ID: v334_stock_movement
Revises: v333_link_invoice_supplier
Create Date: 2026-02-06

StockMovement je jedinstven ledger za sve promene zaliha.
LocationStock je cache stanja po lokaciji.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v334_stock_movement'
down_revision = 'v333_link_invoice_supplier'
branch_labels = None
depends_on = None


def upgrade():
    """Create location_stock and stock_movement tables."""

    # LocationStock - cache stanja po lokaciji
    op.create_table(
        'location_stock',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('location_id', sa.Integer(), sa.ForeignKey('service_location.id', ondelete='CASCADE'), nullable=False),
        sa.Column('goods_item_id', sa.Integer(), sa.ForeignKey('goods_item.id', ondelete='CASCADE'), nullable=True),
        sa.Column('spare_part_id', sa.BigInteger(), sa.ForeignKey('spare_part.id', ondelete='CASCADE'), nullable=True),
        sa.Column('quantity', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last_movement_id', sa.BigInteger(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    # Constraints
    op.create_check_constraint(
        'ck_loc_stock_one_item', 'location_stock',
        '(goods_item_id IS NOT NULL AND spare_part_id IS NULL) OR '
        '(goods_item_id IS NULL AND spare_part_id IS NOT NULL)'
    )
    op.create_unique_constraint('uq_loc_stock_goods', 'location_stock', ['location_id', 'goods_item_id'])
    op.create_unique_constraint('uq_loc_stock_spare', 'location_stock', ['location_id', 'spare_part_id'])
    op.create_index('ix_location_stock_location', 'location_stock', ['location_id'])

    # StockMovement - ledger
    op.create_table(
        'stock_movement',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenant.id', ondelete='CASCADE'), nullable=False),
        sa.Column('location_id', sa.Integer(), sa.ForeignKey('service_location.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('target_location_id', sa.Integer(), sa.ForeignKey('service_location.id', ondelete='SET NULL'), nullable=True),
        # Item references
        sa.Column('goods_item_id', sa.Integer(), sa.ForeignKey('goods_item.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('spare_part_id', sa.BigInteger(), sa.ForeignKey('spare_part.id', ondelete='RESTRICT'), nullable=True),
        # Movement data
        sa.Column('movement_type', sa.String(20), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('balance_before', sa.Integer(), nullable=False),
        sa.Column('balance_after', sa.Integer(), nullable=False),
        # Prices
        sa.Column('unit_cost', sa.Numeric(10, 2), nullable=True),
        sa.Column('unit_price', sa.Numeric(10, 2), nullable=True),
        # Reference
        sa.Column('reference_type', sa.String(30), nullable=True),
        sa.Column('reference_id', sa.BigInteger(), nullable=True),
        sa.Column('reference_number', sa.String(50), nullable=True),
        # Audit
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('tenant_user.id', ondelete='SET NULL'), nullable=False),
        sa.Column('reason', sa.String(255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # Check Constraints
    op.create_check_constraint(
        'ck_movement_one_item', 'stock_movement',
        '(goods_item_id IS NOT NULL AND spare_part_id IS NULL) OR '
        '(goods_item_id IS NULL AND spare_part_id IS NOT NULL)'
    )
    op.create_check_constraint(
        'ck_movement_quantity_nonzero', 'stock_movement',
        'quantity != 0'
    )
    op.create_check_constraint(
        'ck_movement_balance_positive', 'stock_movement',
        'balance_after >= 0'
    )

    # Indexes
    op.create_index('ix_stock_movement_tenant', 'stock_movement', ['tenant_id'])
    op.create_index('ix_stock_movement_location', 'stock_movement', ['location_id'])
    op.create_index('ix_stock_movement_goods', 'stock_movement', ['goods_item_id'])
    op.create_index('ix_stock_movement_spare', 'stock_movement', ['spare_part_id'])
    op.create_index('ix_stock_movement_type', 'stock_movement', ['movement_type'])
    op.create_index('ix_stock_movement_created', 'stock_movement', ['created_at'])
    op.create_index('ix_movement_reference', 'stock_movement', ['reference_type', 'reference_id'])
    op.create_index('ix_movement_location_created', 'stock_movement', ['location_id', 'created_at'])
    op.create_index('ix_movement_goods_created', 'stock_movement', ['goods_item_id', 'created_at'])
    op.create_index('ix_movement_spare_created', 'stock_movement', ['spare_part_id', 'created_at'])


def downgrade():
    """Drop stock_movement and location_stock tables."""
    # Drop indexes first
    op.drop_index('ix_movement_spare_created', 'stock_movement')
    op.drop_index('ix_movement_goods_created', 'stock_movement')
    op.drop_index('ix_movement_location_created', 'stock_movement')
    op.drop_index('ix_movement_reference', 'stock_movement')
    op.drop_index('ix_stock_movement_created', 'stock_movement')
    op.drop_index('ix_stock_movement_type', 'stock_movement')
    op.drop_index('ix_stock_movement_spare', 'stock_movement')
    op.drop_index('ix_stock_movement_goods', 'stock_movement')
    op.drop_index('ix_stock_movement_location', 'stock_movement')
    op.drop_index('ix_stock_movement_tenant', 'stock_movement')

    # Drop check constraints
    op.drop_constraint('ck_movement_balance_positive', 'stock_movement', type_='check')
    op.drop_constraint('ck_movement_quantity_nonzero', 'stock_movement', type_='check')
    op.drop_constraint('ck_movement_one_item', 'stock_movement', type_='check')

    # Drop tables
    op.drop_table('stock_movement')

    op.drop_index('ix_location_stock_location', 'location_stock')
    op.drop_constraint('uq_loc_stock_spare', 'location_stock', type_='unique')
    op.drop_constraint('uq_loc_stock_goods', 'location_stock', type_='unique')
    op.drop_constraint('ck_loc_stock_one_item', 'location_stock', type_='check')
    op.drop_table('location_stock')
