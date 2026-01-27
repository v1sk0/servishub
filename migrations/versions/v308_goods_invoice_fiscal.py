"""v3.08: Add GoodsItem, PurchaseInvoice, StockAdjustment, PosAuditLog, fiscal fields

Revision ID: v308_goods_invoice_fiscal
Revises: v307_pos_credits_tables
Create Date: 2026-01-27 22:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'v308_goods_invoice_fiscal'
down_revision = 'v307_pos_credits_tables'
branch_labels = None
depends_on = None


def upgrade():
    # ==========================================
    # GoodsItem
    # ==========================================
    op.create_table('goods_item',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=300), nullable=False),
        sa.Column('barcode', sa.String(length=50), nullable=True),
        sa.Column('sku', sa.String(length=50), nullable=True),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('purchase_price', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('selling_price', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('default_margin_pct', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=True),
        sa.Column('current_stock', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('min_stock_level', sa.Integer(), nullable=True),
        sa.Column('tax_label', sa.String(length=1), nullable=True),
        sa.Column('unit_of_measure', sa.String(length=20), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['location_id'], ['service_location.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'barcode', name='uq_goods_tenant_barcode')
    )
    op.create_index('ix_goods_item_tenant_id', 'goods_item', ['tenant_id'])
    op.create_index('ix_goods_item_location_id', 'goods_item', ['location_id'])

    # ==========================================
    # PurchaseInvoice
    # ==========================================
    op.create_table('purchase_invoice',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=True),
        sa.Column('supplier_name', sa.String(length=200), nullable=False),
        sa.Column('supplier_pib', sa.String(length=20), nullable=True),
        sa.Column('invoice_number', sa.String(length=100), nullable=False),
        sa.Column('invoice_date', sa.Date(), nullable=False),
        sa.Column('received_date', sa.Date(), nullable=True),
        sa.Column('total_amount', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('received_by_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.Enum('DRAFT', 'RECEIVED', 'CANCELLED', name='invoicestatus'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['location_id'], ['service_location.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['received_by_id'], ['tenant_user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_purchase_invoice_tenant_id', 'purchase_invoice', ['tenant_id'])

    # ==========================================
    # PurchaseInvoiceItem
    # ==========================================
    op.create_table('purchase_invoice_item',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('invoice_id', sa.Integer(), nullable=False),
        sa.Column('goods_item_id', sa.Integer(), nullable=True),
        sa.Column('spare_part_id', sa.BigInteger(), nullable=True),
        sa.Column('item_name', sa.String(length=300), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('purchase_price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('selling_price', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('margin_pct', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('line_total', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.ForeignKeyConstraint(['invoice_id'], ['purchase_invoice.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['goods_item_id'], ['goods_item.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['spare_part_id'], ['spare_part.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_purchase_invoice_item_invoice_id', 'purchase_invoice_item', ['invoice_id'])

    # ==========================================
    # StockAdjustment
    # ==========================================
    op.create_table('stock_adjustment',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('goods_item_id', sa.Integer(), nullable=True),
        sa.Column('spare_part_id', sa.BigInteger(), nullable=True),
        sa.Column('adjustment_type', sa.Enum('WRITE_OFF', 'CORRECTION', 'DAMAGE', 'RETURN_TO_SUPPLIER', name='stockadjustmenttype'), nullable=False),
        sa.Column('quantity_change', sa.Integer(), nullable=False),
        sa.Column('stock_before', sa.Integer(), nullable=False),
        sa.Column('stock_after', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(length=500), nullable=True),
        sa.Column('adjusted_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['goods_item_id'], ['goods_item.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['spare_part_id'], ['spare_part.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['adjusted_by_id'], ['tenant_user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_stock_adjustment_tenant_id', 'stock_adjustment', ['tenant_id'])

    # ==========================================
    # PosAuditLog
    # ==========================================
    op.create_table('pos_audit_log',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('entity_id', sa.BigInteger(), nullable=True),
        sa.Column('details_json', sa.JSON(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['tenant_user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_pos_audit_log_tenant_id', 'pos_audit_log', ['tenant_id'])
    op.create_index('ix_pos_audit_log_action', 'pos_audit_log', ['action'])
    op.create_index('ix_pos_audit_log_created_at', 'pos_audit_log', ['created_at'])

    # ==========================================
    # ALTER: CashRegisterSession — fiscal_mode
    # ==========================================
    op.add_column('cash_register_session',
        sa.Column('fiscal_mode', sa.Boolean(), server_default='false')
    )

    # ==========================================
    # ALTER: Receipt — fiscal fields, idempotency, buyer
    # ==========================================
    op.add_column('receipt', sa.Column('fiscal_status', sa.String(length=20), nullable=True))
    op.add_column('receipt', sa.Column('fiscal_response_json', sa.JSON(), nullable=True))
    op.add_column('receipt', sa.Column('fiscal_retry_count', sa.Integer(), server_default='0'))
    op.add_column('receipt', sa.Column('fiscal_error_code', sa.String(length=50), nullable=True))
    op.add_column('receipt', sa.Column('fiscal_qr_code', sa.Text(), nullable=True))
    op.add_column('receipt', sa.Column('idempotency_key', sa.String(length=255), nullable=True))
    op.add_column('receipt', sa.Column('buyer_pib', sa.String(length=20), nullable=True))
    op.add_column('receipt', sa.Column('buyer_name', sa.String(length=200), nullable=True))
    op.create_unique_constraint('uq_receipt_idempotency', 'receipt', ['idempotency_key'])

    # ==========================================
    # ALTER: ReceiptItem — goods_item_id
    # ==========================================
    op.add_column('receipt_item',
        sa.Column('goods_item_id', sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        'fk_receipt_item_goods_item', 'receipt_item', 'goods_item',
        ['goods_item_id'], ['id'], ondelete='SET NULL'
    )

    # ==========================================
    # ALTER: SaleItemType enum — add GOODS
    # ==========================================
    # PostgreSQL: dodaj novu vrednost u postojeći enum
    op.execute("ALTER TYPE saleitemtype ADD VALUE IF NOT EXISTS 'GOODS'")

    # ==========================================
    # ALTER: ServiceLocation — fiscal config
    # ==========================================
    op.add_column('service_location', sa.Column('fiscal_mode', sa.Boolean(), server_default='false'))
    op.add_column('service_location', sa.Column('pfr_url', sa.String(length=255), nullable=True))
    op.add_column('service_location', sa.Column('pfr_type', sa.String(length=10), nullable=True))
    op.add_column('service_location', sa.Column('business_unit_code', sa.String(length=50), nullable=True))
    op.add_column('service_location', sa.Column('device_code', sa.String(length=50), nullable=True))
    op.add_column('service_location', sa.Column('company_pib', sa.String(length=20), nullable=True))
    op.add_column('service_location', sa.Column('company_name', sa.String(length=200), nullable=True))
    op.add_column('service_location', sa.Column('company_address', sa.String(length=300), nullable=True))


def downgrade():
    # ServiceLocation fiscal columns
    op.drop_column('service_location', 'company_address')
    op.drop_column('service_location', 'company_name')
    op.drop_column('service_location', 'company_pib')
    op.drop_column('service_location', 'device_code')
    op.drop_column('service_location', 'business_unit_code')
    op.drop_column('service_location', 'pfr_type')
    op.drop_column('service_location', 'pfr_url')
    op.drop_column('service_location', 'fiscal_mode')

    # ReceiptItem goods_item_id
    op.drop_constraint('fk_receipt_item_goods_item', 'receipt_item', type_='foreignkey')
    op.drop_column('receipt_item', 'goods_item_id')

    # Receipt fiscal fields
    op.drop_constraint('uq_receipt_idempotency', 'receipt', type_='unique')
    op.drop_column('receipt', 'buyer_name')
    op.drop_column('receipt', 'buyer_pib')
    op.drop_column('receipt', 'idempotency_key')
    op.drop_column('receipt', 'fiscal_qr_code')
    op.drop_column('receipt', 'fiscal_error_code')
    op.drop_column('receipt', 'fiscal_retry_count')
    op.drop_column('receipt', 'fiscal_response_json')
    op.drop_column('receipt', 'fiscal_status')

    # CashRegisterSession
    op.drop_column('cash_register_session', 'fiscal_mode')

    # Drop tables
    op.drop_table('pos_audit_log')
    op.drop_table('stock_adjustment')
    op.drop_table('purchase_invoice_item')
    op.drop_table('purchase_invoice')
    op.drop_table('goods_item')

    # Drop enums
    sa.Enum(name='stockadjustmenttype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='invoicestatus').drop(op.get_bind(), checkfirst=True)
    # Note: Cannot remove 'GOODS' from saleitemtype enum in PostgreSQL