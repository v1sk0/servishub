"""Add rejection_reason to service_ticket and REJECTED status

Revision ID: q8r9s0t1u2v3
Revises: p7q8r9s0t1u2
Create Date: 2026-01-20

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'q8r9s0t1u2v3'
down_revision = 'p7q8r9s0t1u2'
branch_labels = None
depends_on = None


def upgrade():
    # Add REJECTED value to ticketstatus enum (PostgreSQL specific)
    op.execute("ALTER TYPE ticketstatus ADD VALUE IF NOT EXISTS 'REJECTED'")

    # Add rejection_reason column to service_ticket table
    op.add_column('service_ticket', sa.Column(
        'rejection_reason',
        sa.Text(),
        nullable=True
    ))


def downgrade():
    op.drop_column('service_ticket', 'rejection_reason')
    # Note: PostgreSQL doesn't support removing values from enums easily
    # The REJECTED enum value will remain but can be safely ignored