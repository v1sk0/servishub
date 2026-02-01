"""Add sms_opt_out field to service_ticket

Revision ID: v324_sms_opt_out
Revises: v323_sms_price_platform_settings
Create Date: 2026-02-01

Dodaje polje sms_opt_out u service_ticket tabelu.
Klijent moze da odbije SMS obavestenja za konkretan tiket.
Default je False (prima SMS po opt-in modelu).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v324_sms_opt_out'
down_revision = 'v323_sms_price_platform_settings'
branch_labels = None
depends_on = None


def upgrade():
    # Dodaj sms_opt_out polje - default False znaci da prima SMS
    op.add_column('service_ticket', sa.Column(
        'sms_opt_out',
        sa.Boolean(),
        nullable=False,
        server_default='false'
    ))


def downgrade():
    op.drop_column('service_ticket', 'sms_opt_out')
