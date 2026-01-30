"""Add google_photos field to TenantGoogleIntegration

Revision ID: google_photos
Revises: viper_enhance
Create Date: 2026-01-30 01:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'google_photos'
down_revision = 'viper_enhance'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('tenant_google_integration',
                  sa.Column('google_photos', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('tenant_google_integration', 'google_photos')
