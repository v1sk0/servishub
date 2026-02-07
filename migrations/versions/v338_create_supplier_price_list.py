"""Create SupplierPriceList and SupplierPriceListItem tables

Revision ID: v338_supplier_price_list
Revises: v337_transfer_request
Create Date: 2026-02-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v338_supplier_price_list'
down_revision = 'v337_transfer_request'
branch_labels = None
depends_on = None


def upgrade():
    """Create supplier_price_list and supplier_price_list_item tables."""

    # SupplierPriceList
    op.create_table(
        'supplier_price_list',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('supplier_tenant_id', sa.Integer(), sa.ForeignKey('tenant.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('currency', sa.String(3), server_default='RSD'),
        sa.Column('status', sa.String(20), server_default='DRAFT', nullable=False),
        sa.Column('valid_from', sa.Date()),
        sa.Column('valid_until', sa.Date()),
        sa.Column('total_items', sa.Integer(), server_default='0'),
        sa.Column('total_orders', sa.Integer(), server_default='0'),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('tenant_user.id', ondelete='SET NULL')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime()),
        sa.Column('last_import_at', sa.DateTime()),
    )
    op.create_index('ix_supplier_price_list_tenant', 'supplier_price_list', ['supplier_tenant_id'])
    op.create_index('ix_supplier_price_list_status', 'supplier_price_list', ['status'])

    # SupplierPriceListItem
    op.create_table(
        'supplier_price_list_item',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('price_list_id', sa.Integer(), sa.ForeignKey('supplier_price_list.id', ondelete='CASCADE'), nullable=False),
        # Matching fields
        sa.Column('brand', sa.String(100), nullable=False),
        sa.Column('model', sa.String(100)),
        sa.Column('part_category', sa.String(50)),
        sa.Column('part_name', sa.String(200), nullable=False),
        # Quality
        sa.Column('quality_grade', sa.String(20)),
        sa.Column('is_original', sa.Boolean(), server_default='false'),
        # Price
        sa.Column('price', sa.Numeric(10, 2), nullable=False),
        sa.Column('currency', sa.String(3), server_default='RSD'),
        # Availability
        sa.Column('in_stock', sa.Boolean(), server_default='true'),
        sa.Column('stock_quantity', sa.Integer()),
        sa.Column('lead_time_days', sa.Integer()),
        # Search
        sa.Column('search_text', sa.Text()),
        # Status
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime()),
    )
    op.create_index('ix_price_list_item_list', 'supplier_price_list_item', ['price_list_id'])
    op.create_index('ix_price_list_item_brand', 'supplier_price_list_item', ['brand'])
    op.create_index('ix_price_list_item_model', 'supplier_price_list_item', ['model'])
    op.create_index('ix_price_list_item_category', 'supplier_price_list_item', ['part_category'])
    op.create_index('ix_price_item_brand_model', 'supplier_price_list_item', ['brand', 'model'])
    op.create_index('ix_price_item_active_stock', 'supplier_price_list_item', ['is_active', 'in_stock'])


def downgrade():
    """Drop supplier_price_list_item and supplier_price_list tables."""
    op.drop_index('ix_price_item_active_stock', 'supplier_price_list_item')
    op.drop_index('ix_price_item_brand_model', 'supplier_price_list_item')
    op.drop_index('ix_price_list_item_category', 'supplier_price_list_item')
    op.drop_index('ix_price_list_item_model', 'supplier_price_list_item')
    op.drop_index('ix_price_list_item_brand', 'supplier_price_list_item')
    op.drop_index('ix_price_list_item_list', 'supplier_price_list_item')
    op.drop_table('supplier_price_list_item')

    op.drop_index('ix_supplier_price_list_status', 'supplier_price_list')
    op.drop_index('ix_supplier_price_list_tenant', 'supplier_price_list')
    op.drop_table('supplier_price_list')
