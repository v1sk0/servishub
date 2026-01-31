"""Add Notification System tables

Revision ID: v320_notification
Revises: flash_services_01, google_photos
Create Date: 2026-01-31

This migration adds:
- admin_notification_settings: Global notification settings (singleton)
- notification_log: Log of all sent notifications
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'v320_notification'
down_revision = ('flash_services_01', 'google_photos')  # Merge migration
branch_labels = None
depends_on = None


def upgrade():
    # =========================================================================
    # 1. Nova tabela: admin_notification_settings (singleton)
    # =========================================================================
    op.create_table(
        'admin_notification_settings',
        sa.Column('id', sa.Integer(), primary_key=True),

        # Primaoci
        sa.Column('email_recipients', postgresql.JSON(astext_type=sa.Text()), server_default='[]'),
        sa.Column('sms_recipients', postgresql.JSON(astext_type=sa.Text()), server_default='[]'),

        # Security events
        sa.Column('notify_failed_login', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('notify_new_device', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('notify_password_change', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('notify_2fa_disabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('notify_suspicious', sa.Boolean(), nullable=False, server_default='true'),

        # Billing events
        sa.Column('notify_new_payment', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('notify_payment_overdue', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('notify_suspension', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('notify_expiring', sa.Boolean(), nullable=False, server_default='true'),

        # System events
        sa.Column('notify_new_tenant', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('notify_kyc_submitted', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('notify_daily_summary', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('notify_weekly_report', sa.Boolean(), nullable=False, server_default='true'),

        # Thresholds
        sa.Column('failed_login_threshold', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('overdue_days_threshold', sa.Integer(), nullable=False, server_default='7'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    )

    # =========================================================================
    # 2. Nova tabela: notification_log
    # =========================================================================
    op.create_table(
        'notification_log',
        sa.Column('id', sa.BigInteger(), primary_key=True),

        # Tip i kanal
        sa.Column('notification_type', sa.String(50), nullable=False),
        sa.Column('channel', sa.String(20), nullable=False, server_default='email'),

        # Primalac i sadrzaj
        sa.Column('recipient', sa.String(200), nullable=False),
        sa.Column('subject', sa.String(300)),
        sa.Column('content', sa.Text()),

        # Status
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('error_message', sa.Text()),

        # Payload za debugging
        sa.Column('payload', postgresql.JSON(astext_type=sa.Text()), server_default='{}'),

        # Idempotency
        sa.Column('event_key', sa.String(200)),

        # Reference
        sa.Column('related_tenant_id', sa.Integer(),
                  sa.ForeignKey('tenant.id', ondelete='SET NULL'), nullable=True),
        sa.Column('related_admin_id', sa.Integer(),
                  sa.ForeignKey('platform_admin.id', ondelete='SET NULL'), nullable=True),

        # Request context
        sa.Column('ip_address', sa.String(50)),
        sa.Column('user_agent', sa.String(500)),

        # Timestamps
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('sent_at', sa.DateTime()),
    )

    # Indeksi za notification_log
    op.create_index('ix_notification_log_type', 'notification_log', ['notification_type'])
    op.create_index('ix_notification_log_status', 'notification_log', ['status'])
    op.create_index('ix_notification_log_created', 'notification_log', ['created_at'])
    op.create_index('ix_notification_log_tenant', 'notification_log', ['related_tenant_id'])
    op.create_index('ix_notification_log_type_created', 'notification_log', ['notification_type', 'created_at'])
    op.create_index('ix_notification_log_event_key_status', 'notification_log', ['event_key', 'status'])

    # =========================================================================
    # 3. Seed: Kreiraj default settings row
    # =========================================================================
    op.execute("""
        INSERT INTO admin_notification_settings (id, email_recipients, sms_recipients)
        VALUES (1, '[]', '[]')
        ON CONFLICT (id) DO NOTHING
    """)


def downgrade():
    op.drop_table('notification_log')
    op.drop_table('admin_notification_settings')
