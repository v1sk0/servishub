"""Add landing page contact fields to platform_settings

Revision ID: r9s0t1u2v3w4
Revises: q8r9s0t1u2v3
Create Date: 2026-01-21

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'r9s0t1u2v3w4'
down_revision = 'q8r9s0t1u2v3'
branch_labels = None
depends_on = None


def upgrade():
    # Contact fields for landing page
    op.add_column('platform_settings', sa.Column('contact_email', sa.String(100), nullable=True, server_default=''))
    op.add_column('platform_settings', sa.Column('contact_phone', sa.String(50), nullable=True, server_default=''))
    op.add_column('platform_settings', sa.Column('contact_location', sa.String(200), nullable=True, server_default=''))

    # Social media links
    op.add_column('platform_settings', sa.Column('social_twitter', sa.String(255), nullable=True, server_default=''))
    op.add_column('platform_settings', sa.Column('social_facebook', sa.String(255), nullable=True, server_default=''))
    op.add_column('platform_settings', sa.Column('social_instagram', sa.String(255), nullable=True, server_default=''))
    op.add_column('platform_settings', sa.Column('social_linkedin', sa.String(255), nullable=True, server_default=''))
    op.add_column('platform_settings', sa.Column('social_youtube', sa.String(255), nullable=True, server_default=''))


def downgrade():
    op.drop_column('platform_settings', 'social_youtube')
    op.drop_column('platform_settings', 'social_linkedin')
    op.drop_column('platform_settings', 'social_instagram')
    op.drop_column('platform_settings', 'social_facebook')
    op.drop_column('platform_settings', 'social_twitter')
    op.drop_column('platform_settings', 'contact_location')
    op.drop_column('platform_settings', 'contact_phone')
    op.drop_column('platform_settings', 'contact_email')
