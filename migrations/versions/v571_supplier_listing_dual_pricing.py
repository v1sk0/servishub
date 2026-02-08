"""v571: Add dual pricing (price_rsd, price_eur) to SupplierListing + eur_rate to Supplier

Revision ID: v571_dual_pricing
Revises: v570_supplier_action_types
Create Date: 2026-02-07

Svaki SupplierListing sada ima DVE cene: price_rsd i price_eur.
Dobavljac unosi jednu, sistem auto-preracunava drugu po kursu.
Supplier model dobija eur_rate polje za kurs po dobavljacu.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v571_dual_pricing'
down_revision = 'v570_supplier_action_types'
branch_labels = None
depends_on = None


def upgrade():
    # Dodaj price_rsd i price_eur na SupplierListing
    op.add_column('supplier_listing', sa.Column('price_rsd', sa.Numeric(10, 2)))
    op.add_column('supplier_listing', sa.Column('price_eur', sa.Numeric(10, 2)))

    # Dodaj eur_rate na Supplier (kurs po dobavljacu)
    op.add_column('supplier', sa.Column('eur_rate', sa.Numeric(8, 4), server_default='117.5'))

    # Migriraj postojece podatke iz price+currency u nova polja
    op.execute("""
        UPDATE supplier_listing
        SET price_rsd = CASE
                WHEN currency = 'EUR' THEN ROUND(price * 117.5, 2)
                ELSE price
            END,
            price_eur = CASE
                WHEN currency = 'EUR' THEN price
                ELSE ROUND(price / 117.5, 2)
            END
        WHERE price IS NOT NULL
    """)


def downgrade():
    op.drop_column('supplier_listing', 'price_rsd')
    op.drop_column('supplier_listing', 'price_eur')
    op.drop_column('supplier', 'eur_rate')