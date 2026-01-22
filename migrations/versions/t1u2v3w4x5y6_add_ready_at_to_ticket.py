"""Add ready_at field to service_ticket

Revision ID: t1u2v3w4x5y6
Revises: s0t1u2v3w4x5
Create Date: 2026-01-22

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 't1u2v3w4x5y6'
down_revision = 's0t1u2v3w4x5'
branch_labels = None
depends_on = None


def upgrade():
    # Add ready_at column to service_ticket table
    op.add_column('service_ticket', sa.Column('ready_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('service_ticket', 'ready_at')
