"""Billing Enhancement v303 - PDF uplatnica, Bank Import, Reconciliation

Revision ID: v303_billing_enhancement
Revises: v302_invoice_counter
Create Date: 2026-01-24

This migration adds:
- bank_statement_import table: Track imported bank statements
- bank_transaction table: Individual transactions with matching status
- New columns on subscription_payment: IPS QR, reconciliation tracking
- ips_purpose_code on platform_settings
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = 'v303_billing_enhancement'
down_revision = 'v302_invoice_counter'
branch_labels = None
depends_on = None


def upgrade():
    # =========================================================================
    # 1. Nova tabela: bank_statement_import
    # =========================================================================
    op.create_table(
        'bank_statement_import',
        sa.Column('id', sa.BigInteger(), primary_key=True),

        # Fajl info
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('file_hash', sa.String(64), unique=True),
        sa.Column('file_size', sa.Integer()),

        # Banka i format
        sa.Column('bank_code', sa.String(20), nullable=False),
        sa.Column('bank_name', sa.String(100)),
        sa.Column('import_format', sa.String(20)),
        sa.Column('encoding', sa.String(20)),

        # Datum izvoda
        sa.Column('statement_date', sa.Date(), nullable=False),
        sa.Column('statement_number', sa.String(50)),

        # Processing stats
        sa.Column('total_transactions', sa.Integer(), server_default='0'),
        sa.Column('credit_transactions', sa.Integer(), server_default='0'),
        sa.Column('debit_transactions', sa.Integer(), server_default='0'),
        sa.Column('matched_count', sa.Integer(), server_default='0'),
        sa.Column('unmatched_count', sa.Integer(), server_default='0'),
        sa.Column('manual_match_count', sa.Integer(), server_default='0'),

        # Totali
        sa.Column('total_credit_amount', sa.Numeric(14, 2)),
        sa.Column('total_debit_amount', sa.Numeric(14, 2)),

        # Status
        sa.Column('status', sa.String(20), server_default='PENDING'),
        sa.Column('error_message', sa.Text()),
        sa.Column('warnings', postgresql.JSON(astext_type=sa.Text()), server_default='[]'),

        # Ko i kad
        sa.Column('imported_by_id', sa.Integer(), sa.ForeignKey('platform_admin.id')),
        sa.Column('imported_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('processed_at', sa.DateTime()),
    )

    op.create_index('ix_bank_import_date', 'bank_statement_import', ['statement_date'])
    op.create_index('ix_bank_import_status', 'bank_statement_import', ['status'])

    # =========================================================================
    # 2. Nova tabela: bank_transaction
    # =========================================================================
    op.create_table(
        'bank_transaction',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('import_id', sa.BigInteger(), sa.ForeignKey('bank_statement_import.id'), nullable=False),

        # IDEMPOTENCY - sprečava duplikate
        sa.Column('transaction_hash', sa.String(64), unique=True, nullable=False),

        # Tip transakcije
        sa.Column('transaction_type', sa.String(10), server_default='CREDIT'),

        # Datumi
        sa.Column('transaction_date', sa.Date(), nullable=False),
        sa.Column('value_date', sa.Date()),
        sa.Column('booking_date', sa.Date()),

        # Iznos
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('currency', sa.String(3), server_default='RSD'),

        # Platilac info
        sa.Column('payer_name', sa.String(200)),
        sa.Column('payer_account', sa.String(50)),
        sa.Column('payer_address', sa.String(200)),

        # Poziv na broj
        sa.Column('payment_reference', sa.String(50)),
        sa.Column('payment_reference_model', sa.String(5)),
        sa.Column('payment_reference_raw', sa.String(100)),

        # Svrha uplate
        sa.Column('purpose', sa.String(500)),
        sa.Column('purpose_code', sa.String(10)),

        # Bank-specific ID
        sa.Column('bank_transaction_id', sa.String(100)),

        # Raw data
        sa.Column('raw_data', postgresql.JSON(astext_type=sa.Text())),

        # Matching rezultat
        sa.Column('match_status', sa.String(20), server_default='UNMATCHED'),
        sa.Column('matched_payment_id', sa.BigInteger(), sa.ForeignKey('subscription_payment.id')),
        sa.Column('match_confidence', sa.Numeric(4, 2)),
        sa.Column('match_method', sa.String(50)),
        sa.Column('match_notes', sa.Text()),

        # Ko je upairo
        sa.Column('matched_by_id', sa.Integer(), sa.ForeignKey('platform_admin.id')),
        sa.Column('matched_at', sa.DateTime()),

        # Ignore info
        sa.Column('ignored_by_id', sa.Integer(), sa.ForeignKey('platform_admin.id')),
        sa.Column('ignored_at', sa.DateTime()),
        sa.Column('ignore_reason', sa.String(200)),

        # Timestamps
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    op.create_index('ix_bank_txn_reference', 'bank_transaction', ['payment_reference'])
    op.create_index('ix_bank_txn_match_status', 'bank_transaction', ['match_status'])
    op.create_index('ix_bank_txn_date_amount', 'bank_transaction', ['transaction_date', 'amount'])
    op.create_index('ix_bank_txn_import_status', 'bank_transaction', ['import_id', 'match_status'])

    # =========================================================================
    # 3. Izmene u subscription_payment
    # =========================================================================

    # Invoice delivery tracking
    op.add_column('subscription_payment',
        sa.Column('invoice_sent_at', sa.DateTime()))
    op.add_column('subscription_payment',
        sa.Column('invoice_sent_to', sa.String(200)))

    # Uplatnica PDF URL
    op.add_column('subscription_payment',
        sa.Column('uplatnica_pdf_url', sa.String(500)))

    # IPS QR data
    op.add_column('subscription_payment',
        sa.Column('ips_qr_string', sa.Text()))
    op.add_column('subscription_payment',
        sa.Column('ips_qr_generated_at', sa.DateTime()))

    # Poziv na broj model (payment_reference already exists)
    op.add_column('subscription_payment',
        sa.Column('payment_reference_model', sa.String(5), server_default='97'))

    # Bank reconciliation
    op.add_column('subscription_payment',
        sa.Column('reconciled_at', sa.DateTime()))
    op.add_column('subscription_payment',
        sa.Column('reconciled_via', sa.String(50)))
    op.add_column('subscription_payment',
        sa.Column('bank_transaction_id', sa.BigInteger(),
                  sa.ForeignKey('bank_transaction.id')))

    op.create_index('ix_payment_sent', 'subscription_payment', ['invoice_sent_at'])

    # =========================================================================
    # 4. Izmene u platform_settings
    # =========================================================================
    # Dodaj SAMO IPS-specifično polje (bank info već postoji)
    op.add_column('platform_settings',
        sa.Column('ips_purpose_code', sa.String(4), server_default='221'))

    # =========================================================================
    # 5. Migracija postojećih faktura - generiši payment_reference
    # =========================================================================
    conn = op.get_bind()

    # Za svaku postojeću fakturu bez payment_reference, generiši ga
    conn.execute(text("""
        UPDATE subscription_payment
        SET payment_reference = '97' || LPAD(tenant_id::text, 6, '0') ||
            LPAD(COALESCE(
                CAST(SUBSTRING(invoice_number FROM 'SH-[0-9]{4}-([0-9]+)$') AS INTEGER),
                id
            )::text, 5, '0'),
            payment_reference_model = '97'
        WHERE payment_reference IS NULL
          AND invoice_number IS NOT NULL
    """))

    print("[MIGRATION v303] Updated existing payments with payment_reference")


def downgrade():
    # Ukloni indekse
    op.drop_index('ix_payment_sent', 'subscription_payment')
    op.drop_index('ix_bank_txn_import_status', 'bank_transaction')
    op.drop_index('ix_bank_txn_date_amount', 'bank_transaction')
    op.drop_index('ix_bank_txn_match_status', 'bank_transaction')
    op.drop_index('ix_bank_txn_reference', 'bank_transaction')
    op.drop_index('ix_bank_import_status', 'bank_statement_import')
    op.drop_index('ix_bank_import_date', 'bank_statement_import')

    # Ukloni kolonu iz platform_settings
    op.drop_column('platform_settings', 'ips_purpose_code')

    # Ukloni kolone iz subscription_payment
    op.drop_column('subscription_payment', 'bank_transaction_id')
    op.drop_column('subscription_payment', 'reconciled_via')
    op.drop_column('subscription_payment', 'reconciled_at')
    op.drop_column('subscription_payment', 'payment_reference_model')
    op.drop_column('subscription_payment', 'ips_qr_generated_at')
    op.drop_column('subscription_payment', 'ips_qr_string')
    op.drop_column('subscription_payment', 'uplatnica_pdf_url')
    op.drop_column('subscription_payment', 'invoice_sent_to')
    op.drop_column('subscription_payment', 'invoice_sent_at')

    # Ukloni tabele (redosled je bitan zbog FK)
    op.drop_table('bank_transaction')
    op.drop_table('bank_statement_import')