"""
Admin Credits API - platform-wide credit audit and management.

Endpoints:
    GET  /credits/overview                          - ukupna statistika platforme
    GET  /credits/transactions                      - sve transakcije (filterable)
    GET  /credits/balance/<owner_type>/<owner_id>   - stanje + historija za vlasnika
    POST /credits/adjust                            - admin manual adjustment
"""

from decimal import Decimal
from datetime import datetime
from flask import Blueprint, request
from app.extensions import db
from app.api.middleware.auth import platform_admin_required
from app.models.credits import (
    CreditBalance, CreditTransaction,
    OwnerType, CreditTransactionType
)
from app.services.credit_service import add_credits, deduct_credits

bp = Blueprint('admin_credits', __name__, url_prefix='/credits')


@bp.route('/overview', methods=['GET'])
@platform_admin_required
def get_overview():
    """Ukupna statistika kreditnog sistema."""
    balances = CreditBalance.query.all()

    total_balance = sum(float(b.balance) for b in balances)
    total_purchased = sum(float(b.total_purchased) for b in balances)
    total_spent = sum(float(b.total_spent) for b in balances)
    total_free = sum(float(b.total_received_free) for b in balances)

    by_type = {}
    for b in balances:
        key = b.owner_type.value
        if key not in by_type:
            by_type[key] = {'count': 0, 'total_balance': 0, 'total_spent': 0}
        by_type[key]['count'] += 1
        by_type[key]['total_balance'] += float(b.balance)
        by_type[key]['total_spent'] += float(b.total_spent)

    return {
        'total_active_balances': len(balances),
        'total_credits_in_system': total_balance,
        'total_credits_purchased': total_purchased,
        'total_credits_spent': total_spent,
        'total_credits_free': total_free,
        'by_owner_type': by_type,
    }, 200


