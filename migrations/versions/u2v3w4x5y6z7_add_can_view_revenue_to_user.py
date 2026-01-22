"""Add can_view_revenue field to tenant_user

Revision ID: u2v3w4x5y6z7
Revises: t1u2v3w4x5y6
Create Date: 2026-01-23

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'u2v3w4x5y6z7'
down_revision = 't1u2v3w4x5y6'
branch_labels = None
depends_on = None


def upgrade():
    # Add can_view_revenue column to tenant_user table
    op.add_column('tenant_user', sa.Column('can_view_revenue', sa.Boolean(), nullable=False, server_default='false'))


def downgrade():
    op.drop_column('tenant_user', 'can_view_revenue')