"""Add company data fields to platform_settings

Revision ID: l3m4n5o6p7q8
Revises: k2l3m4n5o6p7
Create Date: 2026-01-17

Dodaje polja za podatke o firmi ServisHub u platform_settings tabelu.
Ovi podaci se koriste na fakturama, notifikacijama, i svuda gde
ServisHub treba da se predstavi kao firma.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'l3m4n5o6p7q8'
down_revision = 'k2l3m4n5o6p7'
branch_labels = None
depends_on = None


def upgrade():
    # Dodaj company data polja
    op.add_column('platform_settings', sa.Column('company_name', sa.String(200), nullable=True, server_default='ServisHub DOO'))
    op.add_column('platform_settings', sa.Column('company_address', sa.String(300), nullable=True, server_default=''))
    op.add_column('platform_settings', sa.Column('company_city', sa.String(100), nullable=True, server_default='Beograd'))
    op.add_column('platform_settings', sa.Column('company_postal_code', sa.String(20), nullable=True, server_default=''))
    op.add_column('platform_settings', sa.Column('company_country', sa.String(100), nullable=True, server_default='Srbija'))
    op.add_column('platform_settings', sa.Column('company_pib', sa.String(20), nullable=True, server_default=''))
    op.add_column('platform_settings', sa.Column('company_mb', sa.String(20), nullable=True, server_default=''))
    op.add_column('platform_settings', sa.Column('company_phone', sa.String(50), nullable=True, server_default=''))
    op.add_column('platform_settings', sa.Column('company_email', sa.String(100), nullable=True, server_default=''))
    op.add_column('platform_settings', sa.Column('company_website', sa.String(200), nullable=True, server_default=''))
    op.add_column('platform_settings', sa.Column('company_bank_name', sa.String(100), nullable=True, server_default=''))
    op.add_column('platform_settings', sa.Column('company_bank_account', sa.String(50), nullable=True, server_default=''))


def downgrade():
    op.drop_column('platform_settings', 'company_bank_account')
    op.drop_column('platform_settings', 'company_bank_name')
    op.drop_column('platform_settings', 'company_website')
    op.drop_column('platform_settings', 'company_email')
    op.drop_column('platform_settings', 'company_phone')
    op.drop_column('platform_settings', 'company_mb')
    op.drop_column('platform_settings', 'company_pib')
    op.drop_column('platform_settings', 'company_country')
    op.drop_column('platform_settings', 'company_postal_code')
    op.drop_column('platform_settings', 'company_city')
    op.drop_column('platform_settings', 'company_address')
    op.drop_column('platform_settings', 'company_name')