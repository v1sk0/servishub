"""SMS Management - tenant SMS limits and usage tracking

Revision ID: v321_sms_management
Revises: v320_notification_system
Create Date: 2026-02-01

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v321_sms_management'
down_revision = 'v320_notification_system'
branch_labels = None
depends_on = None


def upgrade():
    # ====== TenantSmsConfig ======
    op.create_table('tenant_sms_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('sms_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('monthly_limit', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('warning_threshold_percent', sa.Integer(), nullable=False, server_default='20'),
        sa.Column('warning_sent_this_month', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('custom_sender_id', sa.String(20), nullable=True),
        sa.Column('admin_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id')
    )
    op.create_index('ix_tenant_sms_config_tenant_id', 'tenant_sms_config', ['tenant_id'])

    # ====== TenantSmsUsage ======
    op.create_table('tenant_sms_usage',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('sms_type', sa.String(50), nullable=False),
        sa.Column('recipient_masked', sa.String(20), nullable=True),
        sa.Column('reference_type', sa.String(30), nullable=True),
        sa.Column('reference_id', sa.BigInteger(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('provider_message_id', sa.String(100), nullable=True),
        sa.Column('cost', sa.Numeric(10, 4), nullable=True, server_default='0'),
        sa.Column('initiated_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['initiated_by_user_id'], ['tenant_user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_tenant_sms_usage_tenant_id', 'tenant_sms_usage', ['tenant_id'])
    op.create_index('ix_tenant_sms_usage_sms_type', 'tenant_sms_usage', ['sms_type'])
    op.create_index('ix_tenant_sms_usage_created_at', 'tenant_sms_usage', ['created_at'])
    op.create_index('ix_sms_usage_tenant_created', 'tenant_sms_usage', ['tenant_id', 'created_at'])
    op.create_index('ix_sms_usage_type_status', 'tenant_sms_usage', ['sms_type', 'status'])

    # ====== TicketNotificationLog new columns ======
    # Add new columns to existing ticket_notification_log table
    op.add_column('ticket_notification_log', sa.Column('recipient', sa.String(100), nullable=True))
    op.add_column('ticket_notification_log', sa.Column('status', sa.String(20), nullable=True))
    op.add_column('ticket_notification_log', sa.Column('message', sa.Text(), nullable=True))


def downgrade():
    # Remove TicketNotificationLog new columns
    op.drop_column('ticket_notification_log', 'message')
    op.drop_column('ticket_notification_log', 'status')
    op.drop_column('ticket_notification_log', 'recipient')

    # Drop TenantSmsUsage
    op.drop_index('ix_sms_usage_type_status', table_name='tenant_sms_usage')
    op.drop_index('ix_sms_usage_tenant_created', table_name='tenant_sms_usage')
    op.drop_index('ix_tenant_sms_usage_created_at', table_name='tenant_sms_usage')
    op.drop_index('ix_tenant_sms_usage_sms_type', table_name='tenant_sms_usage')
    op.drop_index('ix_tenant_sms_usage_tenant_id', table_name='tenant_sms_usage')
    op.drop_table('tenant_sms_usage')

    # Drop TenantSmsConfig
    op.drop_index('ix_tenant_sms_config_tenant_id', table_name='tenant_sms_config')
    op.drop_table('tenant_sms_config')
