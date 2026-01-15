"""Add DEMO status, bank_account, OAuth and SMS verification fields

Revision ID: b3c4d5e6f7g8
Revises: a2b3c4d5e6f7
Create Date: 2026-01-15 14:00:00.000000

Dodaje:
- DEMO u TenantStatus enum (zamena za PENDING)
- bank_account polje u tenant tabelu
- demo_ends_at polje u tenant tabelu
- Google OAuth polja u tenant_user (google_id, auth_provider)
- SMS verifikacija polja u tenant_user (phone_verification_code, phone_verification_expires, phone_verified)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3c4d5e6f7g8'
down_revision = 'a2b3c4d5e6f7'
branch_labels = None
depends_on = None


def upgrade():
    # Dodaj nova polja u tenant tabelu
    with op.batch_alter_table('tenant', schema=None) as batch_op:
        # Bankovni racun
        batch_op.add_column(sa.Column('bank_account', sa.String(length=50), nullable=True))
        # Demo period istek
        batch_op.add_column(sa.Column('demo_ends_at', sa.DateTime(), nullable=True))

    # Dodaj nova polja u tenant_user tabelu
    with op.batch_alter_table('tenant_user', schema=None) as batch_op:
        # Google OAuth polja
        batch_op.add_column(sa.Column('google_id', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('auth_provider', sa.String(length=20), nullable=True, server_default='email'))

        # SMS verifikacija polja
        batch_op.add_column(sa.Column('phone_verification_code', sa.String(length=6), nullable=True))
        batch_op.add_column(sa.Column('phone_verification_expires', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('phone_verified', sa.Boolean(), nullable=True, server_default='false'))

        # Unique constraint za google_id
        batch_op.create_index('ix_tenant_user_google_id', ['google_id'], unique=True)

    # Update TenantStatus enum - dodaj DEMO vrednost
    # PostgreSQL enum update
    op.execute("ALTER TYPE tenantstatus ADD VALUE IF NOT EXISTS 'DEMO'")

    # Prebaci sve PENDING statuse u DEMO
    op.execute("UPDATE tenant SET status = 'DEMO' WHERE status = 'PENDING'")


def downgrade():
    # Ukloni nova polja iz tenant_user tabele
    with op.batch_alter_table('tenant_user', schema=None) as batch_op:
        batch_op.drop_index('ix_tenant_user_google_id')
        batch_op.drop_column('phone_verified')
        batch_op.drop_column('phone_verification_expires')
        batch_op.drop_column('phone_verification_code')
        batch_op.drop_column('auth_provider')
        batch_op.drop_column('google_id')

    # Ukloni nova polja iz tenant tabele
    with op.batch_alter_table('tenant', schema=None) as batch_op:
        batch_op.drop_column('demo_ends_at')
        batch_op.drop_column('bank_account')

    # Prebaci DEMO nazad u PENDING
    op.execute("UPDATE tenant SET status = 'PENDING' WHERE status = 'DEMO'")

    # Napomena: Brisanje vrednosti iz PostgreSQL enum-a je kompleksno
    # i obicno se ne radi u downgrade migracijama