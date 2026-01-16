"""Add AdminActivityLog table for tracking admin actions

Revision ID: c4d5e6f7g8h9
Revises: b3c4d5e6f7g8
Create Date: 2026-01-16 12:00:00.000000

Dodaje:
- AdminActionType enum
- admin_activity_log tabelu za pracenje admin akcija
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4d5e6f7g8h9'
down_revision = 'b3c4d5e6f7g8'
branch_labels = None
depends_on = None


def upgrade():
    # Kreiraj AdminActionType enum
    adminactiontype = sa.Enum(
        'ACTIVATE_TRIAL',
        'ACTIVATE_SUBSCRIPTION',
        'SUSPEND_TENANT',
        'UNSUSPEND_TENANT',
        'EXTEND_TRIAL',
        'KYC_VERIFY',
        'KYC_REJECT',
        'KYC_REQUEST_RESUBMIT',
        'UPDATE_TENANT',
        'DELETE_TENANT',
        'UPDATE_LOCATIONS',
        name='adminactiontype'
    )

    # Kreiraj admin_activity_log tabelu
    op.create_table(
        'admin_activity_log',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('admin_id', sa.Integer(), nullable=True),
        sa.Column('admin_email', sa.String(length=100), nullable=True),
        sa.Column('action_type', adminactiontype, nullable=False),
        sa.Column('target_type', sa.String(length=50), nullable=False),
        sa.Column('target_id', sa.Integer(), nullable=False),
        sa.Column('target_name', sa.String(length=200), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('old_status', sa.String(length=50), nullable=True),
        sa.Column('new_status', sa.String(length=50), nullable=True),
        sa.Column('ip_address', sa.String(length=50), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['admin_id'], ['platform_admin.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # Kreiraj indekse
    op.create_index('ix_admin_activity_log_action_type', 'admin_activity_log', ['action_type'], unique=False)
    op.create_index('ix_admin_activity_log_admin_id', 'admin_activity_log', ['admin_id'], unique=False)
    op.create_index('ix_admin_activity_log_created_at', 'admin_activity_log', ['created_at'], unique=False)
    op.create_index('ix_admin_activity_target', 'admin_activity_log', ['target_type', 'target_id'], unique=False)
    op.create_index('ix_admin_activity_admin_created', 'admin_activity_log', ['admin_id', 'created_at'], unique=False)


def downgrade():
    # Obrisi indekse
    op.drop_index('ix_admin_activity_admin_created', table_name='admin_activity_log')
    op.drop_index('ix_admin_activity_target', table_name='admin_activity_log')
    op.drop_index('ix_admin_activity_log_created_at', table_name='admin_activity_log')
    op.drop_index('ix_admin_activity_log_admin_id', table_name='admin_activity_log')
    op.drop_index('ix_admin_activity_log_action_type', table_name='admin_activity_log')

    # Obrisi tabelu
    op.drop_table('admin_activity_log')

    # Obrisi enum tip
    op.execute('DROP TYPE IF EXISTS adminactiontype')