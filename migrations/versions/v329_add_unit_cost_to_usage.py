"""Add unit_cost to SparePartUsage for profit tracking

Revision ID: v329_unit_cost
Revises: v328_color_mode
Create Date: 2026-02-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v329_unit_cost'
down_revision = 'v328_color_mode'
branch_labels = None
depends_on = None


def upgrade():
    """Add unit_cost column to spare_part_usage table."""
    op.add_column(
        'spare_part_usage',
        sa.Column('unit_cost', sa.Numeric(10, 2), nullable=True)
    )


def downgrade():
    """Remove unit_cost column."""
    op.drop_column('spare_part_usage', 'unit_cost')
