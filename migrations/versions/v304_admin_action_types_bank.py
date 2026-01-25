"""Add bank import AdminActionType values

Revision ID: v304_admin_action_types_bank
Revises: v303_billing_enhancement
Create Date: 2026-01-24

Adds new AdminActionType enum values for bank import functionality:
- BANK_IMPORT
- BANK_IMPORT_PROCESS
- BANK_IMPORT_DELETE
- MANUAL_MATCH
- UNMATCH
- IGNORE_TRANSACTION
- UNIGNORE_TRANSACTION
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'v304_admin_action_types_bank'
down_revision = 'v303_billing_enhancement'
branch_labels = None
depends_on = None


def upgrade():
    # Add new values to adminactiontype enum
    # PostgreSQL ENUM types need ALTER TYPE to add new values
    op.execute("ALTER TYPE adminactiontype ADD VALUE IF NOT EXISTS 'BANK_IMPORT'")
    op.execute("ALTER TYPE adminactiontype ADD VALUE IF NOT EXISTS 'BANK_IMPORT_PROCESS'")
    op.execute("ALTER TYPE adminactiontype ADD VALUE IF NOT EXISTS 'BANK_IMPORT_DELETE'")
    op.execute("ALTER TYPE adminactiontype ADD VALUE IF NOT EXISTS 'MANUAL_MATCH'")
    op.execute("ALTER TYPE adminactiontype ADD VALUE IF NOT EXISTS 'UNMATCH'")
    op.execute("ALTER TYPE adminactiontype ADD VALUE IF NOT EXISTS 'IGNORE_TRANSACTION'")
    op.execute("ALTER TYPE adminactiontype ADD VALUE IF NOT EXISTS 'UNIGNORE_TRANSACTION'")


def downgrade():
    # PostgreSQL does not support removing values from ENUM types
    # The values will remain but won't be used after downgrade
    pass