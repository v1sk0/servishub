"""
Public User Requests - CRUD servisnih zahteva i accept bid.
"""

from datetime import datetime, timedelta
from flask import Blueprint, request, g
from app.extensions import db
from app.models.public_user import PublicUser
from app.models.service_request import (
    ServiceRequest, ServiceBid,
    ServiceRequestStatus, ServiceRequestCategory, ServiceBidStatus
)
from app.models.rating import Rating, RatingType
from app.models.content_report import ContentReport, ReportReason, ReportStatus
from app.models.credits import OwnerType, CreditTransactionType
from app.models.feature_flag import is_feature_enabled
from .auth import public_jwt_required

bp = Blueprint('public_requests', __name__, url_prefix='/requests')


def _check_b2c():
    if not is_feature_enabled('b2c_marketplace_enabled'):
        return {'error': 'B2C marketplace nije aktiviran'}, 403
    return None


@bp.route('', methods=['POST'])
@public_jwt_required
def create_request():
    """Kreiraj servisni zahtev. Max 3/dan."""
    check = _check_b2c()
    if check:
        return check

    # Rate limit: max 3 zahteva dnevno
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = ServiceRequest.query.filter(
        ServiceRequest.public_user_id == g.public_user_id,
        ServiceRequest.created_at >= today_start
    ).count()
    if today_count >= 3:
        return {'error': 'Maksimalno 3 zahteva dnevno'}, 429

    data = request.get_json() or {}

    try:
        category = ServiceRequestCategory(data.get('category', 'OTHER'))
    except ValueError:
        category = ServiceRequestCategory.OTHER

    title = data.get('title', '').strip()
    if not title:
        return {'error': 'Naslov je obavezan'}, 400

    sr = ServiceRequest(
        public_user_id=g.public_user_id,
        category=category,
        title=title,
        description=data.get('description'),
        device_type=data.get('device_type'),
        device_brand=data.get('device_brand'),
        device_model=data.get('device_model'),
        city=data.get('city'),
        latitude=data.get('latitude'),
        longitude=data.get('longitude'),
        budget_min=data.get('budget_min'),
        budget_max=data.get('budget_max'),
        urgency=data.get('urgency', 2),
        expires_at=datetime.utcnow() + timedelta(days=7),
    )
    db.session.add(sr)
    db.session.commit()

    return {
        'message': 'Zahtev kreiran',
        'request_id': sr.id,
    }, 201


