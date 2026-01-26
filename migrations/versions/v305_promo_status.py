"""v3.05: Add PROMO status and promo_ends_at column

Revision ID: v305_promo_status
Revises: a1b2c3d4e5f6
Create Date: 2026-01-25

Adds:
- PROMO value to tenantstatus enum (2 months FREE for new tenants)
- promo_ends_at column to tenant table
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v305_promo_status'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # Add PROMO value to tenantstatus enum
    # PostgreSQL ENUM types need ALTER TYPE to add new values
    op.execute("ALTER TYPE tenantstatus ADD VALUE IF NOT EXISTS 'PROMO'")

    # Add promo_ends_at column to tenant table
    op.add_column('tenant', sa.Column('promo_ends_at', sa.DateTime(), nullable=True))


def downgrade():
    # Remove promo_ends_at column
    op.drop_column('tenant', 'promo_ends_at')

    # PostgreSQL does not support removing values from ENUM types
    # The PROMO value will remain but won't be used after downgrade