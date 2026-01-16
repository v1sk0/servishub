"""Add PendingEmailVerification table for email verification before registration

Revision ID: d5e6f7g8h9i0
Revises: c4d5e6f7g8h9
Create Date: 2026-01-16 15:00:00.000000

Dodaje:
- pending_email_verification tabelu za verifikaciju emaila pre registracije
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd5e6f7g8h9i0'
down_revision = 'c4d5e6f7g8h9'
branch_labels = None
depends_on = None


def upgrade():
    # Kreiraj pending_email_verification tabelu
    op.create_table(
        'pending_email_verification',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=100), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('verified', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('send_count', sa.Integer(), nullable=True, server_default='1'),
        sa.Column('last_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Kreiraj indekse
    op.create_index('ix_pending_email_verification_email', 'pending_email_verification', ['email'], unique=True)
    op.create_index('ix_pending_email_verification_verified', 'pending_email_verification', ['verified'], unique=False)
    op.create_index('ix_pending_email_verified', 'pending_email_verification', ['email', 'verified'], unique=False)


def downgrade():
    # Obrisi indekse
    op.drop_index('ix_pending_email_verified', table_name='pending_email_verification')
    op.drop_index('ix_pending_email_verification_verified', table_name='pending_email_verification')
    op.drop_index('ix_pending_email_verification_email', table_name='pending_email_verification')

    # Obrisi tabelu
    op.drop_table('pending_email_verification')