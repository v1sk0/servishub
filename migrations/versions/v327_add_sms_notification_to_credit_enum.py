"""Add SMS_NOTIFICATION to credittransactiontype enum.

Revision ID: v327_sms_txn_enum
Revises: v326_sms_d7_cost_fields
Create Date: 2026-02-01

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'v327_sms_txn_enum'
down_revision = 'v326_sms_d7_cost_fields'
branch_labels = None
depends_on = None


def upgrade():
    # Add SMS_NOTIFICATION to the credittransactiontype enum
    # PostgreSQL requires ALTER TYPE ... ADD VALUE
    op.execute("ALTER TYPE credittransactiontype ADD VALUE IF NOT EXISTS 'SMS_NOTIFICATION'")


def downgrade():
    # PostgreSQL doesn't allow removing enum values easily
    # This would require recreating the enum and all columns using it
    pass
