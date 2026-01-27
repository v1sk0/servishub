"""v3.08a: Add pos_role to TenantUser

Revision ID: v308a_audit_fixes
Revises: v308_goods_invoice_fiscal
Create Date: 2026-01-27 23:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'v308a_audit_fixes'
down_revision = 'v308_goods_invoice_fiscal'
branch_labels = None
depends_on = None


def upgrade():
    # PosRole enum type
    pos_role_enum = sa.Enum('CASHIER', 'MANAGER', 'ADMIN', name='posrole')
    pos_role_enum.create(op.get_bind(), checkfirst=True)

    op.add_column('tenant_user', sa.Column('pos_role', sa.Enum('CASHIER', 'MANAGER', 'ADMIN', name='posrole'), nullable=True))


def downgrade():
    op.drop_column('tenant_user', 'pos_role')

    pos_role_enum = sa.Enum('CASHIER', 'MANAGER', 'ADMIN', name='posrole')
    pos_role_enum.drop(op.get_bind(), checkfirst=True)