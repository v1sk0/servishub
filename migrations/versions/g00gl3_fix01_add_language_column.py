"""Add language column to tenant_google_review

Revision ID: g00gl3_fix01
Revises: g00gl3_int3gr
Create Date: 2026-01-30 00:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'g00gl3_fix01'
down_revision = 'g00gl3_int3gr'
branch_labels = None
depends_on = None


def upgrade():
    # Add language column to tenant_google_review
    op.add_column('tenant_google_review', sa.Column('language', sa.String(10), nullable=True))


def downgrade():
    op.drop_column('tenant_google_review', 'language')
