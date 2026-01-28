"""Add promo_months to platform_settings

Revision ID: v310_add_promo_months
Revises: v309_make_prezime_optional
Create Date: 2026-01-29

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v310_add_promo_months'
down_revision = 'v309_make_prezime_optional'
branch_labels = None
depends_on = None


def upgrade():
    # Add promo_months column with default 2
    op.add_column('platform_settings',
                  sa.Column('promo_months', sa.Integer(), nullable=True, server_default='2'))


def downgrade():
    op.drop_column('platform_settings', 'promo_months')
