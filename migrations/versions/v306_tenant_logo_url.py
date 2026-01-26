"""v3.06: Add logo_url column to tenant table

Revision ID: v306_tenant_logo_url
Revises: v305_promo_status
Create Date: 2026-01-26

Adds logo_url column to tenant table for storing Cloudinary logo URL.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v306_tenant_logo_url'
down_revision = 'v305_promo_status'
branch_labels = None
depends_on = None


def upgrade():
    # Add logo_url column to tenant table
    op.add_column('tenant', sa.Column('logo_url', sa.String(500), nullable=True))


def downgrade():
    # Remove logo_url column
    op.drop_column('tenant', 'logo_url')
