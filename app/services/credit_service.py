"""
Credit Service - biznis logika za kreditni sistem.

Sve operacije sa kreditima prolaze kroz ovaj servis:
- add_credits / deduct_credits / refund_credits
- promo code validacija
- welcome credits

Princip: 1 kredit = 1 EUR (~117.5 RSD)
"""

from decimal import Decimal
from datetime import datetime
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models.credits import (
    CreditBalance, CreditTransaction, CreditPurchase, PromoCode,
    OwnerType, CreditTransactionType, CreditPaymentStatus, DiscountType
)


# ============================================
# KONFIGURACIJA PAKETA
# ============================================

CREDIT_PACKAGES = {
    'starter':    {'credits': 20,  'price_eur': 20,  'discount': 0},
    'standard':   {'credits': 50,  'price_eur': 45,  'discount': 10},
    'pro':        {'credits': 100, 'price_eur': 80,  'discount': 20},
    'business':   {'credits': 250, 'price_eur': 175, 'discount': 30},
    'enterprise': {'credits': 500, 'price_eur': 300, 'discount': 40},
}

EUR_TO_RSD = Decimal('117.5')

WELCOME_CREDITS = {
    OwnerType.TENANT: Decimal('20'),
    OwnerType.SUPPLIER: Decimal('20'),
    OwnerType.PUBLIC_USER: Decimal('10'),
}


# ============================================
# CORE FUNKCIJE
# ============================================

def get_or_create_balance(owner_type, owner_id):
    """
    Dohvati ili kreiraj CreditBalance za vlasnika.

    Args:
        owner_type: OwnerType enum
        owner_id: ID vlasnika (tenant_id, supplier_id, ili public_user_id)

    Returns:
        CreditBalance instanca
    """
    # Mapiraj owner_type na odgovarajući FK
    filters = {'owner_type': owner_type}
    if owner_type == OwnerType.TENANT:
        filters['tenant_id'] = owner_id
    elif owner_type == OwnerType.SUPPLIER:
        filters['supplier_id'] = owner_id
    elif owner_type == OwnerType.PUBLIC_USER:
        filters['public_user_id'] = owner_id

    balance = CreditBalance.query.filter_by(**filters).first()
    if balance:
        return balance

    balance = CreditBalance(**filters)
    db.session.add(balance)
    db.session.flush()
    return balance


def add_credits(owner_type, owner_id, amount, transaction_type,
                description=None, ref_type=None, ref_id=None,
                promo_code_id=None, idempotency_key=None):
    """
    Dodaj kredite na balance.

    Args:
        owner_type: OwnerType enum
        owner_id: ID vlasnika
        amount: Decimal iznos (pozitivan)
        transaction_type: CreditTransactionType enum
        description: Opis transakcije
        ref_type: Tip reference (npr. 'credit_purchase')
        ref_id: ID reference
        promo_code_id: ID promo koda (opciono)
        idempotency_key: Ključ za sprečavanje duplih transakcija

    Returns:
        CreditTransaction instanca
    """
    amount = Decimal(str(amount))
    if amount <= 0:
        raise ValueError("Amount must be positive for add_credits")

    # Idempotency check
    if idempotency_key:
        existing = CreditTransaction.query.filter_by(
            idempotency_key=idempotency_key
        ).first()
        if existing:
            return existing

    balance = get_or_create_balance(owner_type, owner_id)
    balance_before = balance.balance

    balance.balance = balance.balance + amount
    if transaction_type == CreditTransactionType.PURCHASE:
        balance.total_purchased = balance.total_purchased + amount
    elif transaction_type in (CreditTransactionType.WELCOME, CreditTransactionType.PROMO):
        balance.total_received_free = balance.total_received_free + amount

    # Reset low balance alert
    if balance.low_balance_threshold and balance.balance >= balance.low_balance_threshold:
        balance.low_balance_alert_sent = False

    txn = CreditTransaction(
        credit_balance_id=balance.id,
        transaction_type=transaction_type,
        amount=amount,
        balance_before=balance_before,
        balance_after=balance.balance,
        description=description,
        reference_type=ref_type,
        reference_id=ref_id,
        idempotency_key=idempotency_key,
    )
    db.session.add(txn)
    db.session.flush()
    return txn


