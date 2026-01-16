"""
Make password_hash nullable for OAuth users.

OAuth users authenticate via Google and don't have a password,
so password_hash needs to be nullable.

Revision ID: g8h9i0j1k2l3
Revises: f7g8h9i0j1k2
Create Date: 2026-01-16
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'g8h9i0j1k2l3'
down_revision = 'f7g8h9i0j1k2'
branch_labels = None
depends_on = None


def upgrade():
    """Make password_hash column nullable."""
    op.alter_column('tenant_user', 'password_hash',
                    existing_type=sa.String(200),
                    nullable=True)


def downgrade():
    """Make password_hash column NOT NULL again."""
    # Note: This will fail if there are OAuth users with NULL passwords
    op.alter_column('tenant_user', 'password_hash',
                    existing_type=sa.String(200),
                    nullable=False)