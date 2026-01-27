"""
Public Marketplace - pretraga servisa i javni profili.
"""

from flask import Blueprint, request
from app.extensions import db
from app.models import Tenant, ServiceLocation, TenantStatus
from app.models.tenant_public_profile import TenantPublicProfile
from app.models.feature_flag import is_feature_enabled
from sqlalchemy import or_

bp = Blueprint('public_marketplace', __name__, url_prefix='/services')


@bp.route('', methods=['GET'])
def search_services():
    """Pretraga servisa po gradu/kategoriji (javno, bez autentifikacije)."""
    if not is_feature_enabled('b2c_marketplace_enabled'):
        return {'error': 'B2C marketplace nije aktiviran'}, 403

    q = request.args.get('q', '').strip()
    city = request.args.get('city')
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)

    query = Tenant.query.filter(
        Tenant.status.in_([TenantStatus.ACTIVE, TenantStatus.PROMO])
    )

    if q:
        query = query.filter(Tenant.name.ilike(f'%{q}%'))
    if city:
        query = query.filter(Tenant.grad.ilike(f'%{city}%'))

    query = query.order_by(Tenant.name)
    total = query.count()
    tenants = query.offset((page - 1) * per_page).limit(per_page).all()

    results = []
    for t in tenants:
        primary_loc = ServiceLocation.query.filter_by(
            tenant_id=t.id, is_primary=True
        ).first()
        results.append({
            'id': t.id,
            'slug': t.slug,
            'name': t.name,
            'city': t.grad,
            'phone': t.telefon,
            'location': {
                'name': primary_loc.name,
                'address': primary_loc.address,
                'city': primary_loc.city,
            } if primary_loc else None,
        })

    return {
        'services': results,
        'total': total,
        'page': page,
        'per_page': per_page,
    }, 200


@bp.route('/<string:slug>', methods=['GET'])
def get_service_profile(slug):
    """Javni profil servisa."""
    if not is_feature_enabled('b2c_marketplace_enabled'):
        return {'error': 'B2C marketplace nije aktiviran'}, 403

    tenant = Tenant.query.filter_by(slug=slug).first()
    if not tenant or tenant.status not in (TenantStatus.ACTIVE, TenantStatus.PROMO):
        return {'error': 'Servis nije pronađen'}, 404

    locations = ServiceLocation.query.filter_by(
        tenant_id=tenant.id, is_active=True
    ).all()

    profile = TenantPublicProfile.query.filter_by(tenant_id=tenant.id).first()

    return {
        'id': tenant.id,
        'slug': tenant.slug,
        'name': tenant.name,
        'city': tenant.grad,
        'phone': tenant.telefon,
        'email': tenant.email,
        'logo_url': tenant.logo_url,
        'profile': {
            'description': profile.description if profile else None,
            'specialties': profile.specialties_json if profile else None,
        } if profile else None,
        'locations': [{
            'id': loc.id,
            'name': loc.name,
            'address': loc.address,
            'city': loc.city,
            'phone': loc.phone,
            'working_hours': loc.working_hours_json,
        } for loc in locations],
    }, 200