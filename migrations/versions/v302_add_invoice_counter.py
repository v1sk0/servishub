"""Add invoice_counter table for race-safe invoice numbering

Revision ID: v302_invoice_counter
Revises: z7a8b9c0d1e2
Create Date: 2026-01-24

This migration adds an invoice_counter table that tracks the last used
invoice sequence number per year. Uses SELECT FOR UPDATE for atomic
increment to prevent race conditions.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = 'v302_invoice_counter'
down_revision = 'z7a8b9c0d1e2'  # Latest: add_tenant_connection_tables
branch_labels = None
depends_on = None


def upgrade():
    # Create invoice_counter table
    op.create_table(
        'invoice_counter',
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('last_seq', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('year')
    )

    # Initialize with MAX(seq) from existing invoices (not COUNT!)
    # This handles gaps in numbering (e.g., invoices 1, 2, 5 -> last_seq = 5)
    conn = op.get_bind()

    # Get current year
    from datetime import datetime
    current_year = datetime.utcnow().year

    # Find MAX sequence number by parsing invoice_number (format: SH-YYYY-NNNNNN)
    # Using SUBSTRING to extract the sequence part and cast to integer
    result = conn.execute(text("""
        SELECT COALESCE(MAX(
            CAST(SUBSTRING(invoice_number FROM 'SH-[0-9]{4}-([0-9]+)$') AS INTEGER)
        ), 0) as max_seq
        FROM subscription_payment
        WHERE invoice_number LIKE :pattern
    """), {'pattern': f'SH-{current_year}-%'})
    max_seq = result.scalar() or 0

    # Insert initial row for current year
    conn.execute(text("""
        INSERT INTO invoice_counter (year, last_seq) VALUES (:year, :seq)
    """), {'year': current_year, 'seq': max_seq})
    print(f"[MIGRATION] Initialized invoice_counter for {current_year} with last_seq={max_seq}")


def downgrade():
    op.drop_table('invoice_counter')