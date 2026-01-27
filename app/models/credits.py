"""
Credit System modeli - kreditni sistem platforme.

CreditBalance - stanje kredita (polimorfno: tenant/supplier/public_user)
CreditTransaction - log svake transakcije (IMMUTABLE)
CreditPurchase - kupovina paketa kredita
PromoCode - promo kodovi za popuste

Princip: 1 kredit = 1 EUR (~117.5 RSD)
"""

import enum
from datetime import datetime
from ..extensions import db


class OwnerType(enum.Enum):
    """Tip vlasnika kredita."""
    TENANT = 'tenant'
    SUPPLIER = 'supplier'
    PUBLIC_USER = 'public_user'


class CreditTransactionType(enum.Enum):
    """Tip kreditne transakcije."""
    PURCHASE = 'PURCHASE'
    WELCOME = 'WELCOME'
    PROMO = 'PROMO'
    CONNECTION_FEE = 'CONNECTION_FEE'
    FEATURED = 'FEATURED'
    PREMIUM = 'PREMIUM'
    BOOST = 'BOOST'
    REFUND = 'REFUND'
    CHARGEBACK = 'CHARGEBACK'
    ADMIN = 'ADMIN'


class DiscountType(enum.Enum):
    """Tip popusta za promo kod."""
    PERCENT = 'percent'
    FIXED_CREDITS = 'fixed_credits'
    FIXED_EUR = 'fixed_eur'


class CreditPaymentStatus(enum.Enum):
    """Status plaćanja za kupovinu kredita."""
    PENDING = 'pending'
    COMPLETED = 'completed'
    FAILED = 'failed'
    REFUNDED = 'refunded'


