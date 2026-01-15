"""Add Dolce Vita style ticket fields and notification log

Revision ID: a2b3c4d5e6f7
Revises: fcf637132d14
Create Date: 2026-01-15 12:00:00.000000

Dodaje nova polja u service_ticket tabelu za Dolce Vita stil:
- B2B kupac podaci (firma, PIB)
- Stanje uredjaja (ABC ocena)
- Problem areas (JSON)
- Write-off sistem
- SMS notifikacije
- Fakturisanje

Kreira novu tabelu ticket_notification_log za pracenje poziva kupcima.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a2b3c4d5e6f7'
down_revision = 'fcf637132d14'
branch_labels = None
depends_on = None


def upgrade():
    # Dodaj nova polja u service_ticket tabelu
    with op.batch_alter_table('service_ticket', schema=None) as batch_op:
        # B2B kupac podaci
        batch_op.add_column(sa.Column('customer_company_name', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('customer_pib', sa.String(length=15), nullable=True))

        # Kategorija servisa
        batch_op.add_column(sa.Column('service_section', sa.String(length=50), nullable=True))

        # Stanje uredjaja - ABC ocena
        batch_op.add_column(sa.Column('device_condition_grade', sa.String(length=1), nullable=True))
        batch_op.add_column(sa.Column('device_condition_notes', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('device_not_working', sa.Boolean(), nullable=True, server_default='false'))

        # Problem areas - JSON
        batch_op.add_column(sa.Column('problem_areas', sa.Text(), nullable=True))

        # Ko je preuzeo uredjaj
        batch_op.add_column(sa.Column('owner_collect', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('owner_collect_timestamp', sa.DateTime(timezone=True), nullable=True))

        # Trajanje popravke
        batch_op.add_column(sa.Column('complete_duration', sa.Integer(), nullable=True))

        # Napomene za servisera
        batch_op.add_column(sa.Column('ticket_notes', sa.Text(), nullable=True))

        # Write-off sistem
        batch_op.add_column(sa.Column('is_written_off', sa.Boolean(), nullable=True, server_default='false'))
        batch_op.add_column(sa.Column('written_off_timestamp', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('written_off_by_id', sa.Integer(), nullable=True))

        # SMS notifikacije flagovi
        batch_op.add_column(sa.Column('sms_notification_completed', sa.Boolean(), nullable=True, server_default='false'))
        batch_op.add_column(sa.Column('sms_notification_10_days', sa.Boolean(), nullable=True, server_default='false'))
        batch_op.add_column(sa.Column('sms_notification_30_days', sa.Boolean(), nullable=True, server_default='false'))

        # Fakturisanje
        batch_op.add_column(sa.Column('billing_status', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('invoice_number', sa.String(length=20), nullable=True))

        # Indeks za is_written_off
        batch_op.create_index('ix_service_ticket_is_written_off', ['is_written_off'], unique=False)

        # Foreign key za written_off_by_id
        batch_op.create_foreign_key(
            'fk_service_ticket_written_off_by',
            'tenant_user',
            ['written_off_by_id'],
            ['id'],
            ondelete='SET NULL'
        )

    # Kreiraj ticket_notification_log tabelu
    op.create_table('ticket_notification_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticket_id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('notification_type', sa.String(length=20), nullable=True, server_default='CALL'),
        sa.Column('contact_successful', sa.Boolean(), nullable=True, server_default='false'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['ticket_id'], ['service_ticket.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['tenant_user.id'], ondelete='SET NULL')
    )
    with op.batch_alter_table('ticket_notification_log', schema=None) as batch_op:
        batch_op.create_index('ix_ticket_notification_log_ticket_id', ['ticket_id'], unique=False)
        batch_op.create_index('ix_notification_ticket_timestamp', ['ticket_id', 'timestamp'], unique=False)


def downgrade():
    # Obrisi ticket_notification_log tabelu
    op.drop_table('ticket_notification_log')

    # Ukloni nova polja iz service_ticket tabele
    with op.batch_alter_table('service_ticket', schema=None) as batch_op:
        batch_op.drop_constraint('fk_service_ticket_written_off_by', type_='foreignkey')
        batch_op.drop_index('ix_service_ticket_is_written_off')

        batch_op.drop_column('invoice_number')
        batch_op.drop_column('billing_status')
        batch_op.drop_column('sms_notification_30_days')
        batch_op.drop_column('sms_notification_10_days')
        batch_op.drop_column('sms_notification_completed')
        batch_op.drop_column('written_off_by_id')
        batch_op.drop_column('written_off_timestamp')
        batch_op.drop_column('is_written_off')
        batch_op.drop_column('ticket_notes')
        batch_op.drop_column('complete_duration')
        batch_op.drop_column('owner_collect_timestamp')
        batch_op.drop_column('owner_collect')
        batch_op.drop_column('problem_areas')
        batch_op.drop_column('device_not_working')
        batch_op.drop_column('device_condition_notes')
        batch_op.drop_column('device_condition_grade')
        batch_op.drop_column('service_section')
        batch_op.drop_column('customer_pib')
        batch_op.drop_column('customer_company_name')