"""Create SimpleSupplier table for internal suppliers

Revision ID: v331_simple_supplier
Revises: v330_service_pos
Create Date: 2026-02-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v331_simple_supplier'
down_revision = 'v330_service_pos'
branch_labels = None
depends_on = None


def upgrade():
    """Create simple_supplier table."""
    op.create_table(
        'simple_supplier',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenant.id', ondelete='CASCADE'), nullable=False),
        sa.Column('supplier_type', sa.String(20), nullable=False, server_default='COMPANY'),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('phone', sa.String(50)),
        sa.Column('email', sa.String(100)),
        sa.Column('address', sa.Text()),
        sa.Column('city', sa.String(100)),
        # Company fields
        sa.Column('company_name', sa.String(200)),
        sa.Column('pib', sa.String(20)),
        sa.Column('maticni_broj', sa.String(20)),
        sa.Column('bank_account', sa.String(50)),
        # Individual fields
        sa.Column('jmbg', sa.String(13)),
        sa.Column('id_card_number', sa.String(20)),
        sa.Column('id_card_issued_by', sa.String(100)),
        sa.Column('id_card_issue_date', sa.Date()),
        # Status
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('notes', sa.Text()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime()),
    )
    op.create_index('ix_simple_supplier_tenant_type', 'simple_supplier', ['tenant_id', 'supplier_type'])


def downgrade():
    """Drop simple_supplier table."""
    op.drop_index('ix_simple_supplier_tenant_type', 'simple_supplier')
    op.drop_table('simple_supplier')