class CreditBalance(db.Model):
    """
    Stanje kredita - polimorfno po owner_type.

    Svaki tenant/supplier/public_user ima tačno jedan CreditBalance zapis.
    Balance ne može biti negativan (CHECK constraint).
    """
    __tablename__ = 'credit_balance'

    id = db.Column(db.Integer, primary_key=True)

    # Polimorfni vlasnik
    owner_type = db.Column(db.Enum(OwnerType), nullable=False, index=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=True,
        index=True
    )
    supplier_id = db.Column(
        db.Integer,
        db.ForeignKey('supplier.id', ondelete='CASCADE'),
        nullable=True,
        index=True
    )
    public_user_id = db.Column(
        db.BigInteger,
        db.ForeignKey('public_user.id', ondelete='CASCADE'),
        nullable=True,
        index=True
    )

    # Stanje
    balance = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    total_purchased = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    total_spent = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    total_received_free = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    # Low balance alert
    low_balance_threshold = db.Column(db.Numeric(10, 2), default=5)
    low_balance_alert_sent = db.Column(db.Boolean, default=False)

    # Timestampovi
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Relacije
    transactions = db.relationship(
        'CreditTransaction',
        backref='credit_balance',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    purchases = db.relationship(
        'CreditPurchase',
        backref='credit_balance',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )

    __table_args__ = (
        db.CheckConstraint('balance >= 0', name='check_balance_non_negative'),
        db.UniqueConstraint('owner_type', 'tenant_id', name='uq_credit_balance_tenant'),
        db.UniqueConstraint('owner_type', 'supplier_id', name='uq_credit_balance_supplier'),
        db.UniqueConstraint('owner_type', 'public_user_id', name='uq_credit_balance_public_user'),
    )

    def __repr__(self):
        return f'<CreditBalance {self.id}: {self.owner_type.value} balance={self.balance}>'


class CreditTransaction(db.Model):
    """
    Log kreditne transakcije - IMMUTABLE.

    Svaka promena balance-a mora imati odgovarajući CreditTransaction zapis.
    Nikada se ne menja ili briše.
    """
    __tablename__ = 'credit_transaction'

    id = db.Column(db.BigInteger, primary_key=True)

    credit_balance_id = db.Column(
        db.Integer,
        db.ForeignKey('credit_balance.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    transaction_type = db.Column(db.Enum(CreditTransactionType), nullable=False, index=True)

    # Iznos: pozitivan = dodavanje kredita, negativan = oduzimanje
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    balance_before = db.Column(db.Numeric(10, 2), nullable=False)
    balance_after = db.Column(db.Numeric(10, 2), nullable=False)

    # Opis i referenca
    description = db.Column(db.String(500))
    reference_type = db.Column(db.String(50))  # npr. 'credit_purchase', 'connection', 'boost'
    reference_id = db.Column(db.Integer)

    # Idempotency - sprečava duplo knjiženje (nullable - ne zahteva svaka transakcija)
    idempotency_key = db.Column(db.String(255), nullable=True)

    # Timestamp
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        db.UniqueConstraint('idempotency_key', name='uq_transaction_idempotency'),
    )

    def __repr__(self):
        return f'<CreditTransaction {self.id}: {self.transaction_type.value} {self.amount}>'


class CreditPurchase(db.Model):
    """
    Kupovina paketa kredita.

    Prati svaku kupovinu: paket, cena, popust, status plaćanja.
    """
    __tablename__ = 'credit_purchase'

    id = db.Column(db.Integer, primary_key=True)

    credit_balance_id = db.Column(
        db.Integer,
        db.ForeignKey('credit_balance.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Paket
    package_code = db.Column(db.String(50), nullable=False)  # npr. 'starter_10', 'pro_50'
    credits_amount = db.Column(db.Numeric(10, 2), nullable=False)

    # Cena
    price_eur = db.Column(db.Numeric(10, 2), nullable=False)
    price_rsd = db.Column(db.Numeric(10, 2))
    discount_percent = db.Column(db.Numeric(5, 2), default=0)

    # Promo kod
    promo_code_id = db.Column(
        db.Integer,
        db.ForeignKey('promo_code.id', ondelete='SET NULL'),
        nullable=True
    )
    promo_discount = db.Column(db.Numeric(10, 2), default=0)

    # Plaćanje
    payment_method = db.Column(db.String(50))  # 'card', 'bank_transfer', 'admin'
    payment_status = db.Column(
        db.Enum(CreditPaymentStatus),
        default=CreditPaymentStatus.PENDING,
        nullable=False,
        index=True
    )
    payment_reference = db.Column(db.String(255))

    # Idempotency
    idempotency_key = db.Column(db.String(255), nullable=True)

    # Timestampovi
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    completed_at = db.Column(db.DateTime)

    __table_args__ = (
        db.UniqueConstraint('idempotency_key', name='uq_purchase_idempotency'),
    )

    def __repr__(self):
        return f'<CreditPurchase {self.id}: {self.package_code} {self.credits_amount} credits>'


class PromoCode(db.Model):
    """
    Promo kod za popust na kupovinu kredita.
    """
    __tablename__ = 'promo_code'

    id = db.Column(db.Integer, primary_key=True)

    # Kod
    code = db.Column(db.String(50), unique=True, nullable=False, index=True)

    # Popust
    discount_type = db.Column(db.Enum(DiscountType), nullable=False)
    discount_value = db.Column(db.Numeric(10, 2), nullable=False)
    min_purchase_eur = db.Column(db.Numeric(10, 2), default=0)

    # Ograničenja
    max_uses_total = db.Column(db.Integer)  # NULL = neograničeno
    max_uses_per_user = db.Column(db.Integer, default=1)

    # Za koga važi (JSON lista: ['tenant', 'supplier', 'public_user'])
    valid_for = db.Column(db.JSON, default=lambda: ['tenant', 'supplier', 'public_user'])

    # Vremenski okvir
    valid_from = db.Column(db.DateTime)
    valid_until = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # Statistika
    times_used = db.Column(db.Integer, default=0, nullable=False)
    total_discount_given = db.Column(db.Numeric(10, 2), default=0, nullable=False)

    # Timestampovi
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relacija
    purchases = db.relationship(
        'CreditPurchase',
        backref='promo_code',
        lazy='dynamic'
    )

    def __repr__(self):
        return f'<PromoCode {self.code}: {self.discount_type.value} {self.discount_value}>'