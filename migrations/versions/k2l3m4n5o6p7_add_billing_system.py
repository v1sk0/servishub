"""Add billing system - tenant billing fields, tenant_message table, subscription_payment updates

Revision ID: k2l3m4n5o6p7
Revises: j1k2l3m4n5o6
Create Date: 2026-01-16 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'k2l3m4n5o6p7'
down_revision = 'j1k2l3m4n5o6'
branch_labels = None
depends_on = None


def upgrade():
    # ============================================
    # 1. TENANT TABLE - New billing/trust fields
    # ============================================

    # Billing - Dugovanje i placanje
    op.add_column('tenant', sa.Column('current_debt', sa.Numeric(10, 2), server_default='0'))
    op.add_column('tenant', sa.Column('last_payment_at', sa.DateTime(), nullable=True))
    op.add_column('tenant', sa.Column('days_overdue', sa.Integer(), server_default='0'))

    # Blokada
    op.add_column('tenant', sa.Column('blocked_at', sa.DateTime(), nullable=True))
    op.add_column('tenant', sa.Column('block_reason', sa.String(200), nullable=True))

    # Trust Score
    op.add_column('tenant', sa.Column('trust_score', sa.Integer(), server_default='100'))
    op.add_column('tenant', sa.Column('trust_activated_at', sa.DateTime(), nullable=True))
    op.add_column('tenant', sa.Column('trust_activation_count', sa.Integer(), server_default='0'))
    op.add_column('tenant', sa.Column('last_trust_activation_period', sa.String(7), nullable=True))
    op.add_column('tenant', sa.Column('consecutive_on_time_payments', sa.Integer(), server_default='0'))

    # Custom cene
    op.add_column('tenant', sa.Column('custom_base_price', sa.Numeric(10, 2), nullable=True))
    op.add_column('tenant', sa.Column('custom_location_price', sa.Numeric(10, 2), nullable=True))
    op.add_column('tenant', sa.Column('custom_price_reason', sa.String(200), nullable=True))
    op.add_column('tenant', sa.Column('custom_price_valid_from', sa.Date(), nullable=True))

    # ============================================
    # 2. SUBSCRIPTION_PAYMENT TABLE - New fields
    # ============================================

    # Make invoice_number unique (if not already)
    op.add_column('subscription_payment', sa.Column('due_date', sa.Date(), nullable=True))
    op.add_column('subscription_payment', sa.Column('discount_reason', sa.String(200), nullable=True))
    op.add_column('subscription_payment', sa.Column('paid_at', sa.DateTime(), nullable=True))
    op.add_column('subscription_payment', sa.Column('payment_notes', sa.Text(), nullable=True))
    op.add_column('subscription_payment', sa.Column('is_auto_generated', sa.Boolean(), server_default='true'))
    op.add_column('subscription_payment', sa.Column('updated_at', sa.DateTime(), nullable=True))

    # Change period columns from DateTime to Date (if possible)
    # Note: This might fail if there's existing data - handle in production
    try:
        op.alter_column('subscription_payment', 'period_start',
                        type_=sa.Date(),
                        existing_type=sa.DateTime(),
                        nullable=True)
        op.alter_column('subscription_payment', 'period_end',
                        type_=sa.Date(),
                        existing_type=sa.DateTime(),
                        nullable=True)
    except Exception:
        pass  # Ignore if column type change fails

    # Create index if not exists
    try:
        op.create_index('ix_subscription_payment_invoice_number', 'subscription_payment', ['invoice_number'], unique=True)
    except Exception:
        pass

    try:
        op.create_index('ix_subscription_payment_tenant_status', 'subscription_payment', ['tenant_id', 'status'])
    except Exception:
        pass

    # ============================================
    # 3. TENANT_MESSAGE TABLE - Create new table
    # ============================================

    # Create enums only if they don't exist
    conn = op.get_bind()

    # Check and create MessageType enum
    result = conn.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'messagetype'"))
    if not result.fetchone():
        op.execute("CREATE TYPE messagetype AS ENUM ('SYSTEM', 'ADMIN', 'TENANT', 'SUPPLIER')")

    # Check and create MessagePriority enum
    result = conn.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'messagepriority'"))
    if not result.fetchone():
        op.execute("CREATE TYPE messagepriority AS ENUM ('LOW', 'NORMAL', 'HIGH', 'URGENT')")

    # Check and create MessageCategory enum
    result = conn.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'messagecategory'"))
    if not result.fetchone():
        op.execute("CREATE TYPE messagecategory AS ENUM ('BILLING', 'PACKAGE_CHANGE', 'SYSTEM', 'SUPPORT', 'ANNOUNCEMENT', 'OTHER')")

    # Check if table already exists
    result = conn.execute(sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = 'tenant_message'"))
    if not result.fetchone():
        # Use raw SQL to create table with existing enum types
        # This avoids SQLAlchemy trying to recreate enum types
        op.execute("""
            CREATE TABLE tenant_message (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
                message_type messagetype NOT NULL,
                sender_admin_id INTEGER REFERENCES platform_admin(id) ON DELETE SET NULL,
                sender_tenant_id INTEGER REFERENCES tenant(id) ON DELETE SET NULL,
                subject VARCHAR(200) NOT NULL,
                body TEXT NOT NULL,
                action_url VARCHAR(500),
                action_label VARCHAR(100),
                priority messagepriority NOT NULL DEFAULT 'NORMAL',
                category messagecategory NOT NULL DEFAULT 'SYSTEM',
                is_read BOOLEAN NOT NULL DEFAULT false,
                read_at TIMESTAMP,
                read_by_user_id INTEGER REFERENCES tenant_user(id) ON DELETE SET NULL,
                related_payment_id BIGINT REFERENCES subscription_payment(id) ON DELETE SET NULL,
                is_deleted BOOLEAN NOT NULL DEFAULT false,
                deleted_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT now()
            )
        """)

        # Create indexes
        op.execute("CREATE INDEX ix_tenant_message_tenant_id ON tenant_message(tenant_id)")
        op.execute("CREATE INDEX ix_tenant_message_is_read ON tenant_message(is_read)")
        op.execute("CREATE INDEX ix_tenant_message_category ON tenant_message(category)")
        op.execute("CREATE INDEX ix_tenant_message_created_at ON tenant_message(created_at)")
        op.execute("CREATE INDEX ix_tenant_message_unread ON tenant_message(tenant_id, is_read, is_deleted)")

    # ============================================
    # 4. ADMIN_ACTION_TYPE ENUM - Add new values
    # ============================================

    # Add new enum values for billing actions
    op.execute("ALTER TYPE adminactiontype ADD VALUE IF NOT EXISTS 'GENERATE_INVOICE'")
    op.execute("ALTER TYPE adminactiontype ADD VALUE IF NOT EXISTS 'VERIFY_PAYMENT'")
    op.execute("ALTER TYPE adminactiontype ADD VALUE IF NOT EXISTS 'REJECT_PAYMENT'")
    op.execute("ALTER TYPE adminactiontype ADD VALUE IF NOT EXISTS 'BLOCK_TENANT'")
    op.execute("ALTER TYPE adminactiontype ADD VALUE IF NOT EXISTS 'UNBLOCK_TENANT'")
    op.execute("ALTER TYPE adminactiontype ADD VALUE IF NOT EXISTS 'UPDATE_PRICING'")
    op.execute("ALTER TYPE adminactiontype ADD VALUE IF NOT EXISTS 'TRUST_ACTIVATE'")
    op.execute("ALTER TYPE adminactiontype ADD VALUE IF NOT EXISTS 'TRUST_EXPIRED'")
    op.execute("ALTER TYPE adminactiontype ADD VALUE IF NOT EXISTS 'UPDATE_TRUST_SCORE'")
    op.execute("ALTER TYPE adminactiontype ADD VALUE IF NOT EXISTS 'SEND_MESSAGE'")


def downgrade():
    # Drop tenant_message table
    op.drop_index('ix_tenant_message_unread', table_name='tenant_message')
    op.drop_index('ix_tenant_message_created_at', table_name='tenant_message')
    op.drop_index('ix_tenant_message_category', table_name='tenant_message')
    op.drop_index('ix_tenant_message_is_read', table_name='tenant_message')
    op.drop_index('ix_tenant_message_tenant_id', table_name='tenant_message')
    op.drop_table('tenant_message')

    # Drop enums
    op.execute("DROP TYPE IF EXISTS messagecategory")
    op.execute("DROP TYPE IF EXISTS messagepriority")
    op.execute("DROP TYPE IF EXISTS messagetype")

    # Remove subscription_payment columns
    op.drop_column('subscription_payment', 'updated_at')
    op.drop_column('subscription_payment', 'is_auto_generated')
    op.drop_column('subscription_payment', 'payment_notes')
    op.drop_column('subscription_payment', 'paid_at')
    op.drop_column('subscription_payment', 'discount_reason')
    op.drop_column('subscription_payment', 'due_date')

    # Remove tenant columns
    op.drop_column('tenant', 'custom_price_valid_from')
    op.drop_column('tenant', 'custom_price_reason')
    op.drop_column('tenant', 'custom_location_price')
    op.drop_column('tenant', 'custom_base_price')
    op.drop_column('tenant', 'consecutive_on_time_payments')
    op.drop_column('tenant', 'last_trust_activation_period')
    op.drop_column('tenant', 'trust_activation_count')
    op.drop_column('tenant', 'trust_activated_at')
    op.drop_column('tenant', 'trust_score')
    op.drop_column('tenant', 'block_reason')
    op.drop_column('tenant', 'blocked_at')
    op.drop_column('tenant', 'days_overdue')
    op.drop_column('tenant', 'last_payment_at')
    op.drop_column('tenant', 'current_debt')

    # Note: Cannot remove enum values in PostgreSQL easily