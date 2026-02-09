"""
Supplier Credits API - credit balance and transaction history.

Endpoints:
    GET  /credits/          - stanje kredita dobavljaca
    GET  /credits/history   - istorija transakcija (paginirano)
"""

from flask import Blueprint, request, g
from app.extensions import db
from .auth import supplier_jwt_required
from app.models.credits import (
    CreditBalance, CreditTransaction,
    OwnerType, CreditTransactionType
)
from app.services.credit_service import get_balance

bp = Blueprint('supplier_credits', __name__, url_prefix='/credits')


@bp.route('/', methods=['GET'])
@supplier_jwt_required
def get_credit_balance():
    """Vraca stanje kredita za trenutnog dobavljaca."""
    balance = get_balance(OwnerType.SUPPLIER, g.supplier_id)
    bal_obj = CreditBalance.query.filter_by(
        owner_type=OwnerType.SUPPLIER,
        supplier_id=g.supplier_id
    ).first()

    return {
        'balance': float(balance),
        'total_purchased': float(bal_obj.total_purchased) if bal_obj else 0,
        'total_spent': float(bal_obj.total_spent) if bal_obj else 0,
        'total_received_free': float(bal_obj.total_received_free) if bal_obj else 0,
    }, 200


@bp.route('/history', methods=['GET'])
@supplier_jwt_required
def get_transaction_history():
    """
    Istorija transakcija (paginirano).

    Query params:
        page: int (default 1)
        per_page: int (default 20, max 100)
        type: str (opciono) - filter po transaction_type
    """
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)
    txn_type = request.args.get('type')

    balance = CreditBalance.query.filter_by(
        owner_type=OwnerType.SUPPLIER,
        supplier_id=g.supplier_id
    ).first()

    if not balance:
        return {'transactions': [], 'total': 0, 'page': page, 'per_page': per_page}, 200

    query = CreditTransaction.query.filter_by(
        credit_balance_id=balance.id
    )
    if txn_type:
        try:
            query = query.filter_by(transaction_type=CreditTransactionType(txn_type))
        except ValueError:
            pass

    query = query.order_by(CreditTransaction.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    transactions = [{
        'id': t.id,
        'type': t.transaction_type.value,
        'amount': float(t.amount),
        'balance_before': float(t.balance_before),
        'balance_after': float(t.balance_after),
        'description': t.description,
        'reference_type': t.reference_type,
        'reference_id': t.reference_id,
        'created_at': t.created_at.isoformat(),
    } for t in pagination.items]

    return {
        'transactions': transactions,
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
        'pages': pagination.pages,
    }, 200
