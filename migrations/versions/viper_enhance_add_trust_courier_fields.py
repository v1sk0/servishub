"""Add trust badges, courier section, popular services fields

Revision ID: viper_enhance
Revises: g00gl3_fix01
Create Date: 2026-01-30 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'viper_enhance'
down_revision = 'g00gl3_fix01'
branch_labels = None
depends_on = None


def upgrade():
    # Trust badges
    op.add_column('tenant_public_profile', sa.Column('warranty_days', sa.Integer(), nullable=True, server_default='90'))
    op.add_column('tenant_public_profile', sa.Column('show_trust_badges', sa.Boolean(), nullable=True, server_default='true'))
    op.add_column('tenant_public_profile', sa.Column('fast_service_text', sa.String(50), nullable=True, server_default='1-3 sata'))

    # Courier section
    op.add_column('tenant_public_profile', sa.Column('show_courier_section', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('tenant_public_profile', sa.Column('courier_price', sa.Integer(), nullable=True))
    op.add_column('tenant_public_profile', sa.Column('courier_title', sa.String(100), nullable=True))
    op.add_column('tenant_public_profile', sa.Column('courier_description', sa.String(300), nullable=True))

    # Popular services
    op.add_column('tenant_public_profile', sa.Column('show_popular_services', sa.Boolean(), nullable=True, server_default='true'))
    op.add_column('tenant_public_profile', sa.Column('popular_services_title', sa.String(100), nullable=True))
    op.add_column('tenant_public_profile', sa.Column('popular_services_limit', sa.Integer(), nullable=True, server_default='6'))


def downgrade():
    op.drop_column('tenant_public_profile', 'popular_services_limit')
    op.drop_column('tenant_public_profile', 'popular_services_title')
    op.drop_column('tenant_public_profile', 'show_popular_services')
    op.drop_column('tenant_public_profile', 'courier_description')
    op.drop_column('tenant_public_profile', 'courier_title')
    op.drop_column('tenant_public_profile', 'courier_price')
    op.drop_column('tenant_public_profile', 'show_courier_section')
    op.drop_column('tenant_public_profile', 'fast_service_text')
    op.drop_column('tenant_public_profile', 'show_trust_badges')
    op.drop_column('tenant_public_profile', 'warranty_days')