def deduct_credits(owner_type, owner_id, amount, transaction_type,
                   description=None, ref_type=None, ref_id=None,
                   idempotency_key=None):
    """
    Oduzmi kredite sa balance-a.

    Args:
        amount: Decimal iznos (pozitivan - biće zapisan kao negativan u transakciji)

    Returns:
        CreditTransaction ako uspešno, False ako nema dovoljno kredita
    """
    amount = Decimal(str(amount))
    if amount <= 0:
        raise ValueError("Amount must be positive for deduct_credits")

    # Idempotency check
    if idempotency_key:
        existing = CreditTransaction.query.filter_by(
            idempotency_key=idempotency_key
        ).first()
        if existing:
            return existing

    balance = get_or_create_balance(owner_type, owner_id)

    # Provera pre pokušaja (ne oslanjamo se samo na DB constraint)
    if balance.balance < amount:
        return False

    balance_before = balance.balance
    balance.balance = balance.balance - amount
    balance.total_spent = balance.total_spent + amount

    txn = CreditTransaction(
        credit_balance_id=balance.id,
        transaction_type=transaction_type,
        amount=-amount,  # Negativan iznos za oduzimanje
        balance_before=balance_before,
        balance_after=balance.balance,
        description=description,
        reference_type=ref_type,
        reference_id=ref_id,
        idempotency_key=idempotency_key,
    )
    db.session.add(txn)
    db.session.flush()
    return txn


def refund_credits(owner_type, owner_id, original_transaction_id, reason=None):
    """
    Refundiraj prethodno oduzete kredite.

    Args:
        original_transaction_id: ID originalne transakcije (mora biti negativan amount)
        reason: Razlog refunda

    Returns:
        CreditTransaction (refund)

    Raises:
        ValueError: ako originalna transakcija ne postoji, nije oduzimanje, ili je već refundirana
    """
    original = CreditTransaction.query.get(original_transaction_id)
    if not original:
        raise ValueError(f"Transaction {original_transaction_id} not found")

    # Samo oduzimanja se mogu refundirati
    if original.amount >= 0:
        raise ValueError("Only deductions (negative amount) can be refunded")

    # Provera da nije već refundirano
    existing_refund = CreditTransaction.query.filter_by(
        reference_type='refund',
        reference_id=original_transaction_id,
        transaction_type=CreditTransactionType.REFUND
    ).first()
    if existing_refund:
        raise ValueError(f"Transaction {original_transaction_id} already refunded")

    refund_amount = abs(original.amount)
    return add_credits(
        owner_type=owner_type,
        owner_id=owner_id,
        amount=refund_amount,
        transaction_type=CreditTransactionType.REFUND,
        description=reason or f"Refund for transaction #{original_transaction_id}",
        ref_type='refund',
        ref_id=original_transaction_id,
        idempotency_key=f"refund_{original_transaction_id}",
    )


def get_balance(owner_type, owner_id):
    """
    Vraća trenutno stanje kredita kao Decimal.

    Returns:
        Decimal (0 ako balance ne postoji)
    """
    filters = {'owner_type': owner_type}
    if owner_type == OwnerType.TENANT:
        filters['tenant_id'] = owner_id
    elif owner_type == OwnerType.SUPPLIER:
        filters['supplier_id'] = owner_id
    elif owner_type == OwnerType.PUBLIC_USER:
        filters['public_user_id'] = owner_id

    balance = CreditBalance.query.filter_by(**filters).first()
    if not balance:
        return Decimal('0')
    return balance.balance


