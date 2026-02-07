"""v570: Add supplier action types to AdminActionType enum

Revision ID: v570_add_supplier_action_types
Revises: v346_add_order_delivery_fk
Create Date: 2026-02-07

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'v570_supplier_action_types'
down_revision = 'v346_order_delivery_fk'
branch_labels = None
depends_on = None


def upgrade():
    """Add new supplier action types to adminactiontype enum."""
    # Add new values to the PostgreSQL enum type
    # PostgreSQL requires ALTER TYPE to add new enum values

    # Add each new value
    op.execute("ALTER TYPE adminactiontype ADD VALUE IF NOT EXISTS 'CREATE_SUPPLIER'")
    op.execute("ALTER TYPE adminactiontype ADD VALUE IF NOT EXISTS 'UPDATE_SUPPLIER'")
    op.execute("ALTER TYPE adminactiontype ADD VALUE IF NOT EXISTS 'VERIFY_SUPPLIER'")
    op.execute("ALTER TYPE adminactiontype ADD VALUE IF NOT EXISTS 'SUSPEND_SUPPLIER'")
    op.execute("ALTER TYPE adminactiontype ADD VALUE IF NOT EXISTS 'ACTIVATE_SUPPLIER'")
    op.execute("ALTER TYPE adminactiontype ADD VALUE IF NOT EXISTS 'CREATE_SUPPLIER_USER'")
    op.execute("ALTER TYPE adminactiontype ADD VALUE IF NOT EXISTS 'UPDATE_SUPPLIER_USER'")


def downgrade():
    """
    Note: PostgreSQL does not support removing values from enum types.
    The values will remain in the enum but won't be used.
    To fully remove, you would need to recreate the enum type.
    """
    pass
