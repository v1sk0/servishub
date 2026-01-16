"""
Add latitude and longitude to Tenant model for company headquarters address.

Revision ID: f7g8h9i0j1k2
Revises: e6f7g8h9i0j1
Create Date: 2026-01-16

ServiceLocation already has latitude/longitude fields.
This migration adds them to Tenant for company headquarters.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f7g8h9i0j1k2'
down_revision = 'e6f7g8h9i0j1'
branch_labels = None
depends_on = None


def upgrade():
    """Add latitude and longitude columns to tenant table."""
    # Dodaj koordinate za sediste firme
    op.add_column('tenant', sa.Column('latitude', sa.Float(), nullable=True))
    op.add_column('tenant', sa.Column('longitude', sa.Float(), nullable=True))


def downgrade():
    """Remove latitude and longitude columns from tenant table."""
    op.drop_column('tenant', 'longitude')
    op.drop_column('tenant', 'latitude')