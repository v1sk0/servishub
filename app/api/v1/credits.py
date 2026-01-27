"""
Credits API - kreditni sistem endpointi.

Endpoints:
    GET  /credits/              - stanje kredita
    GET  /credits/packages      - lista paketa sa cenama
    POST /credits/purchase      - kupovina kredita
    GET  /credits/history       - istorija transakcija (paginirano)
    POST /credits/validate-promo - validacija promo koda
    GET  /credits/export        - CSV export transakcija
"""

import csv
import io
from decimal import Decimal
from datetime import datetime
from flask import Blueprint, request, g, Response
from app.extensions import db
from app.api.middleware.auth import jwt_required
from app.models.credits import (
    CreditBalance, CreditTransaction, CreditPurchase,
    OwnerType, CreditTransactionType, CreditPaymentStatus
)
from app.models.feature_flag import is_feature_enabled
from app.services.credit_service import (
    get_or_create_balance, add_credits, deduct_credits,
    get_balance, validate_promo_code, grant_welcome_credits,
    CREDIT_PACKAGES, EUR_TO_RSD
)

bp = Blueprint('credits', __name__, url_prefix='/credits')


def _check_credits_enabled():
    """Proveri da li je kreditni sistem aktivan za tenanta."""
    if not is_feature_enabled('credits_enabled', g.tenant_id):
        return {'error': 'Kreditni sistem nije aktiviran'}, 403
    return None


@bp.route('/', methods=['GET'])
@jwt_required
def get_credit_balance():
    """Vraća stanje kredita za trenutnog tenanta."""
    check = _check_credits_enabled()
    if check:
        return check

    balance = get_balance(OwnerType.TENANT, g.tenant_id)
    bal_obj = CreditBalance.query.filter_by(
        owner_type=OwnerType.TENANT,
        tenant_id=g.tenant_id
    ).first()

    return {
        'balance': float(balance),
        'total_purchased': float(bal_obj.total_purchased) if bal_obj else 0,
        'total_spent': float(bal_obj.total_spent) if bal_obj else 0,
        'total_received_free': float(bal_obj.total_received_free) if bal_obj else 0,
        'low_balance_threshold': float(bal_obj.low_balance_threshold) if bal_obj and bal_obj.low_balance_threshold else 5,
    }, 200


@bp.route('/packages', methods=['GET'])
@jwt_required
def get_packages():
    """Vraća listu dostupnih paketa sa cenama u EUR i RSD."""
    check = _check_credits_enabled()
    if check:
        return check

    packages = []
    for code, pkg in CREDIT_PACKAGES.items():
        price_eur = Decimal(str(pkg['price_eur']))
        packages.append({
            'code': code,
            'credits': pkg['credits'],
            'price_eur': float(price_eur),
            'price_rsd': float(price_eur * EUR_TO_RSD),
            'discount_percent': pkg['discount'],
            'price_per_credit_eur': round(float(price_eur / Decimal(str(pkg['credits']))), 2),
        })

    return {'packages': packages}, 200


