"""Add rating cache fields to Tenant

Revision ID: v343_tenant_rating_cache
Revises: v342_tenant_favorites
Create Date: 2026-02-06

Note: v343 was originally for location fields (city, lat, lng) but those
already exist in Tenant (grad, latitude, longitude). This migration adds
the marketplace rating cache fields instead.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v343_tenant_rating_cache'
down_revision = 'v342_tenant_favorites'
branch_labels = None
depends_on = None


def upgrade():
    """Add marketplace rating cache fields to tenant table."""

    # Rating cache as supplier
    op.add_column('tenant', sa.Column('supplier_positive_ratings', sa.Integer(), server_default='0'))
    op.add_column('tenant', sa.Column('supplier_negative_ratings', sa.Integer(), server_default='0'))

    # Rating cache as buyer
    op.add_column('tenant', sa.Column('buyer_positive_ratings', sa.Integer(), server_default='0'))
    op.add_column('tenant', sa.Column('buyer_negative_ratings', sa.Integer(), server_default='0'))


def downgrade():
    """Remove marketplace rating cache fields from tenant table."""
    op.drop_column('tenant', 'buyer_negative_ratings')
    op.drop_column('tenant', 'buyer_positive_ratings')
    op.drop_column('tenant', 'supplier_negative_ratings')
    op.drop_column('tenant', 'supplier_positive_ratings')
