"""Add SMS delivery status fields and DLR log table

Revision ID: v325_sms_delivery_status
Revises: v324_sms_opt_out
Create Date: 2026-02-01

Dodaje:
- delivery_status, delivery_status_at, delivery_error_code u tenant_sms_usage
- sms_dlr_log tabelu za idempotency DLR webhook-a
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v325_sms_delivery_status'
down_revision = 'v324_sms_opt_out'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Dodaj delivery_status polja u tenant_sms_usage
    op.add_column('tenant_sms_usage', sa.Column(
        'delivery_status',
        sa.String(30),
        nullable=True,
        server_default='pending'
    ))
    op.add_column('tenant_sms_usage', sa.Column(
        'delivery_status_at',
        sa.DateTime(timezone=True),
        nullable=True
    ))
    op.add_column('tenant_sms_usage', sa.Column(
        'delivery_error_code',
        sa.String(20),
        nullable=True
    ))

    # Dodaj indeks na provider_message_id za brže DLR lookup
    op.create_index(
        'ix_sms_usage_provider_message_id',
        'tenant_sms_usage',
        ['provider_message_id']
    )

    # 2. Kreiraj sms_dlr_log tabelu za idempotency
    op.create_table(
        'sms_dlr_log',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('message_id', sa.String(100), nullable=False, unique=True, index=True),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('raw_payload', sa.Text(), nullable=True),
        sa.Column('error_code', sa.String(20), nullable=True),
        sa.Column('received_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    # Drop DLR log table
    op.drop_table('sms_dlr_log')

    # Drop index
    op.drop_index('ix_sms_usage_provider_message_id', 'tenant_sms_usage')

    # Drop columns
    op.drop_column('tenant_sms_usage', 'delivery_error_code')
    op.drop_column('tenant_sms_usage', 'delivery_status_at')
    op.drop_column('tenant_sms_usage', 'delivery_status')