@bp.route('/transactions', methods=['GET'])
@platform_admin_required
def get_transactions():
    """
    Sve transakcije (paginirano, filterable).

    Query params:
        page, per_page, owner_type (TENANT/SUPPLIER/PUBLIC_USER),
        owner_id, type (transaction_type), start_date, end_date
    """
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 200)
    owner_type_str = request.args.get('owner_type')
    owner_id = request.args.get('owner_id', type=int)
    txn_type = request.args.get('type')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    query = CreditTransaction.query.join(CreditBalance)

    if owner_type_str:
        try:
            ot = OwnerType(owner_type_str)
            query = query.filter(CreditBalance.owner_type == ot)
        except ValueError:
            pass

    if owner_id:
        query = query.filter(
            db.or_(
                CreditBalance.tenant_id == owner_id,
                CreditBalance.supplier_id == owner_id,
                CreditBalance.public_user_id == owner_id,
            )
        )

    if txn_type:
        try:
            query = query.filter(CreditTransaction.transaction_type == CreditTransactionType(txn_type))
        except ValueError:
            pass

    if start_date:
        try:
            dt = datetime.fromisoformat(start_date)
            query = query.filter(CreditTransaction.created_at >= dt)
        except ValueError:
            pass

    if end_date:
        try:
            dt = datetime.fromisoformat(end_date)
            query = query.filter(CreditTransaction.created_at <= dt)
        except ValueError:
            pass

    query = query.order_by(CreditTransaction.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    transactions = []
    for t in pagination.items:
        bal = t.credit_balance
        transactions.append({
            'id': t.id,
            'owner_type': bal.owner_type.value if bal else None,
            'owner_id': bal.tenant_id or bal.supplier_id or bal.public_user_id if bal else None,
            'type': t.transaction_type.value,
            'amount': float(t.amount),
            'balance_before': float(t.balance_before),
            'balance_after': float(t.balance_after),
            'description': t.description,
            'reference_type': t.reference_type,
            'reference_id': t.reference_id,
            'created_at': t.created_at.isoformat(),
        })

    return {
        'transactions': transactions,
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
        'pages': pagination.pages,
    }, 200


@bp.route('/balance/<owner_type>/<int:owner_id>', methods=['GET'])
@platform_admin_required
def get_owner_balance(owner_type, owner_id):
    """Stanje + historija za specificnog vlasnika."""
    try:
        ot = OwnerType(owner_type)
    except ValueError:
        return {'error': f'Nepoznat owner_type: {owner_type}. Dozvoljeni: TENANT, SUPPLIER, PUBLIC_USER'}, 400

    filters = {'owner_type': ot}
    if ot == OwnerType.TENANT:
        filters['tenant_id'] = owner_id
    elif ot == OwnerType.SUPPLIER:
        filters['supplier_id'] = owner_id
    elif ot == OwnerType.PUBLIC_USER:
        filters['public_user_id'] = owner_id

    balance = CreditBalance.query.filter_by(**filters).first()

    if not balance:
        return {
            'balance': 0,
            'total_purchased': 0,
            'total_spent': 0,
            'total_received_free': 0,
            'recent_transactions': [],
        }, 200

    # Poslednjih 20 transakcija
    recent = CreditTransaction.query.filter_by(
        credit_balance_id=balance.id
    ).order_by(CreditTransaction.created_at.desc()).limit(20).all()

    return {
        'balance': float(balance.balance),
        'total_purchased': float(balance.total_purchased),
        'total_spent': float(balance.total_spent),
        'total_received_free': float(balance.total_received_free),
        'recent_transactions': [{
            'id': t.id,
            'type': t.transaction_type.value,
            'amount': float(t.amount),
            'balance_before': float(t.balance_before),
            'balance_after': float(t.balance_after),
            'description': t.description,
            'created_at': t.created_at.isoformat(),
        } for t in recent],
    }, 200


@bp.route('/adjust', methods=['POST'])
@platform_admin_required
def adjust_credits():
    """
    Admin manual credit adjustment.

    Body:
        owner_type: str (TENANT/SUPPLIER/PUBLIC_USER)
        owner_id: int
        amount: float (pozitivan za dodavanje, negativan za oduzimanje)
        reason: str (obavezan, min 5 chars)
    """
    data = request.get_json() or {}

    owner_type_str = data.get('owner_type')
    owner_id = data.get('owner_id')
    amount = data.get('amount')
    reason = data.get('reason', '').strip()

    if not owner_type_str or not owner_id or amount is None:
        return {'error': 'owner_type, owner_id i amount su obavezni'}, 400

    if not reason or len(reason) < 5:
        return {'error': 'Razlog (reason) je obavezan (min 5 karaktera)'}, 400

    try:
        ot = OwnerType(owner_type_str)
    except ValueError:
        return {'error': f'Nepoznat owner_type: {owner_type_str}'}, 400

    amount_val = Decimal(str(amount))

    if amount_val == 0:
        return {'error': 'Iznos ne moze biti 0'}, 400

    description = f'Admin adjustment: {reason}'

    if amount_val > 0:
        txn = add_credits(
            owner_type=ot,
            owner_id=owner_id,
            amount=amount_val,
            transaction_type=CreditTransactionType.ADMIN,
            description=description,
            ref_type='admin_adjust',
        )
    else:
        txn = deduct_credits(
            owner_type=ot,
            owner_id=owner_id,
            amount=abs(amount_val),
            transaction_type=CreditTransactionType.ADMIN,
            description=description,
            ref_type='admin_adjust',
        )
        if txn is False:
            return {'error': 'Nedovoljno kredita za oduzimanje'}, 400

    db.session.commit()

    return {
        'success': True,
        'transaction_id': txn.id,
        'amount': float(amount_val),
        'new_balance': float(txn.balance_after),
        'message': f'Krediti {"dodati" if amount_val > 0 else "oduzeti"}: {abs(amount_val)}'
    }, 200
