"""Add service_item table for cenovnik

Revision ID: m4n5o6p7q8r9
Revises: l3m4n5o6p7q8
Create Date: 2026-01-18 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'm4n5o6p7q8r9'
down_revision = 'l3m4n5o6p7q8'
branch_labels = None
depends_on = None


def upgrade():
    # Kreiraj service_item tabelu sa string kategorijom
    op.create_table('service_item',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=100), nullable=False, server_default='Ostalo'),
        sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='RSD'),
        sa.Column('price_note', sa.String(length=200), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Kreiraj indekse
    op.create_index('ix_service_item_tenant_id', 'service_item', ['tenant_id'], unique=False)
    op.create_index('ix_service_item_category', 'service_item', ['category'], unique=False)
    op.create_index('ix_service_item_display_order', 'service_item', ['display_order'], unique=False)
    op.create_index('ix_service_item_is_active', 'service_item', ['is_active'], unique=False)
    op.create_index('ix_service_tenant_order', 'service_item', ['tenant_id', 'display_order'], unique=False)
    op.create_index('ix_service_tenant_category', 'service_item', ['tenant_id', 'category'], unique=False)

    # Kreiraj unique constraint za ime po tenantu
    op.create_unique_constraint('uq_service_tenant_name', 'service_item', ['tenant_id', 'name'])


def downgrade():
    op.drop_constraint('uq_service_tenant_name', 'service_item', type_='unique')
    op.drop_index('ix_service_tenant_category', table_name='service_item')
    op.drop_index('ix_service_tenant_order', table_name='service_item')
    op.drop_index('ix_service_item_is_active', table_name='service_item')
    op.drop_index('ix_service_item_display_order', table_name='service_item')
    op.drop_index('ix_service_item_category', table_name='service_item')
    op.drop_index('ix_service_item_tenant_id', table_name='service_item')
    op.drop_table('service_item')