"""Add FK for delivery_option_id in PartOrderRequest

Revision ID: v346_order_delivery_fk
Revises: v345_delivery_options
Create Date: 2026-02-06

Note: The delivery_option_id column was created in v339 but without FK
because supplier_delivery_option table didn't exist yet. This migration
adds the FK constraint now that the table exists.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v346_order_delivery_fk'
down_revision = 'v345_delivery_options'
branch_labels = None
depends_on = None


def upgrade():
    """Add FK constraint for delivery_option_id in part_order_request."""

    op.create_foreign_key(
        'fk_part_order_delivery_option',
        'part_order_request', 'supplier_delivery_option',
        ['delivery_option_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade():
    """Remove FK constraint for delivery_option_id."""
    op.drop_constraint('fk_part_order_delivery_option', 'part_order_request', type_='foreignkey')
