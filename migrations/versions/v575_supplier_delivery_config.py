"""v575: Supplier delivery configuration - cities, rounds, couriers, pickup

Revision ID: v575_supplier_delivery_config
Revises: v574_smart_offers
Create Date: 2026-02-09

Dodaje:
- delivery_cities (JSON) - gradovi u koje dobavljac dostavlja
- delivery_rounds (JSON) - ture dostave (weekday/saturday/sunday)
- courier_services_config (JSON) - kurirske sluzbe sa kojima saradjuje
- allows_pickup (Boolean) - licno preuzimanje
- delivery_notes (Text) - napomene o dostavi
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v575_supplier_delivery_config'
down_revision = 'v574_smart_offers'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('supplier', sa.Column('delivery_cities', sa.JSON(), server_default='[]'))
    op.add_column('supplier', sa.Column('delivery_rounds', sa.JSON(), server_default='{}'))
    op.add_column('supplier', sa.Column('courier_services_config', sa.JSON(), server_default='[]'))
    op.add_column('supplier', sa.Column('allows_pickup', sa.Boolean(), server_default='false'))
    op.add_column('supplier', sa.Column('delivery_notes', sa.Text()))


def downgrade():
    op.drop_column('supplier', 'delivery_notes')
    op.drop_column('supplier', 'allows_pickup')
    op.drop_column('supplier', 'courier_services_config')
    op.drop_column('supplier', 'delivery_rounds')
    op.drop_column('supplier', 'delivery_cities')
