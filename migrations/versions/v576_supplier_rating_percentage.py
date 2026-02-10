"""v576: Change supplier.rating from Numeric(2,1) to Numeric(5,1) for percentage storage

Revision ID: v576_supplier_rating_percentage
Revises: v575_supplier_delivery_config
Create Date: 2026-02-10

Rating sada cuva procenat pozitivnih ocena (0-100) umesto 1-5 zvezdica.
Numeric(2,1) max 9.9 - premalo za 100%.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v576_supplier_rating_percentage'
down_revision = 'v575_supplier_delivery_config'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('supplier', 'rating',
                    type_=sa.Numeric(5, 1),
                    existing_type=sa.Numeric(2, 1),
                    existing_nullable=True)


def downgrade():
    op.alter_column('supplier', 'rating',
                    type_=sa.Numeric(2, 1),
                    existing_type=sa.Numeric(5, 1),
                    existing_nullable=True)
