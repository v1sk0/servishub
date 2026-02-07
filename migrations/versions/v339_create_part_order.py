"""Create PartOrderRequest and PartOrderMessage tables

Revision ID: v339_part_order
Revises: v338_supplier_price_list
Create Date: 2026-02-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v339_part_order'
down_revision = 'v338_supplier_price_list'
branch_labels = None
depends_on = None


def upgrade():
    """Create part_order_request and part_order_message tables."""

    # PartOrderRequest
    op.create_table(
        'part_order_request',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('order_number', sa.String(20), unique=True, nullable=False),
        sa.Column('order_date', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        # Participants
        sa.Column('buyer_tenant_id', sa.Integer(), sa.ForeignKey('tenant.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('supplier_tenant_id', sa.Integer(), sa.ForeignKey('tenant.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('price_list_item_id', sa.BigInteger(), sa.ForeignKey('supplier_price_list_item.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('service_ticket_id', sa.BigInteger(), sa.ForeignKey('service_ticket.id', ondelete='SET NULL')),
        # Order details
        sa.Column('quantity', sa.Integer(), server_default='1', nullable=False),
        sa.Column('unit_price', sa.Numeric(10, 2), nullable=False),
        sa.Column('currency', sa.String(3), server_default='RSD'),
        sa.Column('total_amount', sa.Numeric(12, 2), nullable=False),
        # Status
        sa.Column('status', sa.String(20), server_default='PENDING', nullable=False),
        # Notes
        sa.Column('buyer_notes', sa.Text()),
        sa.Column('supplier_notes', sa.Text()),
        sa.Column('reject_reason', sa.String(255)),
        # Credits
        sa.Column('credit_charged', sa.Boolean(), server_default='false'),
        sa.Column('credit_amount_buyer', sa.Numeric(5, 2)),
        sa.Column('credit_amount_supplier', sa.Numeric(5, 2)),
        sa.Column('credit_charged_at', sa.DateTime()),
        # Delivery (will be populated after v345)
        sa.Column('delivery_option_id', sa.Integer()),
        sa.Column('delivery_option_name', sa.String(100)),
        sa.Column('delivery_cost', sa.Numeric(10, 2), server_default='0'),
        sa.Column('estimated_delivery_date', sa.Date()),
        sa.Column('actual_delivery_date', sa.Date()),
        # Audit
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('tenant_user.id', ondelete='SET NULL'), nullable=False),
        sa.Column('confirmed_by_id', sa.Integer(), sa.ForeignKey('tenant_user.id', ondelete='SET NULL')),
        sa.Column('confirmed_at', sa.DateTime()),
        sa.Column('completed_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_part_order_req_buyer', 'part_order_request', ['buyer_tenant_id'])
    op.create_index('ix_part_order_req_supplier', 'part_order_request', ['supplier_tenant_id'])
    op.create_index('ix_part_order_req_status', 'part_order_request', ['status'])
    op.create_index('ix_part_order_req_date', 'part_order_request', ['order_date'])

    # MarketplaceOrderMessage
    op.create_table(
        'marketplace_order_message',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('part_order_request.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sender_tenant_id', sa.Integer(), sa.ForeignKey('tenant.id', ondelete='SET NULL'), nullable=False),
        sa.Column('sender_user_id', sa.Integer(), sa.ForeignKey('tenant_user.id', ondelete='SET NULL')),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('message_type', sa.String(20), server_default='text'),
        sa.Column('is_read', sa.Boolean(), server_default='false'),
        sa.Column('read_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_marketplace_order_message_order', 'marketplace_order_message', ['order_id'])


def downgrade():
    """Drop marketplace_order_message and part_order_request tables."""
    op.drop_index('ix_marketplace_order_message_order', 'marketplace_order_message')
    op.drop_table('marketplace_order_message')

    op.drop_index('ix_part_order_req_date', 'part_order_request')
    op.drop_index('ix_part_order_req_status', 'part_order_request')
    op.drop_index('ix_part_order_req_supplier', 'part_order_request')
    op.drop_index('ix_part_order_req_buyer', 'part_order_request')
    op.drop_table('part_order_request')
