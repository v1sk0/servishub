"""
Admin API - KYC Verifikacija.

Endpointi za verifikaciju identiteta reprezentativa servisa
koji zele da prodaju na B2C marketplace-u.
"""

from datetime import datetime
from flask import Blueprint, request, jsonify, g

from app.extensions import db
from app.models import Tenant
from app.models.representative import ServiceRepresentative, RepresentativeStatus
from app.api.middleware.auth import platform_admin_required

bp = Blueprint('admin_kyc', __name__, url_prefix='/kyc')


@bp.route('/pending', methods=['GET'])
@platform_admin_required
def list_pending_verifications():
    """
    Lista svih reprezentativa koji cekaju verifikaciju.
    """
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)

    query = ServiceRepresentative.query.filter(
        ServiceRepresentative.status == RepresentativeStatus.PENDING
    ).order_by(ServiceRepresentative.created_at.asc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    items = []
    for rep in pagination.items:
        tenant = Tenant.query.get(rep.tenant_id)
        items.append({
            'id': rep.id,
            'tenant_id': rep.tenant_id,
            'tenant_name': tenant.name if tenant else None,
            'full_name': rep.full_name,
            'jmbg': rep.jmbg,  # Admin vidi ceo JMBG
            'address': rep.address,
            'phone': rep.phone,
            'lk_front_url': rep.lk_front_url,
            'lk_back_url': rep.lk_back_url,
            'status': rep.status.value,
            'created_at': rep.created_at.isoformat()
        })

    return jsonify({
        'representatives': items,
        'pagination': {
            'page': pagination.page,
            'per_page': pagination.per_page,
            'total': pagination.total,
            'pages': pagination.pages
        }
    }), 200


@bp.route('/<int:rep_id>', methods=['GET'])
@platform_admin_required
def get_representative(rep_id):
    """
    Detalji jednog reprezentativa za verifikaciju.
    """
    rep = ServiceRepresentative.query.get_or_404(rep_id)
    tenant = Tenant.query.get(rep.tenant_id)

    return jsonify({
        'representative': {
            'id': rep.id,
            'tenant_id': rep.tenant_id,
            'tenant_name': tenant.name if tenant else None,
            'tenant_pib': tenant.pib if tenant else None,
            'full_name': rep.full_name,
            'jmbg': rep.jmbg,
            'address': rep.address,
            'phone': rep.phone,
            'lk_front_url': rep.lk_front_url,
            'lk_back_url': rep.lk_back_url,
            'status': rep.status.value,
            'rejection_reason': rep.rejection_reason,
            'verified_at': rep.verified_at.isoformat() if rep.verified_at else None,
            'verified_by': rep.verified_by,
            'created_at': rep.created_at.isoformat()
        }
    }), 200


@bp.route('/<int:rep_id>/approve', methods=['POST'])
@platform_admin_required
def approve_representative(rep_id):
    """
    Odobrava KYC verifikaciju reprezentativa.
    Servis sada moze da prodaje na B2C marketplace-u.
    """
    rep = ServiceRepresentative.query.get_or_404(rep_id)

    if rep.status == RepresentativeStatus.VERIFIED:
        return jsonify({'error': 'Reprezentativ je vec verifikovan.'}), 400

    rep.status = RepresentativeStatus.VERIFIED
    rep.verified_at = datetime.utcnow()
    rep.verified_by = g.current_admin.id
    rep.rejection_reason = None

    db.session.commit()

    # TODO: Poslati email obavestenje tenantu

    return jsonify({
        'message': f'Reprezentativ "{rep.full_name}" je uspešno verifikovan.',
        'representative_id': rep.id,
        'status': rep.status.value,
        'verified_at': rep.verified_at.isoformat()
    }), 200


@bp.route('/<int:rep_id>/reject', methods=['POST'])
@platform_admin_required
def reject_representative(rep_id):
    """
    Odbija KYC verifikaciju sa razlogom.
    """
    rep = ServiceRepresentative.query.get_or_404(rep_id)
    data = request.get_json() or {}

    reason = data.get('reason')
    if not reason:
        return jsonify({'error': 'Razlog odbijanja je obavezan.'}), 400

    rep.status = RepresentativeStatus.REJECTED
    rep.rejection_reason = reason
    rep.verified_at = None
    rep.verified_by = None

    db.session.commit()

    # TODO: Poslati email obavestenje tenantu sa razlogom

    return jsonify({
        'message': f'Verifikacija za "{rep.full_name}" je odbijena.',
        'representative_id': rep.id,
        'status': rep.status.value,
        'reason': reason
    }), 200


@bp.route('/<int:rep_id>/request-resubmit', methods=['POST'])
@platform_admin_required
def request_resubmit(rep_id):
    """
    Zahteva ponovno slanje dokumenata.
    Koristi se kada su slike nejasne ili nepotpune.
    """
    rep = ServiceRepresentative.query.get_or_404(rep_id)
    data = request.get_json() or {}

    reason = data.get('reason', 'Molimo vas da ponovo pošaljete jasnije slike ličnih dokumenata.')

    rep.status = RepresentativeStatus.PENDING
    rep.rejection_reason = reason
    # Brisemo stare slike da bi morali ponovo da uploaduju
    rep.lk_front_url = None
    rep.lk_back_url = None

    db.session.commit()

    # TODO: Poslati email obavestenje tenantu

    return jsonify({
        'message': 'Zahtev za ponovno slanje dokumenata je poslat.',
        'representative_id': rep.id,
        'reason': reason
    }), 200


@bp.route('/stats', methods=['GET'])
@platform_admin_required
def kyc_stats():
    """
    Statistika KYC verifikacija.
    """
    pending_count = ServiceRepresentative.query.filter(
        ServiceRepresentative.status == RepresentativeStatus.PENDING
    ).count()

    verified_count = ServiceRepresentative.query.filter(
        ServiceRepresentative.status == RepresentativeStatus.VERIFIED
    ).count()

    rejected_count = ServiceRepresentative.query.filter(
        ServiceRepresentative.status == RepresentativeStatus.REJECTED
    ).count()

    # Prosecno vreme verifikacije (za verifikovane)
    from sqlalchemy import func
    avg_time = db.session.query(
        func.avg(
            func.extract('epoch', ServiceRepresentative.verified_at) -
            func.extract('epoch', ServiceRepresentative.created_at)
        )
    ).filter(
        ServiceRepresentative.status == RepresentativeStatus.VERIFIED,
        ServiceRepresentative.verified_at.isnot(None)
    ).scalar()

    avg_hours = round(avg_time / 3600, 1) if avg_time else None

    return jsonify({
        'pending': pending_count,
        'verified': verified_count,
        'rejected': rejected_count,
        'total': pending_count + verified_count + rejected_count,
        'average_verification_hours': avg_hours
    }), 200
