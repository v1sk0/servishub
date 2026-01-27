"""
Service Requests API (Tenant side) - pretraga zahteva i slanje ponuda.
"""

from datetime import datetime
from decimal import Decimal
from flask import Blueprint, request, g
from app.extensions import db
from app.models import Tenant, ServiceLocation
from app.models.service_request import (
    ServiceRequest, ServiceBid,
    ServiceRequestStatus, ServiceBidStatus
)
from app.models.credits import OwnerType, CreditTransactionType
from app.models.feature_flag import is_feature_enabled
from app.api.middleware.auth import jwt_required

bp = Blueprint('service_requests', __name__, url_prefix='/service-requests')


def _check_b2c():
    if not is_feature_enabled('b2c_marketplace_enabled'):
        return {'error': 'B2C marketplace nije aktiviran'}, 403
    return None


@bp.route('', methods=['GET'])
@jwt_required
def list_requests():
    """Dostupni zahtevi u regionu."""
    check = _check_b2c()
    if check:
        return check

    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)
    city = request.args.get('city')
    category = request.args.get('category')

    query = ServiceRequest.query.filter(
        ServiceRequest.status.in_([
            ServiceRequestStatus.OPEN,
            ServiceRequestStatus.IN_BIDDING
        ])
    )

    if city:
        query = query.filter(ServiceRequest.city.ilike(f'%{city}%'))
    if category:
        query = query.filter(ServiceRequest.category == category)

    # Filtriraj istekle
    query = query.filter(
        db.or_(
            ServiceRequest.expires_at.is_(None),
            ServiceRequest.expires_at > datetime.utcnow()
        )
    )

    query = query.order_by(ServiceRequest.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return {
        'requests': [{
            'id': r.id,
            'category': r.category.value,
            'title': r.title,
            'description': r.description,
            'device_type': r.device_type,
            'device_brand': r.device_brand,
            'device_model': r.device_model,
            'city': r.city,
            'budget_min': float(r.budget_min) if r.budget_min else None,
            'budget_max': float(r.budget_max) if r.budget_max else None,
            'urgency': r.urgency,
            'bid_count': r.bid_count,
            'created_at': r.created_at.isoformat(),
            'expires_at': r.expires_at.isoformat() if r.expires_at else None,
        } for r in pagination.items],
        'total': pagination.total,
        'page': page,
        'pages': pagination.pages,
    }, 200


@bp.route('/<int:request_id>', methods=['GET'])
@jwt_required
def get_request(request_id):
    """Detalji zahteva (anonimni korisnik)."""
    check = _check_b2c()
    if check:
        return check

    sr = ServiceRequest.query.get(request_id)
    if not sr or sr.status not in (ServiceRequestStatus.OPEN, ServiceRequestStatus.IN_BIDDING):
        return {'error': 'Zahtev nije pronađen'}, 404

    # Korisnik je anoniman
    return {
        'id': sr.id,
        'category': sr.category.value,
        'title': sr.title,
        'description': sr.description,
        'device_type': sr.device_type,
        'device_brand': sr.device_brand,
        'device_model': sr.device_model,
        'city': sr.city,
        'budget_min': float(sr.budget_min) if sr.budget_min else None,
        'budget_max': float(sr.budget_max) if sr.budget_max else None,
        'urgency': sr.urgency,
        'bid_count': sr.bid_count,
        'view_count': sr.view_count,
        'created_at': sr.created_at.isoformat(),
        'expires_at': sr.expires_at.isoformat() if sr.expires_at else None,
    }, 200


@bp.route('/<int:request_id>/bid', methods=['POST'])
@jwt_required
def create_bid(request_id):
    """Pošalji ponudu za zahtev (-1 kredit)."""
    check = _check_b2c()
    if check:
        return check

    sr = ServiceRequest.query.get(request_id)
    if not sr or sr.status not in (ServiceRequestStatus.OPEN, ServiceRequestStatus.IN_BIDDING):
        return {'error': 'Zahtev nije dostupan za ponude'}, 400

    # Rate limit: max 20 bids/dan
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_bids = ServiceBid.query.filter(
        ServiceBid.tenant_id == g.tenant_id,
        ServiceBid.created_at >= today_start
    ).count()
    if today_bids >= 20:
        return {'error': 'Maksimalno 20 ponuda dnevno'}, 429

    # Proveri da nije već poslao ponudu
    existing = ServiceBid.query.filter_by(
        service_request_id=request_id,
        tenant_id=g.tenant_id
    ).first()
    if existing:
        return {'error': 'Već ste poslali ponudu za ovaj zahtev'}, 409

    data = request.get_json() or {}
    price = data.get('price')
    if not price:
        return {'error': 'Cena je obavezna'}, 400

    # Dedukcija 1 kredita
    from app.services.credit_service import deduct_credits
    idempotency_key = f"bid_{g.tenant_id}_{request_id}"
    txn = deduct_credits(
        owner_type=OwnerType.TENANT,
        owner_id=g.tenant_id,
        amount=1,
        transaction_type=CreditTransactionType.FEATURED,
        description=f"Ponuda za zahtev #{request_id}",
        ref_type='service_bid',
        ref_id=request_id,
        idempotency_key=idempotency_key,
    )

    if txn is False:
        return {'error': 'Nemate dovoljno kredita', 'credits_required': 1}, 402

    bid = ServiceBid(
        service_request_id=request_id,
        tenant_id=g.tenant_id,
        location_id=data.get('location_id'),
        price=Decimal(str(price)),
        currency=data.get('currency', 'RSD'),
        estimated_days=data.get('estimated_days'),
        warranty_days=data.get('warranty_days', 45),
        description=data.get('description'),
        credit_transaction_id=txn.id,
    )
    db.session.add(bid)

    # Ažuriraj bid count i status
    sr.bid_count = (sr.bid_count or 0) + 1
    if sr.status == ServiceRequestStatus.OPEN:
        sr.status = ServiceRequestStatus.IN_BIDDING

    db.session.commit()

    return {
        'message': 'Ponuda poslata',
        'bid_id': bid.id,
        'credits_spent': 1,
    }, 201


@bp.route('/my-bids', methods=['GET'])
@jwt_required
def my_bids():
    """Moje aktivne ponude."""
    check = _check_b2c()
    if check:
        return check

    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)

    query = ServiceBid.query.filter_by(
        tenant_id=g.tenant_id
    ).order_by(ServiceBid.created_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return {
        'bids': [{
            'id': b.id,
            'service_request_id': b.service_request_id,
            'price': float(b.price),
            'currency': b.currency,
            'estimated_days': b.estimated_days,
            'warranty_days': b.warranty_days,
            'status': b.status.value,
            'created_at': b.created_at.isoformat(),
            'accepted_at': b.accepted_at.isoformat() if b.accepted_at else None,
        } for b in pagination.items],
        'total': pagination.total,
        'page': page,
        'pages': pagination.pages,
    }, 200


@bp.route('/<int:request_id>/bid', methods=['DELETE'])
@jwt_required
def withdraw_bid(request_id):
    """Povuci ponudu."""
    check = _check_b2c()
    if check:
        return check

    bid = ServiceBid.query.filter_by(
        service_request_id=request_id,
        tenant_id=g.tenant_id,
        status=ServiceBidStatus.PENDING
    ).first()
    if not bid:
        return {'error': 'Ponuda nije pronađena'}, 404

    bid.status = ServiceBidStatus.WITHDRAWN
    db.session.commit()

    return {'message': 'Ponuda povučena'}, 200