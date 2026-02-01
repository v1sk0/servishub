"""Tenant SMS notification settings - user opt-in fields

Revision ID: v322_tenant_sms_settings
Revises: v321_sms_management
Create Date: 2026-02-01

Dodaje polja za SMS notifikacije u tenant tabelu:
- sms_notifications_enabled: Da li je SMS uključen (default: False)
- sms_notifications_consent_given: Da li je data saglasnost za naplatu
- sms_notifications_activated_at: Kada je tenant aktivirao SMS
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v322_tenant_sms_settings'
down_revision = 'v321_sms_management'
branch_labels = None
depends_on = None


def upgrade():
    # Dodaj SMS notification polja u tenant tabelu
    # Sve kolone su default False/None jer SMS je opt-in
    op.add_column('tenant', sa.Column(
        'sms_notifications_enabled',
        sa.Boolean(),
        nullable=False,
        server_default='false'
    ))
    op.add_column('tenant', sa.Column(
        'sms_notifications_consent_given',
        sa.Boolean(),
        nullable=False,
        server_default='false'
    ))
    op.add_column('tenant', sa.Column(
        'sms_notifications_activated_at',
        sa.DateTime(),
        nullable=True
    ))


def downgrade():
    op.drop_column('tenant', 'sms_notifications_activated_at')
    op.drop_column('tenant', 'sms_notifications_consent_given')
    op.drop_column('tenant', 'sms_notifications_enabled')
