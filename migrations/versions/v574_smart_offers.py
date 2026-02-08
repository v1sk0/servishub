"""v574: Smart offers - OFFERED status, delivery fields, OrderRating, indexes

Revision ID: v574_smart_offers
Revises: v571_dual_pricing
Create Date: 2026-02-08

Dodaje:
- OFFERED status u OrderStatus enum (2-step potvrda)
- Delivery polja na part_order (per-order isporuka)
- expires_at za auto-expiry (2h SENT, 4h OFFERED)
- OrderRating tabela (ocene transakcija)
- Performance indeksi
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v574_smart_offers'
down_revision = 'v571_dual_pricing'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Novi status OFFERED - MORA van transakcije (PostgreSQL ogranicenje)
    connection = op.get_bind()
    connection.execute(sa.text("COMMIT"))
    connection.execute(sa.text("ALTER TYPE orderstatus ADD VALUE IF NOT EXISTS 'OFFERED'"))
    connection.execute(sa.text("BEGIN"))

    # 2. Delivery polja na part_order (supplier popunjava pri confirm-availability)
    op.add_column('part_order', sa.Column('delivery_method', sa.String(30)))
    op.add_column('part_order', sa.Column('courier_service', sa.String(50)))
    op.add_column('part_order', sa.Column('delivery_cost', sa.Numeric(10, 2)))
    op.add_column('part_order', sa.Column('estimated_delivery_days', sa.Integer))
    op.add_column('part_order', sa.Column('delivery_cutoff_time', sa.Time))

    # 3. Timestamps za OFFERED + auto-expiry
    op.add_column('part_order', sa.Column('offered_at', sa.DateTime))
    op.add_column('part_order', sa.Column('expires_at', sa.DateTime))

    # 4. OrderRating tabela
    op.create_table('order_rating',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('order_id', sa.BigInteger,
                  sa.ForeignKey('part_order.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('rater_type', sa.String(10), nullable=False),
        sa.Column('rater_id', sa.Integer, nullable=False),
        sa.Column('rated_id', sa.Integer, nullable=False),
        sa.Column('rating', sa.String(10), nullable=False),
        sa.Column('comment', sa.String(500)),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        'uq_order_rating_unique', 'order_rating',
        ['order_id', 'rater_type', 'rater_id']
    )
    op.create_index('ix_order_rating_rated', 'order_rating',
                    ['rated_id', 'rater_type'])

    # 5. Performance indeksi
    op.create_index('ix_listing_brand_active_category', 'supplier_listing',
                    ['brand', 'is_active', 'part_category'])
    op.create_index('ix_part_order_service_ticket', 'part_order',
                    ['service_ticket_id'])
    op.create_index('ix_part_order_status_seller', 'part_order',
                    ['status', 'seller_supplier_id'])
    op.create_index('ix_part_order_expires', 'part_order',
                    ['status', 'expires_at'])


def downgrade():
    # Indeksi
    op.drop_index('ix_part_order_expires')
    op.drop_index('ix_part_order_status_seller')
    op.drop_index('ix_part_order_service_ticket')
    op.drop_index('ix_listing_brand_active_category')

    # OrderRating
    op.drop_index('ix_order_rating_rated')
    op.drop_constraint('uq_order_rating_unique', 'order_rating')
    op.drop_table('order_rating')

    # Part order kolone
    op.drop_column('part_order', 'expires_at')
    op.drop_column('part_order', 'offered_at')
    op.drop_column('part_order', 'delivery_cutoff_time')
    op.drop_column('part_order', 'estimated_delivery_days')
    op.drop_column('part_order', 'delivery_cost')
    op.drop_column('part_order', 'courier_service')
    op.drop_column('part_order', 'delivery_method')
    # OFFERED enum value ne moze da se ukloni iz PostgreSQL
