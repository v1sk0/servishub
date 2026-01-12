"""
Tenant Profile and Settings API
"""
from flask import Blueprint, request, g
from app.extensions import db
from app.models import Tenant, ServiceLocation, TenantUser, ServiceRepresentative
from app.api.middleware.auth import jwt_required
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

bp = Blueprint('tenant', __name__, url_prefix='/tenant')


# ============== Pydantic Schemas ==============

class TenantProfileUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=200)
    adresa_sedista: Optional[str] = Field(None, max_length=300)
    telefon: Optional[str] = Field(None, max_length=30)
    email: Optional[EmailStr] = None


class TenantSettingsUpdate(BaseModel):
    default_warranty_days: Optional[int] = Field(None, ge=0, le=365)
    default_currency: Optional[str] = Field(None, max_length=3)
    ticket_prefix: Optional[str] = Field(None, max_length=10)
    sms_notifications: Optional[bool] = None
    email_notifications: Optional[bool] = None
    auto_sms_on_ready: Optional[bool] = None


class KYCSubmission(BaseModel):
    ime: str = Field(..., min_length=2, max_length=50)
    prezime: str = Field(..., min_length=2, max_length=50)
    jmbg: Optional[str] = Field(None, max_length=13)
    broj_licne_karte: Optional[str] = Field(None, max_length=20)
    datum_rodjenja: Optional[str] = None
    adresa: Optional[str] = Field(None, max_length=300)
    grad: Optional[str] = Field(None, max_length=100)
    telefon: Optional[str] = Field(None, max_length=30)
    email: Optional[EmailStr] = None
    lk_front_url: Optional[str] = Field(None, max_length=500)
    lk_back_url: Optional[str] = Field(None, max_length=500)


# ============== Routes ==============

@bp.route('/profile', methods=['GET'])
@jwt_required
def get_profile():
    """Get tenant profile"""
    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    # Get stats
    locations_count = ServiceLocation.query.filter_by(
        tenant_id=tenant.id, is_active=True
    ).count()
    users_count = TenantUser.query.filter_by(
        tenant_id=tenant.id, is_active=True
    ).count()

    return {
        'id': tenant.id,
        'slug': tenant.slug,
        'name': tenant.name,
        'pib': tenant.pib,
        'maticni_broj': tenant.maticni_broj,
        'adresa_sedista': tenant.adresa_sedista,
        'email': tenant.email,
        'telefon': tenant.telefon,
        'status': tenant.status.value,
        'trial_ends_at': tenant.trial_ends_at.isoformat() if tenant.trial_ends_at else None,
        'subscription_ends_at': tenant.subscription_ends_at.isoformat() if tenant.subscription_ends_at else None,
        'created_at': tenant.created_at.isoformat(),
        'stats': {
            'locations': locations_count,
            'users': users_count
        }
    }


@bp.route('/profile', methods=['PUT'])
@jwt_required
def update_profile():
    """Update tenant profile (admin only)"""
    user = TenantUser.query.get(g.user_id)
    if not user or user.role.value not in ['OWNER', 'ADMIN']:
        return {'error': 'Admin access required'}, 403

    try:
        data = TenantProfileUpdate(**request.json)
    except Exception as e:
        return {'error': str(e)}, 400

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    # Update fields
    if data.name:
        tenant.name = data.name
    if data.adresa_sedista:
        tenant.adresa_sedista = data.adresa_sedista
    if data.telefon:
        tenant.telefon = data.telefon
    if data.email:
        tenant.email = data.email

    tenant.updated_at = datetime.utcnow()
    db.session.commit()

    return {'message': 'Profile updated', 'tenant_id': tenant.id}


@bp.route('/settings', methods=['GET'])
@jwt_required
def get_settings():
    """Get tenant settings"""
    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    settings = tenant.settings_json or {}

    return {
        'default_warranty_days': settings.get('default_warranty_days', 30),
        'default_currency': settings.get('default_currency', 'RSD'),
        'ticket_prefix': settings.get('ticket_prefix', ''),
        'sms_notifications': settings.get('sms_notifications', False),
        'email_notifications': settings.get('email_notifications', True),
        'auto_sms_on_ready': settings.get('auto_sms_on_ready', False),
        'working_hours': settings.get('working_hours', {}),
        'receipt_footer': settings.get('receipt_footer', ''),
        'terms_and_conditions': settings.get('terms_and_conditions', '')
    }


@bp.route('/settings', methods=['PUT'])
@jwt_required
def update_settings():
    """Update tenant settings (admin only)"""
    user = TenantUser.query.get(g.user_id)
    if not user or user.role.value not in ['OWNER', 'ADMIN']:
        return {'error': 'Admin access required'}, 403

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    # Get current settings
    settings = tenant.settings_json or {}

    # Update with new values
    new_settings = request.json or {}
    for key, value in new_settings.items():
        if value is not None:
            settings[key] = value

    tenant.settings_json = settings
    tenant.updated_at = datetime.utcnow()
    db.session.commit()

    return {'message': 'Settings updated'}


