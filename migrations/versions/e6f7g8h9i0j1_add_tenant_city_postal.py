"""Add grad and postanski_broj columns to tenant table

Revision ID: e6f7g8h9i0j1
Revises: d5e6f7g8h9i0
Create Date: 2026-01-16 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e6f7g8h9i0j1'
down_revision = 'd5e6f7g8h9i0'
branch_labels = None
depends_on = None


def upgrade():
    # Add grad (city) column to tenant table
    op.add_column('tenant', sa.Column('grad', sa.String(100), nullable=True))

    # Add postanski_broj (postal code) column to tenant table
    op.add_column('tenant', sa.Column('postanski_broj', sa.String(10), nullable=True))


def downgrade():
    # Remove the columns
    op.drop_column('tenant', 'postanski_broj')
    op.drop_column('tenant', 'grad')