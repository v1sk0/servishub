"""Create BuybackContract and BuybackContractItem tables

Revision ID: v332_buyback_contract
Revises: v331_simple_supplier
Create Date: 2026-02-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v332_buyback_contract'
down_revision = 'v331_simple_supplier'
branch_labels = None
depends_on = None


def upgrade():
    """Create buyback_contract and buyback_contract_item tables."""
    # BuybackContract - otkupni ugovor za fizička lica
    op.create_table(
        'buyback_contract',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenant.id', ondelete='CASCADE'), nullable=False),
        sa.Column('location_id', sa.Integer(), sa.ForeignKey('service_location.id', ondelete='SET NULL')),
        sa.Column('contract_number', sa.String(20), unique=True, nullable=False),
        sa.Column('contract_date', sa.Date(), nullable=False),
        # Podaci o prodavcu (fizičko lice)
        sa.Column('seller_name', sa.String(200), nullable=False),
        sa.Column('seller_jmbg', sa.String(13), nullable=False),
        sa.Column('seller_id_card', sa.String(20), nullable=False),
        sa.Column('seller_id_issued_by', sa.String(100)),
        sa.Column('seller_address', sa.Text(), nullable=False),
        sa.Column('seller_city', sa.String(100)),
        sa.Column('seller_phone', sa.String(50)),
        # Veza ka SimpleSupplier za ponovne otkupe
        sa.Column('supplier_id', sa.Integer(), sa.ForeignKey('simple_supplier.id', ondelete='SET NULL')),
        # Iznos
        sa.Column('total_amount', sa.Numeric(12, 2), server_default='0'),
        sa.Column('currency', sa.String(3), server_default='RSD'),
        # Način isplate
        sa.Column('payment_method', sa.String(20), server_default='CASH'),
        sa.Column('bank_account', sa.String(50)),
        # Status workflow
        sa.Column('status', sa.String(20), server_default='DRAFT', nullable=False),
        sa.Column('signed_at', sa.DateTime()),
        sa.Column('paid_at', sa.DateTime()),
        sa.Column('cancelled_at', sa.DateTime()),
        sa.Column('cancel_reason', sa.String(255)),
        # Audit
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('tenant_user.id'), nullable=False),
        sa.Column('signed_by_id', sa.Integer(), sa.ForeignKey('tenant_user.id')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('notes', sa.Text()),
    )
    op.create_index('ix_buyback_contract_tenant', 'buyback_contract', ['tenant_id'])
    op.create_index('ix_buyback_contract_status', 'buyback_contract', ['status'])
    op.create_index('ix_buyback_contract_date', 'buyback_contract', ['contract_date'])

    # BuybackContractItem - stavka otkupnog ugovora
    op.create_table(
        'buyback_contract_item',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('contract_id', sa.Integer(), sa.ForeignKey('buyback_contract.id', ondelete='CASCADE'), nullable=False),
        # Opis artikla
        sa.Column('item_description', sa.String(300), nullable=False),
        sa.Column('brand', sa.String(100)),
        sa.Column('model', sa.String(100)),
        # Identifikatori
        sa.Column('imei', sa.String(20)),
        sa.Column('serial_number', sa.String(50)),
        # Količina i cena
        sa.Column('quantity', sa.Integer(), server_default='1', nullable=False),
        sa.Column('unit_price', sa.Numeric(10, 2), nullable=False),
        sa.Column('line_total', sa.Numeric(12, 2), nullable=False),
        # Stanje i tip artikla
        sa.Column('condition', sa.String(20), server_default='USED'),
        sa.Column('item_type', sa.String(20), server_default='SPARE_PART'),
        sa.Column('part_category', sa.String(30)),
        # Link ka kreiranom artiklu posle potpisivanja
        sa.Column('spare_part_id', sa.BigInteger(), sa.ForeignKey('spare_part.id', ondelete='SET NULL')),
        sa.Column('goods_item_id', sa.Integer(), sa.ForeignKey('goods_item.id', ondelete='SET NULL')),
        sa.Column('phone_listing_id', sa.BigInteger(), sa.ForeignKey('phone_listing.id', ondelete='SET NULL')),
    )
    op.create_index('ix_buyback_contract_item_contract', 'buyback_contract_item', ['contract_id'])


def downgrade():
    """Drop buyback_contract_item and buyback_contract tables."""
    op.drop_index('ix_buyback_contract_item_contract', 'buyback_contract_item')
    op.drop_table('buyback_contract_item')
    op.drop_index('ix_buyback_contract_date', 'buyback_contract')
    op.drop_index('ix_buyback_contract_status', 'buyback_contract')
    op.drop_index('ix_buyback_contract_tenant', 'buyback_contract')
    op.drop_table('buyback_contract')
