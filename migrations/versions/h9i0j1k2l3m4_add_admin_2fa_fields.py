"""Add 2FA fields to platform_admin

Revision ID: h9i0j1k2l3m4
Revises: g8h9i0j1k2l3
Create Date: 2026-01-16

Dodaje polja za 2FA (TOTP) autentifikaciju:
- totp_secret: Base32 secret za TOTP generisanje
- is_2fa_enabled: Da li je 2FA aktiviran
- totp_verified_at: Kada je 2FA verifikovan
- backup_codes: JSON lista hashiranih backup kodova
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'h9i0j1k2l3m4'
down_revision = 'g8h9i0j1k2l3'
branch_labels = None
depends_on = None


def upgrade():
    # Dodaj 2FA polja u platform_admin tabelu
    op.add_column('platform_admin', sa.Column('totp_secret', sa.String(32), nullable=True))
    op.add_column('platform_admin', sa.Column('is_2fa_enabled', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('platform_admin', sa.Column('totp_verified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('platform_admin', sa.Column('backup_codes', sa.Text(), nullable=True))


def downgrade():
    # Ukloni 2FA polja
    op.drop_column('platform_admin', 'backup_codes')
    op.drop_column('platform_admin', 'totp_verified_at')
    op.drop_column('platform_admin', 'is_2fa_enabled')
    op.drop_column('platform_admin', 'totp_secret')