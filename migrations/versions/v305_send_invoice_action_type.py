"""Add SEND_INVOICE AdminActionType value

Revision ID: v305_send_invoice_action_type
Revises: v304_admin_action_types_bank
Create Date: 2026-01-25

Adds new AdminActionType enum value for sending invoices via email:
- SEND_INVOICE
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'v305_send_invoice_action_type'
down_revision = 'v304_admin_action_types_bank'
branch_labels = None
depends_on = None


def upgrade():
    # Add new value to adminactiontype enum
    # PostgreSQL ENUM types need ALTER TYPE to add new values
    op.execute("ALTER TYPE adminactiontype ADD VALUE IF NOT EXISTS 'SEND_INVOICE'")


def downgrade():
    # PostgreSQL does not support removing values from ENUM types
    # The value will remain but won't be used after downgrade
    pass
