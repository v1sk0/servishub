"""Add security_event table for storing security events in database.

Revision ID: i0j1k2l3m4n5
Revises: h9i0j1k2l3m4
Create Date: 2026-01-16

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'i0j1k2l3m4n5'
down_revision = 'h9i0j1k2l3m4'
branch_labels = None
depends_on = None


def upgrade():
    # Kreiraj security_event tabelu
    op.create_table('security_event',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('severity', sa.String(20), nullable=False, server_default='info'),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('user_type', sa.String(20), nullable=True),
        sa.Column('email_hash', sa.String(64), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(500), nullable=True),
        sa.Column('endpoint', sa.String(200), nullable=True),
        sa.Column('method', sa.String(10), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Kreiraj indekse za brze pretrage
    op.create_index('ix_security_event_event_type', 'security_event', ['event_type'])
    op.create_index('ix_security_event_user_id', 'security_event', ['user_id'])
    op.create_index('ix_security_event_ip_address', 'security_event', ['ip_address'])
    op.create_index('ix_security_event_created_at', 'security_event', ['created_at'])
    op.create_index('ix_security_event_severity', 'security_event', ['severity'])


def downgrade():
    # Ukloni indekse
    op.drop_index('ix_security_event_severity', table_name='security_event')
    op.drop_index('ix_security_event_created_at', table_name='security_event')
    op.drop_index('ix_security_event_ip_address', table_name='security_event')
    op.drop_index('ix_security_event_user_id', table_name='security_event')
    op.drop_index('ix_security_event_event_type', table_name='security_event')

    # Ukloni tabelu
    op.drop_table('security_event')