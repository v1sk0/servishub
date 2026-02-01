"""Add SMS D7 cost fields to platform_settings

Revision ID: v326_sms_d7_cost_fields
Revises: v325_sms_delivery_status
Create Date: 2026-02-01

Dodaje:
- sms_d7_cost_usd: D7 Networks cena po SMS u USD ($0.026 za Srbiju)
- sms_usd_to_eur: USD to EUR kurs za kalkulaciju
"""
from alembic import op
import sqlalchemy as sa
from decimal import Decimal


# revision identifiers, used by Alembic.
revision = 'v326_sms_d7_cost_fields'
down_revision = 'v325_sms_delivery_status'
branch_labels = None
depends_on = None


def upgrade():
    # Dodaj D7 cost polje - $0.026 za Srbiju
    op.add_column('platform_settings', sa.Column(
        'sms_d7_cost_usd',
        sa.Numeric(10, 4),
        nullable=True,
        server_default='0.026'
    ))

    # Dodaj USD to EUR kurs
    op.add_column('platform_settings', sa.Column(
        'sms_usd_to_eur',
        sa.Numeric(10, 4),
        nullable=True,
        server_default='0.92'
    ))


def downgrade():
    op.drop_column('platform_settings', 'sms_usd_to_eur')
    op.drop_column('platform_settings', 'sms_d7_cost_usd')
