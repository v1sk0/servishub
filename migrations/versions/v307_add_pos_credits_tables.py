"""Add POS, Credits, and SparePartUsage tables.

Revision ID: v307_pos_credits_tables
Revises: ac2742c5b2f8
Create Date: 2026-01-27 19:20:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v307_pos_credits_tables'
down_revision = 'ac2742c5b2f8'
branch_labels = None
depends_on = None


def upgrade():
    # ==========================================
    # POS Tables
    # ==========================================

    op.create_table('cash_register_session',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('opened_by_id', sa.Integer(), nullable=True),
        sa.Column('opened_at', sa.DateTime(), nullable=True),
        sa.Column('opening_cash', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('closed_by_id', sa.Integer(), nullable=True),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.Column('closing_cash', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('expected_cash', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('cash_difference', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('status', sa.Enum('OPEN', 'CLOSED', name='cashregisterstatus'), nullable=False),
        sa.Column('total_revenue', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('total_cost', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('total_profit', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('total_cash', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('total_card', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('total_transfer', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('receipt_count', sa.Integer(), nullable=True),
        sa.Column('voided_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['location_id'], ['service_location.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['opened_by_id'], ['tenant_user.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['closed_by_id'], ['tenant_user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'location_id', 'date', name='uq_session_tenant_location_date')
    )
    op.create_index('ix_cash_register_session_tenant_id', 'cash_register_session', ['tenant_id'])
    op.create_index('ix_cash_register_session_location_id', 'cash_register_session', ['location_id'])
    op.create_index('ix_cash_register_session_date', 'cash_register_session', ['date'])

    op.create_table('receipt',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=True),
        sa.Column('receipt_number', sa.String(length=50), nullable=False),
        sa.Column('receipt_type', sa.Enum('SALE', 'REFUND', name='receipttype'), nullable=False),
        sa.Column('original_receipt_id', sa.BigInteger(), nullable=True),
        sa.Column('status', sa.Enum('DRAFT', 'ISSUED', 'VOIDED', 'REFUNDED', name='receiptstatus'), nullable=False),
        sa.Column('customer_name', sa.String(length=200), nullable=True),
        sa.Column('customer_phone', sa.String(length=30), nullable=True),
        sa.Column('customer_pib', sa.String(length=20), nullable=True),
        sa.Column('subtotal', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('discount_amount', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('total_amount', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('total_cost', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('profit', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('payment_method', sa.Enum('CASH', 'CARD', 'TRANSFER', 'MIXED', name='paymentmethod'), nullable=True),
        sa.Column('cash_received', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('cash_change', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('card_amount', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('transfer_amount', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('service_ticket_id', sa.Integer(), nullable=True),
        sa.Column('issued_by_id', sa.Integer(), nullable=True),
        sa.Column('issued_at', sa.DateTime(), nullable=True),
        sa.Column('voided_by_id', sa.Integer(), nullable=True),
        sa.Column('voided_at', sa.DateTime(), nullable=True),
        sa.Column('void_reason', sa.String(length=300), nullable=True),
        sa.Column('fiscal_invoice_number', sa.String(length=100), nullable=True),
        sa.Column('fiscal_signature', sa.Text(), nullable=True),
        sa.Column('fiscal_sent_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_id'], ['cash_register_session.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['original_receipt_id'], ['receipt.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['service_ticket_id'], ['service_ticket.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['issued_by_id'], ['tenant_user.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['voided_by_id'], ['tenant_user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'receipt_number', name='uq_receipt_tenant_number')
    )
    op.create_index('ix_receipt_tenant_id', 'receipt', ['tenant_id'])
    op.create_index('ix_receipt_session_id', 'receipt', ['session_id'])
    op.create_index('ix_receipt_status', 'receipt', ['status'])

    op.create_table('receipt_item',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('receipt_id', sa.BigInteger(), nullable=False),
        sa.Column('item_type', sa.Enum('PHONE', 'SPARE_PART', 'SERVICE', 'TICKET', 'CUSTOM', name='saleitemtype'), nullable=False),
        sa.Column('item_name', sa.String(length=300), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('phone_listing_id', sa.Integer(), nullable=True),
        sa.Column('spare_part_id', sa.Integer(), nullable=True),
        sa.Column('service_item_id', sa.Integer(), nullable=True),
        sa.Column('service_ticket_id', sa.Integer(), nullable=True),
        sa.Column('purchase_price', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('unit_price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('discount_pct', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('line_total', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('line_cost', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('line_profit', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.ForeignKeyConstraint(['receipt_id'], ['receipt.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['phone_listing_id'], ['phone_listing.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['spare_part_id'], ['spare_part.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['service_item_id'], ['service_item.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['service_ticket_id'], ['service_ticket.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_receipt_item_receipt_id', 'receipt_item', ['receipt_id'])

    op.create_table('daily_report',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('total_revenue', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('total_cost', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('total_profit', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('profit_margin_pct', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('total_cash', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('total_card', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('total_transfer', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('opening_cash', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('closing_cash', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('cash_difference', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('receipt_count', sa.Integer(), nullable=True),
        sa.Column('voided_count', sa.Integer(), nullable=True),
        sa.Column('items_sold', sa.Integer(), nullable=True),
        sa.Column('phones_sold', sa.Integer(), nullable=True),
        sa.Column('parts_sold', sa.Integer(), nullable=True),
        sa.Column('services_sold', sa.Integer(), nullable=True),
        sa.Column('top_items_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['location_id'], ['service_location.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_id'], ['cash_register_session.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'location_id', 'date', name='uq_daily_report_tenant_location_date')
    )
    op.create_index('ix_daily_report_tenant_id', 'daily_report', ['tenant_id'])
    op.create_index('ix_daily_report_location_id', 'daily_report', ['location_id'])
    op.create_index('ix_daily_report_date', 'daily_report', ['date'])

    # ==========================================
    # Credits Tables
    # ==========================================

    op.create_table('promo_code',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('discount_type', sa.Enum('percent', 'fixed_credits', 'fixed_eur', name='discounttype'), nullable=False),
        sa.Column('discount_value', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('min_purchase_eur', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('max_uses_total', sa.Integer(), nullable=True),
        sa.Column('max_uses_per_user', sa.Integer(), nullable=True),
        sa.Column('valid_for', sa.JSON(), nullable=True),
        sa.Column('valid_from', sa.DateTime(), nullable=True),
        sa.Column('valid_until', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('times_used', sa.Integer(), nullable=False),
        sa.Column('total_discount_given', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_promo_code_code', 'promo_code', ['code'], unique=True)

    op.create_table('credit_balance',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('owner_type', sa.Enum('tenant', 'supplier', 'public_user', name='ownertype'), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('supplier_id', sa.Integer(), nullable=True),  # FK deferred - supplier table TBD
        sa.Column('public_user_id', sa.BigInteger(), nullable=True),  # FK deferred - public_user table TBD
        sa.Column('balance', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('total_purchased', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('total_spent', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('total_received_free', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('low_balance_threshold', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('low_balance_alert_sent', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ondelete='CASCADE'),
        # supplier and public_user FKs deferred until those tables exist
        sa.CheckConstraint('balance >= 0', name='check_balance_non_negative'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('owner_type', 'tenant_id', name='uq_credit_balance_tenant'),
        sa.UniqueConstraint('owner_type', 'supplier_id', name='uq_credit_balance_supplier'),
        sa.UniqueConstraint('owner_type', 'public_user_id', name='uq_credit_balance_public_user')
    )
    op.create_index('ix_credit_balance_owner_type', 'credit_balance', ['owner_type'])
    op.create_index('ix_credit_balance_tenant_id', 'credit_balance', ['tenant_id'])
    op.create_index('ix_credit_balance_supplier_id', 'credit_balance', ['supplier_id'])
    op.create_index('ix_credit_balance_public_user_id', 'credit_balance', ['public_user_id'])

    op.create_table('credit_transaction',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('credit_balance_id', sa.Integer(), nullable=False),
        sa.Column('transaction_type', sa.Enum('PURCHASE', 'WELCOME', 'PROMO', 'CONNECTION_FEE', 'FEATURED', 'PREMIUM', 'BOOST', 'REFUND', 'CHARGEBACK', 'ADMIN', name='credittransactiontype'), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('balance_before', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('balance_after', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('reference_type', sa.String(length=50), nullable=True),
        sa.Column('reference_id', sa.Integer(), nullable=True),
        sa.Column('idempotency_key', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['credit_balance_id'], ['credit_balance.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key', name='uq_transaction_idempotency')
    )
    op.create_index('ix_credit_transaction_credit_balance_id', 'credit_transaction', ['credit_balance_id'])
    op.create_index('ix_credit_transaction_transaction_type', 'credit_transaction', ['transaction_type'])
    op.create_index('ix_credit_transaction_created_at', 'credit_transaction', ['created_at'])

    op.create_table('credit_purchase',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('credit_balance_id', sa.Integer(), nullable=False),
        sa.Column('package_code', sa.String(length=50), nullable=False),
        sa.Column('credits_amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('price_eur', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('price_rsd', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('discount_percent', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('promo_code_id', sa.Integer(), nullable=True),
        sa.Column('promo_discount', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('payment_method', sa.String(length=50), nullable=True),
        sa.Column('payment_status', sa.Enum('pending', 'completed', 'failed', 'refunded', name='creditpaymentstatus'), nullable=False),
        sa.Column('payment_reference', sa.String(length=255), nullable=True),
        sa.Column('idempotency_key', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['credit_balance_id'], ['credit_balance.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['promo_code_id'], ['promo_code.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key', name='uq_purchase_idempotency')
    )
    op.create_index('ix_credit_purchase_credit_balance_id', 'credit_purchase', ['credit_balance_id'])
    op.create_index('ix_credit_purchase_payment_status', 'credit_purchase', ['payment_status'])

    # ==========================================
    # SparePartUsage Table
    # ==========================================

    op.create_table('spare_part_usage',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('service_ticket_id', sa.BigInteger(), nullable=False),
        sa.Column('spare_part_id', sa.BigInteger(), nullable=False),
        sa.Column('quantity_used', sa.Integer(), nullable=False),
        sa.Column('unit_price', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=True),
        sa.Column('added_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['service_ticket_id'], ['service_ticket.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['spare_part_id'], ['spare_part.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['added_by_id'], ['tenant_user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('service_ticket_id', 'spare_part_id', name='uq_usage_ticket_part')
    )
    op.create_index('ix_spare_part_usage_tenant_id', 'spare_part_usage', ['tenant_id'])


def downgrade():
    op.drop_table('spare_part_usage')
    op.drop_table('credit_purchase')
    op.drop_table('credit_transaction')
    op.drop_table('credit_balance')
    op.drop_table('promo_code')
    op.drop_table('daily_report')
    op.drop_table('receipt_item')
    op.drop_table('receipt')
    op.drop_table('cash_register_session')

    # Drop enums
    sa.Enum(name='cashregisterstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='receipttype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='receiptstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='paymentmethod').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='saleitemtype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='discounttype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='ownertype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='credittransactiontype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='creditpaymentstatus').drop(op.get_bind(), checkfirst=True)