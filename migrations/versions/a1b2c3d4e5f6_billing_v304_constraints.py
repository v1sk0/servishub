"""billing v304 constraints

Revision ID: a1b2c3d4e5f6
Revises: z7a8b9c0d1e2
Create Date: 2026-01-25

Adds:
- UNIQUE constraint on payment_reference
- UNIQUE constraint on (tenant_id, period_start) for idempotency
- payment_reference_normalized column with INDEX for performance
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'v305_send_invoice_action_type'
branch_labels = None
depends_on = None


def upgrade():
    # 1. UNIQUE constraint na payment_reference
    # Audit prethodn - nema duplikata, safe to add
    op.create_unique_constraint(
        'uq_subscription_payment_reference',
        'subscription_payment',
        ['payment_reference']
    )

    # 2. UNIQUE constraint na (tenant_id, period_start) za idempotency
    # Sprecava kreiranje duplih faktura za isti period
    op.create_unique_constraint(
        'uq_tenant_period',
        'subscription_payment',
        ['tenant_id', 'period_start']
    )

    # 3. Dodaj payment_reference_normalized kolonu za performanse
    # Cuva normalizovanu referencu (samo cifre) za brzi DB lookup
    op.add_column(
        'subscription_payment',
        sa.Column('payment_reference_normalized', sa.String(25), nullable=True)
    )

    # 4. Popuni postojece zapise
    op.execute("""
        UPDATE subscription_payment
        SET payment_reference_normalized = regexp_replace(payment_reference, '[^0-9]', '', 'g')
        WHERE payment_reference IS NOT NULL
          AND payment_reference_normalized IS NULL
    """)

    # 5. Kreiraj INDEX na normalizovanoj koloni
    op.create_index(
        'idx_payment_ref_normalized',
        'subscription_payment',
        ['payment_reference_normalized']
    )


def downgrade():
    # Ukloni INDEX
    op.drop_index('idx_payment_ref_normalized', table_name='subscription_payment')

    # Ukloni kolonu
    op.drop_column('subscription_payment', 'payment_reference_normalized')

    # Ukloni UNIQUE constraint-e
    op.drop_constraint('uq_tenant_period', 'subscription_payment', type_='unique')
    op.drop_constraint('uq_subscription_payment_reference', 'subscription_payment', type_='unique')