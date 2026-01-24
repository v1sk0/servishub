"""Add MessageThread, ThreadParticipant, and Message tables

Revision ID: y6z7a8b9c0d1
Revises: x5y6z7a8b9c0
Create Date: 2026-01-24

Threaded messaging sistem za:
- SYSTEM notifikacije (read-only)
- SUPPORT konverzacije (tenant ↔ admin)
- NETWORK komunikacija (tenant ↔ tenant)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'y6z7a8b9c0d1'
down_revision = 'x5y6z7a8b9c0'
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


def enum_exists(enum_name):
    """Check if PostgreSQL enum type exists"""
    conn = op.get_bind()
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_type WHERE typname = :enum_name
        )
    """), {'enum_name': enum_name})
    return result.scalar()


def upgrade():
    # NAPOMENA: Koristimo String umesto PostgreSQL ENUM za sve type/status kolone
    # Enum konverzija se radi u Python modelu

    # MessageThread tabela
    if not table_exists('message_thread'):
        op.create_table('message_thread',
            sa.Column('id', sa.Integer(), nullable=False),
            # Vlasnik
            sa.Column('tenant_id', sa.Integer(), nullable=False),
            # Tip i status - String umesto Enum
            sa.Column('thread_type', sa.String(20), nullable=False),
            sa.Column('status', sa.String(20), server_default='OPEN'),
            # Naslov i tagovi
            sa.Column('subject', sa.String(200), nullable=False),
            sa.Column('tags', sa.JSON(), nullable=True),
            # SLA tracking
            sa.Column('assigned_to_id', sa.Integer(), nullable=True),
            sa.Column('first_response_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('last_reply_at', sa.DateTime(timezone=True), nullable=True),
            # Network veza
            sa.Column('connection_id', sa.Integer(), nullable=True),
            sa.Column('other_tenant_id', sa.Integer(), nullable=True),
            # Timestamps
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
            # Constraints
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ),
            sa.ForeignKeyConstraint(['assigned_to_id'], ['platform_admin.id'], ),
            sa.ForeignKeyConstraint(['other_tenant_id'], ['tenant.id'], ),
        )

    # ThreadParticipant tabela
    if not table_exists('thread_participant'):
        op.create_table('thread_participant',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('thread_id', sa.Integer(), nullable=False),
            # Učesnik (jedan od tri)
            sa.Column('tenant_id', sa.Integer(), nullable=True),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('admin_id', sa.Integer(), nullable=True),
            # Role i read tracking
            sa.Column('role', sa.String(20), nullable=True),
            sa.Column('last_read_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('unread_count', sa.Integer(), default=0),
            # Timestamp
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
            # Constraints
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['thread_id'], ['message_thread.id'], ),
            sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ),
            sa.ForeignKeyConstraint(['user_id'], ['tenant_user.id'], ),
            sa.ForeignKeyConstraint(['admin_id'], ['platform_admin.id'], ),
        )

    # Message tabela
    if not table_exists('message'):
        op.create_table('message',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('thread_id', sa.Integer(), nullable=False),
            # Pošiljalac (jedan od tri)
            sa.Column('sender_tenant_id', sa.Integer(), nullable=True),
            sa.Column('sender_user_id', sa.Integer(), nullable=True),
            sa.Column('sender_admin_id', sa.Integer(), nullable=True),
            # Sadržaj
            sa.Column('body', sa.Text(), nullable=False),
            sa.Column('category', sa.String(50), nullable=True),
            # Edit audit
            sa.Column('is_edited', sa.Boolean(), default=False),
            sa.Column('edited_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('edit_history_json', sa.JSON(), nullable=True),
            # Soft delete
            sa.Column('is_hidden', sa.Boolean(), default=False),
            sa.Column('hidden_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('hidden_by_id', sa.Integer(), nullable=True),
            sa.Column('hidden_by_type', sa.String(20), nullable=True),
            sa.Column('hidden_reason', sa.String(200), nullable=True),
            # Timestamp
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
            # Constraints
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['thread_id'], ['message_thread.id'], ),
            sa.ForeignKeyConstraint(['sender_tenant_id'], ['tenant.id'], ),
            sa.ForeignKeyConstraint(['sender_user_id'], ['tenant_user.id'], ),
            sa.ForeignKeyConstraint(['sender_admin_id'], ['platform_admin.id'], ),
        )

    # Indeksi za performance
    op.create_index('ix_thread_tenant_status', 'message_thread', ['tenant_id', 'status'], unique=False)
    op.create_index('ix_thread_type_status', 'message_thread', ['thread_type', 'status'], unique=False)
    op.create_index('ix_thread_assigned', 'message_thread', ['assigned_to_id'], unique=False)
    op.create_index('ix_message_thread_created', 'message', ['thread_id', 'created_at'], unique=False)
    op.create_index('ix_participant_user_thread', 'thread_participant', ['user_id', 'thread_id'], unique=False)
    op.create_index('ix_participant_tenant_thread', 'thread_participant', ['tenant_id', 'thread_id'], unique=False)


def downgrade():
    # Drop indeksi
    op.drop_index('ix_participant_tenant_thread', table_name='thread_participant')
    op.drop_index('ix_participant_user_thread', table_name='thread_participant')
    op.drop_index('ix_message_thread_created', table_name='message')
    op.drop_index('ix_thread_assigned', table_name='message_thread')
    op.drop_index('ix_thread_type_status', table_name='message_thread')
    op.drop_index('ix_thread_tenant_status', table_name='message_thread')

    # Drop tabele
    op.drop_table('message')
    op.drop_table('thread_participant')
    op.drop_table('message_thread')