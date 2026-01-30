"""Add flash_services fields to TenantPublicProfile

Revision ID: flash_services_01
Revises: z7a8b9c0d1e2
Create Date: 2026-01-30

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'flash_services_01'
down_revision = 'z7a8b9c0d1e2'
branch_labels = None
depends_on = None


def upgrade():
    # Add show_flash_services column
    op.add_column('tenant_public_profile',
        sa.Column('show_flash_services', sa.Boolean(), nullable=True, server_default='true')
    )

    # Add flash_service_categories JSON column
    op.add_column('tenant_public_profile',
        sa.Column('flash_service_categories', sa.JSON(), nullable=True)
    )


def downgrade():
    op.drop_column('tenant_public_profile', 'flash_service_categories')
    op.drop_column('tenant_public_profile', 'show_flash_services')