@bp.route('/subscription', methods=['GET'])
@jwt_required
def get_subscription():
    """Get subscription status"""
    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    # Count locations for pricing
    locations_count = ServiceLocation.query.filter_by(
        tenant_id=tenant.id, is_active=True
    ).count()

    # Calculate monthly cost
    base_price = 3600  # RSD
    location_price = 1800  # RSD per additional location
    additional_locations = max(0, locations_count - 1)
    monthly_total = base_price + (additional_locations * location_price)

    # Check if in trial
    is_trial = tenant.status.value == 'TRIAL'
    trial_days_left = 0
    if is_trial and tenant.trial_ends_at:
        delta = tenant.trial_ends_at - datetime.utcnow()
        trial_days_left = max(0, delta.days)

    return {
        'status': tenant.status.value,
        'is_trial': is_trial,
        'trial_days_left': trial_days_left,
        'trial_ends_at': tenant.trial_ends_at.isoformat() if tenant.trial_ends_at else None,
        'subscription_ends_at': tenant.subscription_ends_at.isoformat() if tenant.subscription_ends_at else None,
        'pricing': {
            'base_price': base_price,
            'location_price': location_price,
            'locations_count': locations_count,
            'additional_locations': additional_locations,
            'monthly_total': monthly_total,
            'currency': 'RSD'
        }
    }


@bp.route('/kyc', methods=['GET'])
@jwt_required
def get_kyc_status():
    """Get KYC verification status"""
    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    # Get primary representative
    representative = ServiceRepresentative.query.filter_by(
        tenant_id=tenant.id,
        is_primary=True
    ).first()

    if not representative:
        return {
            'kyc_submitted': False,
            'kyc_status': None,
            'representative': None
        }

    return {
        'kyc_submitted': True,
        'kyc_status': representative.status.value,
        'verified_at': representative.verified_at.isoformat() if representative.verified_at else None,
        'rejection_reason': representative.rejection_reason,
        'representative': {
            'id': representative.id,
            'ime': representative.ime,
            'prezime': representative.prezime,
            'email': representative.email,
            'telefon': representative.telefon
        }
    }


@bp.route('/kyc', methods=['POST'])
@jwt_required
def submit_kyc():
    """Submit KYC verification"""
    user = TenantUser.query.get(g.user_id)
    if not user or user.role.value not in ['OWNER', 'ADMIN']:
        return {'error': 'Admin access required'}, 403

    try:
        data = KYCSubmission(**request.json)
    except Exception as e:
        return {'error': str(e)}, 400

    # Check if already submitted
    existing = ServiceRepresentative.query.filter_by(
        tenant_id=g.tenant_id,
        is_primary=True
    ).first()

    if existing and existing.status.value == 'VERIFIED':
        return {'error': 'KYC already verified'}, 400

    if existing and existing.status.value == 'PENDING':
        return {'error': 'KYC already pending review'}, 400

    # Parse date
    datum_rodjenja = None
    if data.datum_rodjenja:
        try:
            datum_rodjenja = datetime.strptime(data.datum_rodjenja, '%Y-%m-%d').date()
        except:
            pass

    # Create or update representative
    if existing:
        existing.ime = data.ime
        existing.prezime = data.prezime
        existing.jmbg = data.jmbg
        existing.broj_licne_karte = data.broj_licne_karte
        existing.datum_rodjenja = datum_rodjenja
        existing.adresa = data.adresa
        existing.grad = data.grad
        existing.telefon = data.telefon
        existing.email = data.email
        existing.lk_front_url = data.lk_front_url
        existing.lk_back_url = data.lk_back_url
        existing.status = 'PENDING'
        existing.rejection_reason = None
        existing.updated_at = datetime.utcnow()
        representative = existing
    else:
        from app.models import RepresentativeStatus
        representative = ServiceRepresentative(
            tenant_id=g.tenant_id,
            ime=data.ime,
            prezime=data.prezime,
            jmbg=data.jmbg,
            broj_licne_karte=data.broj_licne_karte,
            datum_rodjenja=datum_rodjenja,
            adresa=data.adresa,
            grad=data.grad,
            telefon=data.telefon,
            email=data.email,
            lk_front_url=data.lk_front_url,
            lk_back_url=data.lk_back_url,
            is_primary=True,
            status=RepresentativeStatus.PENDING
        )
        db.session.add(representative)

    db.session.commit()

    return {
        'message': 'KYC submitted for review',
        'representative_id': representative.id
    }, 201