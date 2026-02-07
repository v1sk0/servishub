"""Create MarketplaceRating table

Revision ID: v341_marketplace_rating
Revises: v340_marketplace_settings
Create Date: 2026-02-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v341_marketplace_rating'
down_revision = 'v340_marketplace_settings'
branch_labels = None
depends_on = None


def upgrade():
    """Create marketplace_rating table."""

    op.create_table(
        'marketplace_rating',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('part_order_request.id', ondelete='CASCADE'), nullable=False),
        # Rater
        sa.Column('rater_tenant_id', sa.Integer(), sa.ForeignKey('tenant.id', ondelete='CASCADE'), nullable=False),
        sa.Column('rater_user_id', sa.Integer(), sa.ForeignKey('tenant_user.id', ondelete='SET NULL')),
        # Rated
        sa.Column('rated_tenant_id', sa.Integer(), sa.ForeignKey('tenant.id', ondelete='CASCADE'), nullable=False),
        # Rating
        sa.Column('rating_role', sa.String(20), nullable=False),  # buyer, supplier
        sa.Column('rating_type', sa.String(20), nullable=False),  # POSITIVE, NEGATIVE
        sa.Column('comment', sa.Text()),
        # Timestamp
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # One rating per role per order
    op.create_unique_constraint('uq_rating_order_rater', 'marketplace_rating', ['order_id', 'rater_tenant_id'])

    op.create_index('ix_marketplace_rating_order', 'marketplace_rating', ['order_id'])
    op.create_index('ix_marketplace_rating_rater', 'marketplace_rating', ['rater_tenant_id'])
    op.create_index('ix_marketplace_rating_rated', 'marketplace_rating', ['rated_tenant_id'])


def downgrade():
    """Drop marketplace_rating table."""
    op.drop_index('ix_marketplace_rating_rated', 'marketplace_rating')
    op.drop_index('ix_marketplace_rating_rater', 'marketplace_rating')
    op.drop_index('ix_marketplace_rating_order', 'marketplace_rating')
    op.drop_constraint('uq_rating_order_rater', 'marketplace_rating', type_='unique')
    op.drop_table('marketplace_rating')