@bp.route('', methods=['GET'])
@public_jwt_required
def list_requests():
    """Lista mojih zahteva."""
    check = _check_b2c()
    if check:
        return check

    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)

    query = ServiceRequest.query.filter_by(
        public_user_id=g.public_user_id
    ).order_by(ServiceRequest.created_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return {
        'requests': [{
            'id': r.id,
            'category': r.category.value,
            'title': r.title,
            'status': r.status.value,
            'city': r.city,
            'bid_count': r.bid_count,
            'created_at': r.created_at.isoformat(),
            'expires_at': r.expires_at.isoformat() if r.expires_at else None,
        } for r in pagination.items],
        'total': pagination.total,
        'page': page,
        'pages': pagination.pages,
    }, 200


@bp.route('/<int:request_id>/bids', methods=['GET'])
@public_jwt_required
def list_bids(request_id):
    """Lista ponuda za moj zahtev (anonimni servisi pre accept-a)."""
    check = _check_b2c()
    if check:
        return check

    sr = ServiceRequest.query.filter_by(
        id=request_id,
        public_user_id=g.public_user_id
    ).first()
    if not sr:
        return {'error': 'Zahtev nije pronađen'}, 404

    bids = ServiceBid.query.filter_by(
        service_request_id=request_id
    ).order_by(ServiceBid.created_at).all()

    from app.models import Tenant, ServiceLocation
    result = []
    for bid in bids:
        # Anonimni prikaz pre accept-a
        is_accepted = bid.status == ServiceBidStatus.ACCEPTED
        tenant = Tenant.query.get(bid.tenant_id)
        location = ServiceLocation.query.get(bid.location_id) if bid.location_id else None

        bid_data = {
            'id': bid.id,
            'price': float(bid.price),
            'currency': bid.currency,
            'estimated_days': bid.estimated_days,
            'warranty_days': bid.warranty_days,
            'description': bid.description,
            'status': bid.status.value,
            'created_at': bid.created_at.isoformat(),
        }

        if is_accepted and tenant:
            bid_data['tenant'] = {
                'id': tenant.id,
                'name': tenant.name,
                'city': tenant.grad,
                'rating': float(tenant.trust_score) if tenant.trust_score else None,
            }
            if location:
                bid_data['location'] = {
                    'name': location.name,
                    'address': location.address,
                    'phone': location.phone,
                }
        else:
            bid_data['tenant'] = {
                'city': tenant.grad if tenant else None,
                'is_revealed': False,
            }

        result.append(bid_data)

    return {'bids': result}, 200


@bp.route('/<int:request_id>/accept-bid', methods=['POST'])
@public_jwt_required
def accept_bid(request_id):
    """Prihvati ponudu (-1 kredit za otkrivanje servisa)."""
    check = _check_b2c()
    if check:
        return check

    sr = ServiceRequest.query.filter_by(
        id=request_id,
        public_user_id=g.public_user_id
    ).first()
    if not sr:
        return {'error': 'Zahtev nije pronađen'}, 404

    data = request.get_json() or {}
    bid_id = data.get('bid_id')
    if not bid_id:
        return {'error': 'bid_id je obavezan'}, 400

    bid = ServiceBid.query.filter_by(
        id=bid_id,
        service_request_id=request_id,
        status=ServiceBidStatus.PENDING
    ).first()
    if not bid:
        return {'error': 'Ponuda nije pronađena ili je već prihvaćena'}, 404

    # Dedukcija 1 kredita
    from app.services.credit_service import deduct_credits
    idempotency_key = f"accept_bid_{g.public_user_id}_{bid_id}"
    txn = deduct_credits(
        owner_type=OwnerType.PUBLIC_USER,
        owner_id=g.public_user_id,
        amount=1,
        transaction_type=CreditTransactionType.CONNECTION_FEE,
        description=f"Prihvatanje ponude #{bid_id}",
        ref_type='service_bid',
        ref_id=bid_id,
        idempotency_key=idempotency_key,
    )

    if txn is False:
        return {'error': 'Nemate dovoljno kredita', 'credits_required': 1}, 402

    bid.status = ServiceBidStatus.ACCEPTED
    bid.accepted_at = datetime.utcnow()
    bid.credit_transaction_id = txn.id
    sr.status = ServiceRequestStatus.ACCEPTED
    db.session.commit()

    # Vrati revealed podatke
    from app.models import Tenant, ServiceLocation
    tenant = Tenant.query.get(bid.tenant_id)
    location = ServiceLocation.query.get(bid.location_id) if bid.location_id else None

    return {
        'message': 'Ponuda prihvaćena',
        'tenant': {
            'id': tenant.id,
            'name': tenant.name,
            'email': tenant.email,
            'telefon': tenant.telefon,
            'city': tenant.grad,
        } if tenant else None,
        'location': {
            'name': location.name,
            'address': location.address,
            'phone': location.phone,
        } if location else None,
        'credits_spent': 1,
    }, 200


@bp.route('/ratings', methods=['POST'])
@public_jwt_required
def create_rating():
    """Ostavi ocenu za servis (samo posle završene transakcije)."""
    check = _check_b2c()
    if check:
        return check

    data = request.get_json() or {}
    service_request_id = data.get('service_request_id')
    score = data.get('score')
    comment = data.get('comment')

    if not service_request_id or not score:
        return {'error': 'service_request_id i score su obavezni'}, 400
    if score < 1 or score > 5:
        return {'error': 'Score mora biti 1-5'}, 400

    # Proveri da postoji accepted bid
    sr = ServiceRequest.query.filter_by(
        id=service_request_id,
        public_user_id=g.public_user_id
    ).first()
    if not sr:
        return {'error': 'Zahtev nije pronađen'}, 404

    accepted_bid = ServiceBid.query.filter_by(
        service_request_id=service_request_id,
        status=ServiceBidStatus.ACCEPTED
    ).first()
    if not accepted_bid:
        return {'error': 'Nema prihvaćene ponude za ovaj zahtev'}, 400

    # Proveri vremenski limit (30 dana)
    if accepted_bid.accepted_at and (datetime.utcnow() - accepted_bid.accepted_at).days > 30:
        return {'error': 'Istekao rok za ocenjivanje (30 dana)'}, 400

    # Proveri da nije već ocenjeno
    existing = Rating.query.filter_by(
        rater_type='public_user',
        rater_id=g.public_user_id,
        service_request_id=service_request_id
    ).first()
    if existing:
        return {'error': 'Već ste ocenili ovaj zahtev'}, 409

    rating = Rating(
        rating_type=RatingType.USER_TO_SERVICE,
        rater_type='public_user',
        rater_id=g.public_user_id,
        rated_type='tenant',
        rated_id=accepted_bid.tenant_id,
        score=score,
        comment=comment,
        service_request_id=service_request_id,
    )
    db.session.add(rating)
    db.session.commit()

    return {'message': 'Ocena ostavljena', 'rating_id': rating.id}, 201


@bp.route('/report', methods=['POST'])
@public_jwt_required
def report_content():
    """Prijavi sadržaj."""
    check = _check_b2c()
    if check:
        return check

    data = request.get_json() or {}
    entity_type = data.get('entity_type')
    entity_id = data.get('entity_id')
    reason = data.get('reason')

    if not entity_type or not entity_id or not reason:
        return {'error': 'entity_type, entity_id i reason su obavezni'}, 400

    try:
        reason_enum = ReportReason(reason)
    except ValueError:
        return {'error': f'Nepoznat razlog: {reason}'}, 400

    report = ContentReport(
        reporter_type='public_user',
        reporter_id=g.public_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        reason=reason_enum,
        description=data.get('description'),
    )
    db.session.add(report)
    db.session.commit()

    return {'message': 'Prijava poslata', 'report_id': report.id}, 201