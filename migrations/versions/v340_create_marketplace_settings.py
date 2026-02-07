"""Create MarketplaceSettings table

Revision ID: v340_marketplace_settings
Revises: v339_part_order
Create Date: 2026-02-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v340_marketplace_settings'
down_revision = 'v339_part_order'
branch_labels = None
depends_on = None


def upgrade():
    """Create marketplace_settings table with default values."""

    op.create_table(
        'marketplace_settings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('key', sa.String(50), unique=True, nullable=False),
        sa.Column('value', sa.String(200), nullable=False),
        sa.Column('description', sa.String(255)),
        sa.Column('updated_at', sa.DateTime()),
        sa.Column('updated_by_id', sa.Integer()),
    )

    # Insert default values
    op.execute("""
        INSERT INTO marketplace_settings (key, value, description) VALUES
        ('part_order_credit_buyer', '0.5', 'Krediti koji se skidaju kupcu po transakciji'),
        ('part_order_credit_supplier', '0.5', 'Krediti koji se skidaju dobavljaču po transakciji'),
        ('min_credits_to_order', '1.0', 'Minimalni broj kredita potreban za kreiranje porudžbine')
    """)


def downgrade():
    """Drop marketplace_settings table."""
    op.drop_table('marketplace_settings')
