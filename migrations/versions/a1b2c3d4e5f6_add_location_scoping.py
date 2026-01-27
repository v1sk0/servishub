"""Add LocationStatus, current_location_id, UserLocation fields, location scoping

Revision ID: a1b2c3d4e5f6
Revises: z7a8b9c0d1e2
Create Date: 2026-01-27

Task-001: Location scoping infrastructure
- LocationStatus enum (ACTIVE, INACTIVE, ARCHIVED)
- ServiceLocation: status, archived_at, archived_by_id
- UserLocation: role_at_location, assigned_at
- TenantUser: current_location_id
- Partial unique index za is_primary per tenant
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'z7a8b9c0d1e2'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Kreiraj LocationStatus enum
    location_status_enum = sa.Enum('ACTIVE', 'INACTIVE', 'ARCHIVED', name='locationstatus')
    location_status_enum.create(op.get_bind(), checkfirst=True)

    # 2. ServiceLocation: dodaj status, archived_at, archived_by_id
    op.add_column('service_location', sa.Column(
        'status', sa.Enum('ACTIVE', 'INACTIVE', 'ARCHIVED', name='locationstatus'),
        nullable=True
    ))
    # Postavi default vrednost za postojece redove
    op.execute("UPDATE service_location SET status = 'ACTIVE' WHERE is_active = true")
    op.execute("UPDATE service_location SET status = 'INACTIVE' WHERE is_active = false")
    op.alter_column('service_location', 'status', nullable=False)

    op.add_column('service_location', sa.Column('archived_at', sa.DateTime(), nullable=True))
    op.add_column('service_location', sa.Column(
        'archived_by_id', sa.Integer(), sa.ForeignKey('tenant_user.id'), nullable=True
    ))

    # 3. UserLocation: dodaj role_at_location, assigned_at
    op.add_column('user_location', sa.Column(
        'role_at_location', sa.String(30), nullable=True
    ))
    op.add_column('user_location', sa.Column(
        'assigned_at', sa.DateTime(), nullable=True
    ))
    # Postavi assigned_at na created_at za postojece redove
    op.execute("UPDATE user_location SET assigned_at = created_at")

    # 4. TenantUser: dodaj current_location_id
    op.add_column('tenant_user', sa.Column(
        'current_location_id', sa.Integer(),
        sa.ForeignKey('service_location.id', ondelete='SET NULL'),
        nullable=True
    ))
    op.create_index('ix_tenant_user_current_location_id', 'tenant_user', ['current_location_id'])

    # 5. Partial unique index: samo jedna primary lokacija po tenantu
    op.create_index(
        'ix_unique_primary_per_tenant',
        'service_location',
        ['tenant_id'],
        unique=True,
        postgresql_where=text("is_primary = true")
    )


def downgrade():
    op.drop_index('ix_unique_primary_per_tenant', table_name='service_location')
    op.drop_index('ix_tenant_user_current_location_id', table_name='tenant_user')
    op.drop_column('tenant_user', 'current_location_id')
    op.drop_column('user_location', 'assigned_at')
    op.drop_column('user_location', 'role_at_location')
    op.drop_column('service_location', 'archived_by_id')
    op.drop_column('service_location', 'archived_at')
    op.drop_column('service_location', 'status')

    # Drop enum
    sa.Enum(name='locationstatus').drop(op.get_bind(), checkfirst=True)
