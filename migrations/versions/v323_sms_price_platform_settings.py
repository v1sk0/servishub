"""Add SMS price to platform settings

Revision ID: v323_sms_price_platform_settings
Revises: v322_tenant_sms_settings
Create Date: 2026-02-01

Dodaje polje sms_price_credits u platform_settings tabelu
za konfiguraciju cene SMS-a iz admin panela.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v323_sms_price_platform_settings'
down_revision = 'v322_tenant_sms_settings'
branch_labels = None
depends_on = None


def upgrade():
    # Dodaj SMS cenu u platform settings
    # Default: 0.20 kredita (1 kredit = 1 EUR)
    op.add_column('platform_settings', sa.Column(
        'sms_price_credits',
        sa.Numeric(10, 4),
        nullable=True,
        server_default='0.20'
    ))


def downgrade():
    op.drop_column('platform_settings', 'sms_price_credits')
