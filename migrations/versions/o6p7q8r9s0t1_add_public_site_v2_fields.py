"""Add Public Site v2 fields

Revision ID: o6p7q8r9s0t1
Revises: n5o6p7q8r9s0
Create Date: 2026-01-19 01:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'o6p7q8r9s0t1'
down_revision = 'n5o6p7q8r9s0'
branch_labels = None
depends_on = None


def upgrade():
    # FAQ sekcija
    op.add_column('tenant_public_profile', sa.Column('faq_title', sa.String(200), nullable=True))
    op.add_column('tenant_public_profile', sa.Column('faq_items', sa.JSON(), nullable=True))

    # Brendovi
    op.add_column('tenant_public_profile', sa.Column('show_brands_section', sa.Boolean(), nullable=True, server_default='true'))
    op.add_column('tenant_public_profile', sa.Column('supported_brands', sa.JSON(), nullable=True))

    # Proces rada
    op.add_column('tenant_public_profile', sa.Column('show_process_section', sa.Boolean(), nullable=True, server_default='true'))
    op.add_column('tenant_public_profile', sa.Column('process_title', sa.String(200), nullable=True))
    op.add_column('tenant_public_profile', sa.Column('process_steps', sa.JSON(), nullable=True))

    # WhatsApp
    op.add_column('tenant_public_profile', sa.Column('show_whatsapp_button', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('tenant_public_profile', sa.Column('whatsapp_number', sa.String(20), nullable=True))
    op.add_column('tenant_public_profile', sa.Column('whatsapp_message', sa.String(300), nullable=True))

    # Status tracking widget
    op.add_column('tenant_public_profile', sa.Column('show_tracking_widget', sa.Boolean(), nullable=True, server_default='true'))
    op.add_column('tenant_public_profile', sa.Column('tracking_widget_title', sa.String(200), nullable=True))

    # Hero stil
    op.add_column('tenant_public_profile', sa.Column('hero_style', sa.String(20), nullable=True))


def downgrade():
    # Hero stil
    op.drop_column('tenant_public_profile', 'hero_style')

    # Status tracking widget
    op.drop_column('tenant_public_profile', 'tracking_widget_title')
    op.drop_column('tenant_public_profile', 'show_tracking_widget')

    # WhatsApp
    op.drop_column('tenant_public_profile', 'whatsapp_message')
    op.drop_column('tenant_public_profile', 'whatsapp_number')
    op.drop_column('tenant_public_profile', 'show_whatsapp_button')

    # Proces rada
    op.drop_column('tenant_public_profile', 'process_steps')
    op.drop_column('tenant_public_profile', 'process_title')
    op.drop_column('tenant_public_profile', 'show_process_section')

    # Brendovi
    op.drop_column('tenant_public_profile', 'supported_brands')
    op.drop_column('tenant_public_profile', 'show_brands_section')

    # FAQ sekcija
    op.drop_column('tenant_public_profile', 'faq_items')
    op.drop_column('tenant_public_profile', 'faq_title')