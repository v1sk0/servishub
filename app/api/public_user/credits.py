"""
Public User Credits - stanje, kupovina, istorija.

Reuse-uje credit_service.py logiku za public_user owner_type.
"""

from flask import Blueprint, request, g
from app.extensions import db
from app.models.credits import (
    CreditBalance, CreditTransaction,
    OwnerType, CreditTransactionType
)
from app.models.feature_flag import is_feature_enabled
from app.services.credit_service import (
    get_balance, get_or_create_balance,
    CREDIT_PACKAGES, EUR_TO_RSD
)
from .auth import public_jwt_required
from decimal import Decimal

bp = Blueprint('public_credits', __name__, url_prefix='/credits')


@bp.route('/', methods=['GET'])
@public_jwt_required
def get_credit_balance():
    """Stanje kredita."""
    if not is_feature_enabled('b2c_marketplace_enabled'):
        return {'error': 'B2C marketplace nije aktiviran'}, 403

    balance = get_balance(OwnerType.PUBLIC_USER, g.public_user_id)
    bal_obj = CreditBalance.query.filter_by(
        owner_type=OwnerType.PUBLIC_USER,
        public_user_id=g.public_user_id
    ).first()

    return {
        'balance': float(balance),
        'total_purchased': float(bal_obj.total_purchased) if bal_obj else 0,
        'total_spent': float(bal_obj.total_spent) if bal_obj else 0,
        'total_received_free': float(bal_obj.total_received_free) if bal_obj else 0,
    }, 200


@bp.route('/history', methods=['GET'])
@public_jwt_required
def get_history():
    """Istorija transakcija."""
    if not is_feature_enabled('b2c_marketplace_enabled'):
        return {'error': 'B2C marketplace nije aktiviran'}, 403

    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)

    balance = CreditBalance.query.filter_by(
        owner_type=OwnerType.PUBLIC_USER,
        public_user_id=g.public_user_id
    ).first()

    if not balance:
        return {'transactions': [], 'total': 0, 'page': page}, 200

    query = CreditTransaction.query.filter_by(
        credit_balance_id=balance.id
    ).order_by(CreditTransaction.created_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return {
        'transactions': [{
            'id': t.id,
            'type': t.transaction_type.value,
            'amount': float(t.amount),
            'balance_after': float(t.balance_after),
            'description': t.description,
            'created_at': t.created_at.isoformat(),
        } for t in pagination.items],
        'total': pagination.total,
        'page': page,
        'pages': pagination.pages,
    }, 200