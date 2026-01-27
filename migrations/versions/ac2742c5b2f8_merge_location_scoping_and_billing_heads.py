"""merge location scoping and billing heads

Revision ID: ac2742c5b2f8
Revises: c3d4e5f6g7h8, v306_tenant_logo_url
Create Date: 2026-01-27 18:51:35.895263

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ac2742c5b2f8'
down_revision = ('c3d4e5f6g7h8', 'v306_tenant_logo_url')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