def validate_promo_code(code, owner_type, owner_id, package_code=None):
    """
    Validira promo kod za korisnika.

    Returns:
        dict sa {'valid': True, 'promo': PromoCode, 'discount': Decimal} ili
        dict sa {'valid': False, 'reason': str}
    """
    promo = PromoCode.query.filter_by(code=code.upper().strip()).first()
    if not promo:
        return {'valid': False, 'reason': 'Promo kod ne postoji'}

    if not promo.is_active:
        return {'valid': False, 'reason': 'Promo kod nije aktivan'}

    now = datetime.utcnow()
    if promo.valid_from and now < promo.valid_from:
        return {'valid': False, 'reason': 'Promo kod još nije validan'}
    if promo.valid_until and now > promo.valid_until:
        return {'valid': False, 'reason': 'Promo kod je istekao'}

    # Provera owner_type
    valid_for = promo.valid_for or ['tenant', 'supplier', 'public_user']
    if owner_type.value not in valid_for:
        return {'valid': False, 'reason': 'Promo kod nije validan za vaš tip naloga'}

    # Max uses total
    if promo.max_uses_total is not None and promo.times_used >= promo.max_uses_total:
        return {'valid': False, 'reason': 'Promo kod je iskorišćen maksimalan broj puta'}

    # Per-user limit
    if promo.max_uses_per_user:
        user_uses = CreditPurchase.query.filter_by(
            promo_code_id=promo.id
        ).join(CreditBalance).filter(
            CreditBalance.owner_type == owner_type,
            _owner_id_filter(owner_type, owner_id)
        ).count()
        if user_uses >= promo.max_uses_per_user:
            return {'valid': False, 'reason': 'Već ste iskoristili ovaj promo kod'}

    # Per-tenant lifetime: max 5 različitih promo kodova
    if owner_type == OwnerType.TENANT:
        distinct_promos = db.session.query(
            db.func.count(db.distinct(CreditPurchase.promo_code_id))
        ).join(CreditBalance).filter(
            CreditBalance.owner_type == OwnerType.TENANT,
            CreditBalance.tenant_id == owner_id,
            CreditPurchase.promo_code_id.isnot(None)
        ).scalar() or 0
        if distinct_promos >= 5:
            return {'valid': False, 'reason': 'Dostigli ste maksimalan broj promo kodova (5)'}

    # Izračunaj popust
    discount = _calculate_discount(promo, package_code)

    return {'valid': True, 'promo': promo, 'discount': discount}


def grant_welcome_credits(owner_type, owner_id):
    """
    Dodeli welcome kredite novom korisniku.

    Idempotentno - ako već postoji WELCOME transakcija, ne dodeljuje ponovo.

    Returns:
        CreditTransaction ili None (ako su već dodeljeni)
    """
    amount = WELCOME_CREDITS.get(owner_type)
    if not amount:
        return None

    idempotency_key = f"welcome_{owner_type.value}_{owner_id}"

    existing = CreditTransaction.query.filter_by(
        idempotency_key=idempotency_key
    ).first()
    if existing:
        return None

    return add_credits(
        owner_type=owner_type,
        owner_id=owner_id,
        amount=amount,
        transaction_type=CreditTransactionType.WELCOME,
        description=f"Welcome credits ({amount})",
        idempotency_key=idempotency_key,
    )


# ============================================
# HELPER FUNKCIJE
# ============================================

def _owner_id_filter(owner_type, owner_id):
    """Vraća SQLAlchemy filter za owner_id na CreditBalance."""
    if owner_type == OwnerType.TENANT:
        return CreditBalance.tenant_id == owner_id
    elif owner_type == OwnerType.SUPPLIER:
        return CreditBalance.supplier_id == owner_id
    elif owner_type == OwnerType.PUBLIC_USER:
        return CreditBalance.public_user_id == owner_id


def _calculate_discount(promo, package_code=None):
    """Izračunaj popust na osnovu promo koda i paketa."""
    package = CREDIT_PACKAGES.get(package_code) if package_code else None
    price_eur = Decimal(str(package['price_eur'])) if package else Decimal('0')

    if promo.discount_type == DiscountType.PERCENT:
        return (price_eur * promo.discount_value / Decimal('100')).quantize(Decimal('0.01'))
    elif promo.discount_type == DiscountType.FIXED_EUR:
        return min(promo.discount_value, price_eur)
    elif promo.discount_type == DiscountType.FIXED_CREDITS:
        return promo.discount_value  # Bonus krediti
    return Decimal('0')