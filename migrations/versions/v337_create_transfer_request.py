"""Create TransferRequest and TransferRequestItem tables

Revision ID: v337_transfer_request
Revises: v334_stock_movement
Create Date: 2026-02-06

TransferRequest omogućava transfer robe između lokacija istog tenanta.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v337_transfer_request'
down_revision = 'v334_stock_movement'
branch_labels = None
depends_on = None


def upgrade():
    """Create transfer_request and transfer_request_item tables."""

    # TransferRequest - zahtev za transfer
    op.create_table(
        'transfer_request',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenant.id', ondelete='CASCADE'), nullable=False),
        sa.Column('request_number', sa.String(20), unique=True, nullable=False),
        sa.Column('request_date', sa.Date(), nullable=False),
        # Locations
        sa.Column('from_location_id', sa.Integer(), sa.ForeignKey('service_location.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('to_location_id', sa.Integer(), sa.ForeignKey('service_location.id', ondelete='RESTRICT'), nullable=False),
        # Status
        sa.Column('status', sa.String(20), server_default='PENDING', nullable=False),
        sa.Column('reason', sa.String(255)),
        sa.Column('notes', sa.Text()),
        # Request audit
        sa.Column('requested_by_id', sa.Integer(), sa.ForeignKey('tenant_user.id', ondelete='SET NULL'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        # Approval
        sa.Column('approved_by_id', sa.Integer(), sa.ForeignKey('tenant_user.id', ondelete='SET NULL')),
        sa.Column('approved_at', sa.DateTime()),
        sa.Column('rejected_reason', sa.String(255)),
        # Shipping
        sa.Column('shipped_at', sa.DateTime()),
        sa.Column('shipped_by_id', sa.Integer(), sa.ForeignKey('tenant_user.id', ondelete='SET NULL')),
        # Receipt
        sa.Column('received_at', sa.DateTime()),
        sa.Column('received_by_id', sa.Integer(), sa.ForeignKey('tenant_user.id', ondelete='SET NULL')),
    )

    # Constraint: from and to locations must be different
    op.create_check_constraint(
        'ck_transfer_diff_locations', 'transfer_request',
        'from_location_id != to_location_id'
    )

    # Indexes
    op.create_index('ix_transfer_request_tenant', 'transfer_request', ['tenant_id'])
    op.create_index('ix_transfer_request_from', 'transfer_request', ['from_location_id'])
    op.create_index('ix_transfer_request_to', 'transfer_request', ['to_location_id'])
    op.create_index('ix_transfer_request_status', 'transfer_request', ['status'])

    # TransferRequestItem - stavka zahteva
    op.create_table(
        'transfer_request_item',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('request_id', sa.Integer(), sa.ForeignKey('transfer_request.id', ondelete='CASCADE'), nullable=False),
        # Item references (one of two)
        sa.Column('goods_item_id', sa.Integer(), sa.ForeignKey('goods_item.id', ondelete='SET NULL')),
        sa.Column('spare_part_id', sa.BigInteger(), sa.ForeignKey('spare_part.id', ondelete='SET NULL')),
        # Quantities
        sa.Column('quantity_requested', sa.Integer(), nullable=False),
        sa.Column('quantity_approved', sa.Integer()),
        sa.Column('quantity_received', sa.Integer()),
        # Notes
        sa.Column('notes', sa.String(255)),
    )

    # Constraint: must have either goods_item_id or spare_part_id
    op.create_check_constraint(
        'ck_transfer_item_one', 'transfer_request_item',
        '(goods_item_id IS NOT NULL AND spare_part_id IS NULL) OR '
        '(goods_item_id IS NULL AND spare_part_id IS NOT NULL)'
    )

    op.create_index('ix_transfer_request_item_request', 'transfer_request_item', ['request_id'])


def downgrade():
    """Drop transfer_request_item and transfer_request tables."""
    op.drop_index('ix_transfer_request_item_request', 'transfer_request_item')
    op.drop_constraint('ck_transfer_item_one', 'transfer_request_item', type_='check')
    op.drop_table('transfer_request_item')

    op.drop_index('ix_transfer_request_status', 'transfer_request')
    op.drop_index('ix_transfer_request_to', 'transfer_request')
    op.drop_index('ix_transfer_request_from', 'transfer_request')
    op.drop_index('ix_transfer_request_tenant', 'transfer_request')
    op.drop_constraint('ck_transfer_diff_locations', 'transfer_request', type_='check')
    op.drop_table('transfer_request')
