"""Add color_mode to TenantPublicProfile

Revision ID: v328_color_mode
Revises: v327_add_sms_notification_to_credit_enum
Create Date: 2026-02-02

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v328_color_mode'
down_revision = 'v327_add_sms_notification_to_credit_enum'
branch_labels = None
depends_on = None


def upgrade():
    """Add color_mode column to tenant_public_profile table."""
    op.add_column(
        'tenant_public_profile',
        sa.Column('color_mode', sa.String(10), nullable=True, server_default='dark')
    )


def downgrade():
    """Remove color_mode column."""
    op.drop_column('tenant_public_profile', 'color_mode')
