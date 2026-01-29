"""v3.17: Add dual-currency support to Receipt and DailyReport

- Receipt.currency: RSD/EUR (for fiscal vs internal mode)
- DailyReport: EUR totals for non-fiscal receipts

Revision ID: v317_dual_currency
Revises: v310_add_promo_months
Create Date: 2026-01-29

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v317_dual_currency'
down_revision = 'v310_add_promo_months'
branch_labels = None
depends_on = None


def upgrade():
    # Receipt.currency field (default RSD)
    op.add_column('receipt',
                  sa.Column('currency', sa.String(3), nullable=False, server_default='RSD'))

    # DailyReport EUR fields
    op.add_column('daily_report',
                  sa.Column('total_revenue_eur', sa.Numeric(12, 2), nullable=True, server_default='0'))
    op.add_column('daily_report',
                  sa.Column('total_cash_eur', sa.Numeric(12, 2), nullable=True, server_default='0'))
    op.add_column('daily_report',
                  sa.Column('total_card_eur', sa.Numeric(12, 2), nullable=True, server_default='0'))
    op.add_column('daily_report',
                  sa.Column('total_transfer_eur', sa.Numeric(12, 2), nullable=True, server_default='0'))


def downgrade():
    # Remove Receipt.currency
    op.drop_column('receipt', 'currency')

    # Remove DailyReport EUR fields
    op.drop_column('daily_report', 'total_revenue_eur')
    op.drop_column('daily_report', 'total_cash_eur')
    op.drop_column('daily_report', 'total_card_eur')
    op.drop_column('daily_report', 'total_transfer_eur')
