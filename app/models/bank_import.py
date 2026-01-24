"""
Bank Import Models - Modeli za uvoz bankovnih izvoda i transakcija.

Koristi se za:
- Import izvoda (CSV, XML) iz banaka
- Automatsko uparivanje uplata sa fakturama
- Reconciliation i audit trail
"""
from datetime import datetime
from ..extensions import db


class ImportStatus:
    """Status uvoza izvoda."""
    PENDING = 'PENDING'
    PROCESSING = 'PROCESSING'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'
    PARTIAL = 'PARTIAL'  # Neke transakcije nisu uspele


class BankCode:
    """Kodovi podržanih banaka."""
    RAIFFEISEN = 'RAIF'
    ERSTE = 'ERST'
    AIK = 'AIK'
    NLB = 'NLB'
    INTESA = 'INT'
    ALTA = 'ALTA'
    UNKNOWN = 'UNK'


class MatchStatus:
    """Status uparivanja transakcije."""
    UNMATCHED = 'UNMATCHED'   # Nije pronađena faktura
    MATCHED = 'MATCHED'       # Auto-matched
    MANUAL = 'MANUAL'         # Ručno upareno
    IGNORED = 'IGNORED'       # Označeno da se ignoriše
    PARTIAL = 'PARTIAL'       # Delimično match (različit iznos)
    DUPLICATE = 'DUPLICATE'   # Duplikat već uparene transakcije


class TransactionType:
    """Tip transakcije."""
    CREDIT = 'CREDIT'  # Uplata NA naš račun
    DEBIT = 'DEBIT'    # Isplata SA našeg računa


class BankStatementImport(db.Model):
    """Import bankovnog izvoda - jedan fajl = jedan import."""
    __tablename__ = 'bank_statement_import'

    id = db.Column(db.BigInteger, primary_key=True)

    # Fajl info
    filename = db.Column(db.String(255), nullable=False)
    file_hash = db.Column(db.String(64), unique=True)  # SHA-256 za deduplication
    file_size = db.Column(db.Integer)

    # Banka i format
    bank_code = db.Column(db.String(20), nullable=False)
    bank_name = db.Column(db.String(100))
    import_format = db.Column(db.String(20))  # CSV, XML, MT940
    encoding = db.Column(db.String(20))  # UTF-8, CP1250, etc.

    # Datum izvoda
    statement_date = db.Column(db.Date, nullable=False)
    statement_number = db.Column(db.String(50))

    # Processing stats
    total_transactions = db.Column(db.Integer, default=0)
    credit_transactions = db.Column(db.Integer, default=0)
    debit_transactions = db.Column(db.Integer, default=0)
    matched_count = db.Column(db.Integer, default=0)
    unmatched_count = db.Column(db.Integer, default=0)
    manual_match_count = db.Column(db.Integer, default=0)

    # Totali
    total_credit_amount = db.Column(db.Numeric(14, 2))
    total_debit_amount = db.Column(db.Numeric(14, 2))

    # Status
    status = db.Column(db.String(20), default=ImportStatus.PENDING)
    error_message = db.Column(db.Text)
    warnings = db.Column(db.JSON, default=list)

    # Ko i kad
    imported_by_id = db.Column(db.Integer, db.ForeignKey('platform_admin.id'))
    imported_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)

    # Relationships
    transactions = db.relationship('BankTransaction', backref='import_batch', lazy='dynamic')
    imported_by = db.relationship('PlatformAdmin', foreign_keys=[imported_by_id])

    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'bank_code': self.bank_code,
            'bank_name': self.bank_name,
            'statement_date': self.statement_date.isoformat() if self.statement_date else None,
            'status': self.status,
            'stats': {
                'total': self.total_transactions,
                'credits': self.credit_transactions,
                'matched': self.matched_count,
                'unmatched': self.unmatched_count,
                'manual': self.manual_match_count,
            },
            'totals': {
                'credit': float(self.total_credit_amount or 0),
                'debit': float(self.total_debit_amount or 0),
            },
            'imported_at': self.imported_at.isoformat() if self.imported_at else None,
            'imported_by': self.imported_by.name if self.imported_by else None,
        }


