"""Add POS fields to ServiceItem: code, is_variable_price, tax_label

Revision ID: v330_service_pos
Revises: v329_unit_cost
Create Date: 2026-02-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v330_service_pos'
down_revision = 'v329_unit_cost'
branch_labels = None
depends_on = None


def upgrade():
    """Add POS-related columns to service_item table."""
    # Code for POS identification
    op.add_column(
        'service_item',
        sa.Column('code', sa.String(20), nullable=True)
    )
    op.create_index('ix_service_item_code', 'service_item', ['code'])

    # Variable price flag
    op.add_column(
        'service_item',
        sa.Column('is_variable_price', sa.Boolean(), nullable=True, server_default='false')
    )

    # Tax label for fiscal
    op.add_column(
        'service_item',
        sa.Column('tax_label', sa.String(1), nullable=True, server_default='A')
    )


def downgrade():
    """Remove POS-related columns."""
    op.drop_index('ix_service_item_code', 'service_item')
    op.drop_column('service_item', 'code')
    op.drop_column('service_item', 'is_variable_price')
    op.drop_column('service_item', 'tax_label')
