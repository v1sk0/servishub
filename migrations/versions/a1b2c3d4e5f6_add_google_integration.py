"""Add Google integration tables and theme field

Revision ID: a1b2c3d4e5f6
Revises: z7a8b9c0d1e2
Create Date: 2026-01-29 23:58:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'v317_dual_currency'
branch_labels = None
depends_on = None


def upgrade():
    # Create tenant_google_integration table
    op.create_table('tenant_google_integration',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('google_place_id', sa.String(255), nullable=True),
        sa.Column('google_rating', sa.Numeric(2, 1), nullable=True),
        sa.Column('total_reviews', sa.Integer(), nullable=True, default=0),
        sa.Column('access_token', sa.Text(), nullable=True),
        sa.Column('refresh_token', sa.Text(), nullable=True),
        sa.Column('token_expires_at', sa.DateTime(), nullable=True),
        sa.Column('last_sync_at', sa.DateTime(), nullable=True),
        sa.Column('sync_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id')
    )
    op.create_index('ix_tenant_google_integration_tenant_id', 'tenant_google_integration', ['tenant_id'], unique=True)

    # Create tenant_google_review table
    op.create_table('tenant_google_review',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('integration_id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('google_review_id', sa.String(255), nullable=False),
        sa.Column('author_name', sa.String(200), nullable=True),
        sa.Column('author_photo_url', sa.String(500), nullable=True),
        sa.Column('rating', sa.Integer(), nullable=True),
        sa.Column('text', sa.Text(), nullable=True),
        sa.Column('review_time', sa.DateTime(), nullable=True),
        sa.Column('relative_time', sa.String(100), nullable=True),
        sa.Column('is_visible', sa.Boolean(), nullable=True, default=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['integration_id'], ['tenant_google_integration.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('google_review_id')
    )
    op.create_index('ix_tenant_google_review_tenant_id', 'tenant_google_review', ['tenant_id'], unique=False)
    op.create_index('ix_tenant_google_review_integration_id', 'tenant_google_review', ['integration_id'], unique=False)

    # Add theme column to tenant_public_profile
    op.add_column('tenant_public_profile', sa.Column('theme', sa.String(20), nullable=True, server_default='starter'))


def downgrade():
    # Remove theme column
    op.drop_column('tenant_public_profile', 'theme')

    # Drop indexes
    op.drop_index('ix_tenant_google_review_integration_id', table_name='tenant_google_review')
    op.drop_index('ix_tenant_google_review_tenant_id', table_name='tenant_google_review')
    op.drop_index('ix_tenant_google_integration_tenant_id', table_name='tenant_google_integration')

    # Drop tables
    op.drop_table('tenant_google_review')
    op.drop_table('tenant_google_integration')
