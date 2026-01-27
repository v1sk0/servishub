"""Add feature_flag table and seed initial flags

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-01-27

Task-003: Feature flags za staged rollout
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d4e5f6g7h8'
down_revision = 'b2c3d4e5f6g7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'feature_flag',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('feature_key', sa.String(50), nullable=False, index=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenant.id'), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, default=False),
        sa.Column('created_at', sa.DateTime()),
        sa.UniqueConstraint('feature_key', 'tenant_id', name='uq_feature_tenant'),
    )

    # Seed initial flags (global defaults)
    op.execute("""
        INSERT INTO feature_flag (feature_key, tenant_id, enabled, created_at)
        VALUES
            ('credits_enabled', NULL, FALSE, NOW()),
            ('pos_enabled', NULL, FALSE, NOW()),
            ('b2c_marketplace_enabled', NULL, FALSE, NOW()),
            ('anonymous_b2b_enabled', NULL, FALSE, NOW()),
            ('location_scoping_enabled', NULL, TRUE, NOW())
    """)

    # Dodaj BLOCKED u tenantstatus enum (ako ne postoji)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'BLOCKED'
                          AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'tenantstatus')) THEN
                ALTER TYPE tenantstatus ADD VALUE 'BLOCKED';
            END IF;
        END$$;
    """)


def downgrade():
    op.drop_table('feature_flag')
    # Ne uklanjamo BLOCKED iz enum-a — PostgreSQL ne dozvoljava DROP VALUE
