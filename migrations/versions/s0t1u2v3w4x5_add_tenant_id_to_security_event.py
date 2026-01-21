"""Add tenant_id to security_event for tracking per-tenant security

Revision ID: s0t1u2v3w4x5
Revises: r9s0t1u2v3w4
Create Date: 2026-01-21

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 's0t1u2v3w4x5'
down_revision = 'r9s0t1u2v3w4'
branch_labels = None
depends_on = None


def upgrade():
    # Dodaj tenant_id kolonu u security_event tabelu
    op.add_column('security_event', sa.Column('tenant_id', sa.Integer(), nullable=True))

    # Kreiraj indeks za brze pretrage po tenant_id
    op.create_index('ix_security_event_tenant_id', 'security_event', ['tenant_id'])


def downgrade():
    # Ukloni indeks
    op.drop_index('ix_security_event_tenant_id', table_name='security_event')

    # Ukloni kolonu
    op.drop_column('security_event', 'tenant_id')
