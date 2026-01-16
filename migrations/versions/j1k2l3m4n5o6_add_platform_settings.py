"""Add platform_settings table and UPDATE_SETTINGS action type

Revision ID: j1k2l3m4n5o6
Revises: i0j1k2l3m4n5
Create Date: 2026-01-16 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'j1k2l3m4n5o6'
down_revision = 'i0j1k2l3m4n5'
branch_labels = None
depends_on = None


def upgrade():
    # Dodaj UPDATE_SETTINGS u adminactiontype enum
    op.execute("ALTER TYPE adminactiontype ADD VALUE IF NOT EXISTS 'UPDATE_SETTINGS'")

    # Kreiraj platform_settings tabelu
    op.create_table('platform_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('base_price', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('location_price', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=True),
        sa.Column('trial_days', sa.Integer(), nullable=True),
        sa.Column('demo_days', sa.Integer(), nullable=True),
        sa.Column('grace_period_days', sa.Integer(), nullable=True),
        sa.Column('default_commission', sa.Numeric(precision=4, scale=2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_by_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['updated_by_id'], ['platform_admin.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Dodaj initial red sa default vrednostima
    op.execute("""
        INSERT INTO platform_settings (base_price, location_price, currency, trial_days, demo_days, grace_period_days, default_commission, created_at)
        VALUES (3600.00, 1800.00, 'RSD', 90, 7, 7, 5.00, NOW())
    """)


def downgrade():
    op.drop_table('platform_settings')
    # Ne mozemo da uklonimo enum vrednost u PostgreSQL-u bez rekreiranja enuma