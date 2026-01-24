"""Add PackageChangeHistory and PackageChangeDelivery tables

Revision ID: x5y6z7a8b9c0
Revises: w4x5y6z7a8b9
Create Date: 2026-01-24

Tabele za verzioniranje promena cena paketa i praćenje dostave notifikacija.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'x5y6z7a8b9c0'
down_revision = 'w4x5y6z7a8b9'
branch_labels = None
depends_on = None


def table_exists(table_name):
    """Check if table exists"""
    conn = op.get_bind()
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = :table
        )
    """), {'table': table_name})
    return result.scalar()


def upgrade():
    # Kreiraj DeliveryStatus enum
    delivery_status = sa.Enum('PENDING', 'SENT', 'FAILED', 'SKIPPED', name='deliverystatus')
    delivery_status.create(op.get_bind(), checkfirst=True)

    # PackageChangeHistory tabela
    if not table_exists('package_change_history'):
        op.create_table('package_change_history',
            sa.Column('id', sa.Integer(), nullable=False),
            # Verzioniranje
            sa.Column('change_date', sa.Date(), nullable=False),
            sa.Column('daily_seq', sa.Integer(), nullable=False),
            # JSON snapshots
            sa.Column('old_settings_json', sa.JSON(), nullable=False),
            sa.Column('new_settings_json', sa.JSON(), nullable=False),
            # Kada stupa na snagu
            sa.Column('effective_at_utc', sa.DateTime(timezone=True), nullable=False),
            sa.Column('effective_timezone', sa.String(50), default='Europe/Belgrade'),
            # Razlog promene
            sa.Column('change_reason', sa.String(500), nullable=True),
            # Idempotency
            sa.Column('idempotency_hash', sa.String(64), nullable=False),
            # Admin
            sa.Column('admin_id', sa.Integer(), nullable=True),
            # Notification stats
            sa.Column('notification_started_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('notification_completed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('tenants_notified', sa.Integer(), default=0),
            sa.Column('emails_sent', sa.Integer(), default=0),
            sa.Column('emails_failed', sa.Integer(), default=0),
            # Timestamp
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
            # Constraints
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['admin_id'], ['platform_admin.id'], ),
            sa.UniqueConstraint('change_date', 'daily_seq', name='uq_package_change_version'),
            sa.UniqueConstraint('idempotency_hash', name='uq_package_idempotency_hash'),
        )

    # PackageChangeDelivery tabela
    if not table_exists('package_change_delivery'):
        op.create_table('package_change_delivery',
            sa.Column('id', sa.Integer(), nullable=False),
            # Veze
            sa.Column('change_id', sa.Integer(), nullable=False),
            sa.Column('tenant_id', sa.Integer(), nullable=False),
            # Email status
            sa.Column('email_status', delivery_status, default='PENDING'),
            sa.Column('email_sent_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('email_error', sa.Text(), nullable=True),
            sa.Column('email_recipient', sa.String(255), nullable=True),
            # In-app status
            sa.Column('inapp_status', delivery_status, default='PENDING'),
            sa.Column('inapp_created_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('inapp_thread_id', sa.Integer(), nullable=True),
            sa.Column('inapp_error', sa.Text(), nullable=True),
            # Timestamp
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
            # Constraints
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['change_id'], ['package_change_history.id'], ),
            sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ),
            sa.UniqueConstraint('change_id', 'tenant_id', name='uq_package_delivery_per_tenant'),
        )

    # Indeksi za performance
    op.create_index('ix_package_change_date', 'package_change_history', ['change_date'], unique=False)
    op.create_index('ix_package_change_admin', 'package_change_history', ['admin_id'], unique=False)
    op.create_index('ix_package_delivery_change', 'package_change_delivery', ['change_id'], unique=False)
    op.create_index('ix_package_delivery_tenant', 'package_change_delivery', ['tenant_id'], unique=False)


def downgrade():
    # Drop indeksi
    op.drop_index('ix_package_delivery_tenant', table_name='package_change_delivery')
    op.drop_index('ix_package_delivery_change', table_name='package_change_delivery')
    op.drop_index('ix_package_change_admin', table_name='package_change_history')
    op.drop_index('ix_package_change_date', table_name='package_change_history')

    # Drop tabele
    op.drop_table('package_change_delivery')
    op.drop_table('package_change_history')

    # Drop enum
    sa.Enum(name='deliverystatus').drop(op.get_bind(), checkfirst=True)