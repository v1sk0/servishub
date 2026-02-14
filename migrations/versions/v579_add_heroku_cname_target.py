"""Add heroku_cname_target to tenant_public_profile

Revision ID: v579_add_heroku_cname_target
Revises: v578_add_receipt_currency
Create Date: 2026-02-11
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v579_add_heroku_cname_target'
down_revision = 'v578_add_receipt_currency'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('tenant_public_profile',
        sa.Column('heroku_cname_target', sa.String(255), nullable=True)
    )

    # Backfill: postojeći dolcevitaservis.com domen
    op.execute("""
        UPDATE tenant_public_profile
        SET heroku_cname_target = 'objective-roundworm-myzwhlgx8r488f1ulwrvm1vq.herokudns.com'
        WHERE custom_domain = 'dolcevitaservis.com'
    """)


def downgrade():
    op.drop_column('tenant_public_profile', 'heroku_cname_target')