class BankTransaction(db.Model):
    """Pojedinačna transakcija iz bankovnog izvoda."""
    __tablename__ = 'bank_transaction'

    id = db.Column(db.BigInteger, primary_key=True)
    import_id = db.Column(db.BigInteger, db.ForeignKey('bank_statement_import.id'), nullable=False)

    # IDEMPOTENCY - sprečava duplikate pri reimportu
    # SHA-256 hash od: date + amount + payer_account + reference
    transaction_hash = db.Column(db.String(64), unique=True, nullable=False)

    # Tip transakcije
    transaction_type = db.Column(db.String(10), default=TransactionType.CREDIT)

    # Datumi
    transaction_date = db.Column(db.Date, nullable=False)
    value_date = db.Column(db.Date)
    booking_date = db.Column(db.Date)

    # Iznos
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(3), default='RSD')

    # Platilac info
    payer_name = db.Column(db.String(200))
    payer_account = db.Column(db.String(50))
    payer_address = db.Column(db.String(200))

    # Poziv na broj - KLJUČNO za matching
    payment_reference = db.Column(db.String(50), index=True)
    payment_reference_model = db.Column(db.String(5))  # 97, 00, etc.
    payment_reference_raw = db.Column(db.String(100))  # Originalni tekst

    # Svrha uplate
    purpose = db.Column(db.String(500))
    purpose_code = db.Column(db.String(10))

    # Bank-specific ID
    bank_transaction_id = db.Column(db.String(100))

    # Raw data za debugging
    raw_data = db.Column(db.JSON)

    # Matching rezultat
    match_status = db.Column(db.String(20), default=MatchStatus.UNMATCHED, index=True)
    matched_payment_id = db.Column(db.BigInteger, db.ForeignKey('subscription_payment.id'))
    match_confidence = db.Column(db.Numeric(4, 2))
    match_method = db.Column(db.String(50))
    match_notes = db.Column(db.Text)

    # Ko je upairo (za manual match)
    matched_by_id = db.Column(db.Integer, db.ForeignKey('platform_admin.id'))
    matched_at = db.Column(db.DateTime)

    # Ignore info
    ignored_by_id = db.Column(db.Integer, db.ForeignKey('platform_admin.id'))
    ignored_at = db.Column(db.DateTime)
    ignore_reason = db.Column(db.String(200))

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    matched_payment = db.relationship('SubscriptionPayment', foreign_keys=[matched_payment_id])
    matched_by = db.relationship('PlatformAdmin', foreign_keys=[matched_by_id])

    # Indeksi
    __table_args__ = (
        db.Index('ix_bank_txn_date_amount', 'transaction_date', 'amount'),
        db.Index('ix_bank_txn_import_status', 'import_id', 'match_status'),
    )

    @staticmethod
    def generate_hash(date, amount, payer_account, reference) -> str:
        """Generiše idempotency hash za transakciju."""
        import hashlib
        data = f"{date}|{amount}|{payer_account or ''}|{reference or ''}"
        return hashlib.sha256(data.encode()).hexdigest()

    def to_dict(self):
        return {
            'id': self.id,
            'import_id': self.import_id,
            'type': self.transaction_type,
            'date': self.transaction_date.isoformat() if self.transaction_date else None,
            'amount': float(self.amount) if self.amount else 0,
            'currency': self.currency,
            'payer': {
                'name': self.payer_name,
                'account': self.payer_account,
            },
            'reference': {
                'model': self.payment_reference_model,
                'number': self.payment_reference,
                'raw': self.payment_reference_raw,
            },
            'purpose': self.purpose,
            'match': {
                'status': self.match_status,
                'payment_id': self.matched_payment_id,
                'confidence': float(self.match_confidence) if self.match_confidence else None,
                'method': self.match_method,
            }
        }