@bp.route('/purchase', methods=['POST'])
@jwt_required
def purchase_credits():
    """
    Kupovina paketa kredita.

    Body:
        package: str (obavezno) - kod paketa
        promo_code: str (opciono) - promo kod
        payment_method: str (obavezno) - 'card' | 'bank_transfer'
        idempotency_key: str (obavezno) - ključ za deduplikaciju
    """
    check = _check_credits_enabled()
    if check:
        return check

    data = request.get_json() or {}
    package_code = data.get('package')
    promo_code = data.get('promo_code')
    payment_method = data.get('payment_method')
    idempotency_key = data.get('idempotency_key')

    if not idempotency_key:
        return {'error': 'idempotency_key je obavezan'}, 400
    if not package_code or package_code not in CREDIT_PACKAGES:
        return {'error': f'Nepoznat paket: {package_code}'}, 400
    if not payment_method:
        return {'error': 'payment_method je obavezan'}, 400

    # Idempotency check na CreditPurchase nivou
    existing = CreditPurchase.query.filter_by(idempotency_key=idempotency_key).first()
    if existing:
        return {
            'purchase_id': existing.id,
            'status': existing.payment_status.value,
            'message': 'Kupovina već postoji (deduplicirano)'
        }, 200

    pkg = CREDIT_PACKAGES[package_code]
    price_eur = Decimal(str(pkg['price_eur']))
    credits_amount = Decimal(str(pkg['credits']))
    promo_discount = Decimal('0')
    promo_id = None

    # Promo validacija
    if promo_code:
        result = validate_promo_code(promo_code, OwnerType.TENANT, g.tenant_id, package_code)
        if not result['valid']:
            return {'error': result['reason']}, 400
        promo_discount = result['discount']
        promo_id = result['promo'].id

    # Kreiraj CreditBalance ako ne postoji
    balance = get_or_create_balance(OwnerType.TENANT, g.tenant_id)

    purchase = CreditPurchase(
        credit_balance_id=balance.id,
        package_code=package_code,
        credits_amount=credits_amount,
        price_eur=price_eur - promo_discount,
        price_rsd=(price_eur - promo_discount) * EUR_TO_RSD,
        discount_percent=Decimal(str(pkg['discount'])),
        promo_code_id=promo_id,
        promo_discount=promo_discount,
        payment_method=payment_method,
        payment_status=CreditPaymentStatus.PENDING,
        payment_reference=f"CREDIT-{idempotency_key}",
        idempotency_key=idempotency_key,
    )
    db.session.add(purchase)
    db.session.flush()

    response = {
        'purchase_id': purchase.id,
        'package': package_code,
        'credits': float(credits_amount),
        'price_eur': float(purchase.price_eur),
        'price_rsd': float(purchase.price_rsd),
        'promo_discount': float(promo_discount),
        'payment_method': payment_method,
        'status': 'pending',
        'payment_reference': purchase.payment_reference,
    }

    # Za bank transfer - generiši IPS QR
    if payment_method == 'bank_transfer':
        try:
            from app.services.ips_service import IPSService
            from app.models.platform_settings import PlatformSettings
            settings = PlatformSettings.get_settings()
            ips = IPSService(settings)

            # Kreiraj pseudo payment objekat za IPS
            class _QRPayment:
                def __init__(self, amount, ref, inv):
                    self.total_amount = amount
                    self.payment_reference = ref
                    self.invoice_number = inv

            qr_payment = _QRPayment(
                amount=purchase.price_rsd,
                ref=purchase.payment_reference,
                inv=f"CREDIT-{purchase.id}"
            )
            from app.models import Tenant
            tenant = Tenant.query.get(g.tenant_id)
            qr_string = ips.generate_qr_string(qr_payment, tenant, settings)
            qr_base64 = ips.generate_qr_base64(qr_string)
            response['qr_code'] = qr_base64
            response['qr_string'] = qr_string
        except Exception:
            pass  # QR generisanje nije kritično

    db.session.commit()
    return response, 201


@bp.route('/history', methods=['GET'])
@jwt_required
def get_transaction_history():
    """
    Istorija transakcija (paginirano).

    Query params:
        page: int (default 1)
        per_page: int (default 20, max 100)
        type: str (opciono) - filter po transaction_type
    """
    check = _check_credits_enabled()
    if check:
        return check

    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)
    txn_type = request.args.get('type')

    balance = CreditBalance.query.filter_by(
        owner_type=OwnerType.TENANT,
        tenant_id=g.tenant_id
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


@bp.route('/validate-promo', methods=['POST'])
@jwt_required
def validate_promo():
    """
    Validira promo kod.

    Body:
        code: str (obavezno)
        package: str (opciono) - za izračun popusta
    """
    check = _check_credits_enabled()
    if check:
        return check

    data = request.get_json() or {}
    code = data.get('code')
    package_code = data.get('package')

    if not code:
        return {'error': 'code je obavezan'}, 400

    result = validate_promo_code(code, OwnerType.TENANT, g.tenant_id, package_code)

    if result['valid']:
        return {
            'valid': True,
            'discount': float(result['discount']),
            'discount_type': result['promo'].discount_type.value,
            'discount_value': float(result['promo'].discount_value),
        }, 200
    else:
        return {
            'valid': False,
            'reason': result['reason'],
        }, 200


@bp.route('/export', methods=['GET'])
@jwt_required
def export_transactions():
    """CSV export svih transakcija."""
    check = _check_credits_enabled()
    if check:
        return check

    balance = CreditBalance.query.filter_by(
        owner_type=OwnerType.TENANT,
        tenant_id=g.tenant_id
    ).first()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Datum', 'Tip', 'Iznos', 'Stanje pre', 'Stanje posle', 'Opis'])

    if balance:
        transactions = CreditTransaction.query.filter_by(
            credit_balance_id=balance.id
        ).order_by(CreditTransaction.created_at.desc()).all()

        for t in transactions:
            writer.writerow([
                t.id,
                t.created_at.strftime('%Y-%m-%d %H:%M'),
                t.transaction_type.value,
                float(t.amount),
                float(t.balance_before),
                float(t.balance_after),
                t.description or '',
            ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=credits_export_{datetime.utcnow().strftime("%Y%m%d")}.csv'}
    )