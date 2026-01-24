"""Add Invite and TenantConnection tables

Revision ID: z7a8b9c0d1e2
Revises: y6z7a8b9c0d1
Create Date: 2026-01-24

Tabele za Tenant-to-Tenant networking:
- Invite: Sigurni invite linkovi (hashed tokens)
- TenantConnection: Bidirekciona veza sa dozvolama
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'z7a8b9c0d1e2'
down_revision = 'y6z7a8b9c0d1'
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
    # Kreiraj ConnectionStatus enum
    connection_status = sa.Enum(
        'PENDING_INVITEE', 'PENDING_INVITER', 'ACTIVE', 'BLOCKED',
        name='connectionstatus'
    )
    connection_status.create(op.get_bind(), checkfirst=True)

    # Invite tabela
    if not table_exists('invite'):
        op.create_table('invite',
            sa.Column('id', sa.Integer(), nullable=False),
            # Token (hashed!)
            sa.Column('token_hash', sa.String(64), nullable=False),
            sa.Column('token_hint', sa.String(6), nullable=True),
            # Ko je kreirao
            sa.Column('created_by_tenant_id', sa.Integer(), nullable=False),
            sa.Column('created_by_user_id', sa.Integer(), nullable=True),
            # Poruka
            sa.Column('message', sa.Text(), nullable=True),
            # Ograničenja
            sa.Column('max_uses', sa.Integer(), default=1),
            sa.Column('used_count', sa.Integer(), default=0),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            # Revoke
            sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('revoked_reason', sa.String(200), nullable=True),
            # Timestamp
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
            # Constraints
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['created_by_tenant_id'], ['tenant.id'], ),
            sa.ForeignKeyConstraint(['created_by_user_id'], ['tenant_user.id'], ),
            sa.UniqueConstraint('token_hash', name='uq_invite_token_hash'),
        )

    # TenantConnection tabela
    if not table_exists('tenant_connection'):
        op.create_table('tenant_connection',
            sa.Column('id', sa.Integer(), nullable=False),
            # Oba tenanta (bidirectional)
            sa.Column('tenant_a_id', sa.Integer(), nullable=False),
            sa.Column('tenant_b_id', sa.Integer(), nullable=False),
            # Status
            sa.Column('status', connection_status, default='PENDING_INVITEE'),
            # Invite koji je korišćen
            sa.Column('invite_id', sa.Integer(), nullable=True),
            # Ko je inicirao
            sa.Column('initiated_by_tenant_id', sa.Integer(), nullable=True),
            # Dozvole
            sa.Column('permissions_json', sa.JSON(), nullable=True),
            # Block info
            sa.Column('blocked_by_tenant_id', sa.Integer(), nullable=True),
            sa.Column('blocked_reason', sa.String(200), nullable=True),
            sa.Column('blocked_at', sa.DateTime(timezone=True), nullable=True),
            # Timestamps
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('connected_at', sa.DateTime(timezone=True), nullable=True),
            # Constraints
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['tenant_a_id'], ['tenant.id'], ),
            sa.ForeignKeyConstraint(['tenant_b_id'], ['tenant.id'], ),
            sa.ForeignKeyConstraint(['invite_id'], ['invite.id'], ),
            sa.ForeignKeyConstraint(['initiated_by_tenant_id'], ['tenant.id'], ),
            sa.ForeignKeyConstraint(['blocked_by_tenant_id'], ['tenant.id'], ),
            sa.UniqueConstraint('tenant_a_id', 'tenant_b_id', name='uq_tenant_connection'),
            sa.CheckConstraint('tenant_a_id < tenant_b_id', name='ck_tenant_order'),
        )

    # Indeksi za performance
    op.create_index('ix_invite_token_hash', 'invite', ['token_hash'], unique=True)
    op.create_index('ix_invite_created_by_tenant', 'invite', ['created_by_tenant_id'], unique=False)
    op.create_index('ix_invite_expires', 'invite', ['expires_at'], unique=False)
    op.create_index('ix_connection_tenant_a', 'tenant_connection', ['tenant_a_id'], unique=False)
    op.create_index('ix_connection_tenant_b', 'tenant_connection', ['tenant_b_id'], unique=False)
    op.create_index('ix_connection_status', 'tenant_connection', ['status'], unique=False)


def downgrade():
    # Drop indeksi
    op.drop_index('ix_connection_status', table_name='tenant_connection')
    op.drop_index('ix_connection_tenant_b', table_name='tenant_connection')
    op.drop_index('ix_connection_tenant_a', table_name='tenant_connection')
    op.drop_index('ix_invite_expires', table_name='invite')
    op.drop_index('ix_invite_created_by_tenant', table_name='invite')
    op.drop_index('ix_invite_token_hash', table_name='invite')

    # Drop tabele
    op.drop_table('tenant_connection')
    op.drop_table('invite')

    # Drop enum
    sa.Enum(name='connectionstatus').drop(op.get_bind(), checkfirst=True)