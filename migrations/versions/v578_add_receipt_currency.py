"""Add missing currency column to receipt table.

Revision ID: v578_receipt_currency
Revises: v577_add_color_fields
Create Date: 2026-02-12
"""
from alembic import op
import sqlalchemy as sa

revision = 'v578_receipt_currency'
down_revision = 'v577_add_color_fields'
branch_labels = None
depends_on = None


def upgrade():
    # Column may already exist (added outside migration chain)
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [c['name'] for c in inspector.get_columns('receipt')]
    if 'currency' not in columns:
        op.add_column('receipt',
            sa.Column('currency', sa.String(3), nullable=False, server_default='RSD')
        )


def downgrade():
    op.drop_column('receipt', 'currency')
