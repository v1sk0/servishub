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
    """
    Get complete subscription status with billing info.

    Returns:
        - status: DEMO/TRIAL/ACTIVE/EXPIRED/SUSPENDED
        - pricing: mesečna cena sa lokacijama
        - billing: dugovanje, dani kašnjenja
        - trust: trust score i "na reč" info
        - dates: svi relevantni datumi
    """
    from app.models import PlatformSettings

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    # Dobavi platformska podešavanja
    settings = PlatformSettings.get_settings()

    # Broj lokacija
    locations_count = ServiceLocation.query.filter_by(
        tenant_id=tenant.id, is_active=True
    ).count()

    # Cene (custom ili platformske)
    base_price = float(tenant.custom_base_price) if tenant.custom_base_price else float(settings.base_price)
    location_price = float(tenant.custom_location_price) if tenant.custom_location_price else float(settings.location_price)

    # Kalkulacija mesečne cene
    additional_locations = max(0, locations_count - 1)
    monthly_total = base_price + (additional_locations * location_price)

    # Status info
    is_demo = tenant.status.value == 'DEMO'
    is_trial = tenant.status.value == 'TRIAL'
    is_active = tenant.status.value == 'ACTIVE'
    is_expired = tenant.status.value == 'EXPIRED'
    is_suspended = tenant.status.value == 'SUSPENDED'

    # Preostali dani
    days_remaining = tenant.days_remaining

    # Custom pricing info
    custom_pricing = None
    if tenant.custom_base_price or tenant.custom_location_price:
        custom_pricing = {
            'base_price': float(tenant.custom_base_price) if tenant.custom_base_price else None,
            'location_price': float(tenant.custom_location_price) if tenant.custom_location_price else None,
            'reason': tenant.custom_price_reason,
            'valid_from': tenant.custom_price_valid_from.isoformat() if tenant.custom_price_valid_from else None
        }

    return {
        # Status
        'status': tenant.status.value,
        'is_demo': is_demo,
        'is_trial': is_trial,
        'is_active': is_active,
        'is_expired': is_expired,
        'is_suspended': is_suspended,
        'days_remaining': days_remaining,

        # Datumi
        'demo_ends_at': tenant.demo_ends_at.isoformat() if tenant.demo_ends_at else None,
        'trial_ends_at': tenant.trial_ends_at.isoformat() if tenant.trial_ends_at else None,
        'subscription_ends_at': tenant.subscription_ends_at.isoformat() if tenant.subscription_ends_at else None,

        # Cenovnik
        'pricing': {
            'base_price': base_price,
            'location_price': location_price,
            'platform_base_price': float(settings.base_price),
            'platform_location_price': float(settings.location_price),
            'locations_count': locations_count,
            'additional_locations': additional_locations,
            'monthly_total': monthly_total,
            'currency': settings.currency or 'RSD',
            'has_custom_pricing': custom_pricing is not None,
            'custom_pricing': custom_pricing
        },

        # Billing
        'billing': {
            'current_debt': float(tenant.current_debt) if tenant.current_debt else 0,
            'has_debt': tenant.has_debt,
            'days_overdue': tenant.days_overdue or 0,
            'last_payment_at': tenant.last_payment_at.isoformat() if tenant.last_payment_at else None,
            'is_blocked': tenant.is_blocked,
            'blocked_at': tenant.blocked_at.isoformat() if tenant.blocked_at else None,
            'block_reason': tenant.block_reason
        },

        # Trust Score
        'trust': {
            'score': tenant.trust_score or 100,
            'level': tenant.trust_level,
            'can_activate_trust': tenant.can_activate_trust,
            'is_trust_active': tenant.is_trust_active,
            'trust_hours_remaining': tenant.trust_hours_remaining,
            'trust_activated_at': tenant.trust_activated_at.isoformat() if tenant.trust_activated_at else None,
            'trust_activation_count': tenant.trust_activation_count or 0,
            'consecutive_on_time_payments': tenant.consecutive_on_time_payments or 0
        }
    }


@bp.route('/subscription/payments', methods=['GET'])
@jwt_required
def get_subscription_payments():
    """
    Lista svih faktura za tenant.

    Query params:
        - status: filter po statusu (PENDING, PAID, OVERDUE)
        - limit: broj rezultata (default 20)
        - offset: offset za paginaciju
    """
    from app.models import SubscriptionPayment

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    status = request.args.get('status')
    limit = min(request.args.get('limit', 20, type=int), 100)
    offset = request.args.get('offset', 0, type=int)

    # Base query
    query = SubscriptionPayment.query.filter_by(tenant_id=tenant.id)

    # Filter by status
    if status:
        query = query.filter(SubscriptionPayment.status == status)

    # Order by created_at desc
    query = query.order_by(SubscriptionPayment.created_at.desc())

    # Total count
    total = query.count()

    # Paginate
    payments = query.offset(offset).limit(limit).all()

    return {
        'payments': [p.to_dict() for p in payments],
        'total': total,
        'limit': limit,
        'offset': offset
    }


@bp.route('/subscription/payments/<int:payment_id>/notify', methods=['POST'])
@jwt_required
def notify_payment(payment_id):
    """
    Prijava uplate od strane servisa.

    Servis upload-uje sliku uplatnice i unosi referencu plaćanja.
    Admin kasnije verifikuje uplatu.

    Body JSON:
        - payment_method: BANK_TRANSFER/CARD/CASH
        - payment_reference: poziv na broj
        - payment_proof_url: URL slike uplatnice (Cloudinary)
        - payment_notes: napomena (opciono)
    """
    from app.models import SubscriptionPayment, TenantMessage, MessageCategory, MessagePriority
    from pydantic import BaseModel, Field
    from typing import Optional

    class PaymentNotification(BaseModel):
        payment_method: str = Field(..., pattern='^(BANK_TRANSFER|CARD|CASH)$')
        payment_reference: Optional[str] = Field(None, max_length=100)
        payment_proof_url: Optional[str] = Field(None, max_length=500)
        payment_notes: Optional[str] = None

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    # Find payment
    payment = SubscriptionPayment.query.filter_by(
        id=payment_id,
        tenant_id=tenant.id
    ).first()

    if not payment:
        return {'error': 'Payment not found'}, 404

    if payment.status == 'PAID':
        return {'error': 'Payment already verified'}, 400

    # Validate input
    try:
        data = PaymentNotification(**request.json)
    except Exception as e:
        return {'error': str(e)}, 400

    # Update payment
    payment.payment_method = data.payment_method
    payment.payment_reference = data.payment_reference
    payment.payment_proof_url = data.payment_proof_url
    payment.payment_notes = data.payment_notes
    payment.paid_at = datetime.utcnow()  # Označi kada je servis prijavio

    db.session.commit()

    return {
        'message': 'Uplata prijavljena. Čeka verifikaciju admina.',
        'payment': payment.to_dict()
    }


@bp.route('/subscription/trust-activate', methods=['POST'])
@jwt_required
def activate_trust():
    """
    Aktivira "Uključenje na reč" za blokirani servis.

    Omogućava servisu da nastavi rad za 48 sati uz obećanje plaćanja.
    Može se koristiti samo 1x mesečno i samo iz SUSPENDED statusa.
    """
    from app.models import TenantMessage, MessageCategory, MessagePriority
    from app.models.tenant import TenantStatus

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    # Proveri da li može aktivirati
    if not tenant.can_activate_trust:
        if tenant.status != TenantStatus.SUSPENDED:
            return {'error': 'Trust aktivacija je moguća samo iz SUSPENDED statusa'}, 400

        current_period = datetime.utcnow().strftime('%Y-%m')
        if tenant.last_trust_activation_period == current_period:
            return {'error': 'Već ste koristili "Na reč" ovog meseca'}, 400

        return {'error': 'Ne možete aktivirati "Na reč"'}, 400

    # Aktiviraj trust
    tenant.activate_trust()

    # Kreiraj sistemsku poruku
    TenantMessage.create_system_message(
        tenant_id=tenant.id,
        subject='Aktivirali ste "Uključenje na reč"',
        body=f'''Uspešno ste aktivirali "Uključenje na reč".

Imate 48 sati da izvršite uplatu ili pošaljete dokaz o uplati.

Ako ne platite u roku od 48 sati, nalog će ponovo biti blokiran,
a vaš Trust Score će biti umanjen za 30 poena.

Trenutni Trust Score: {tenant.trust_score}
Preostalo vreme: 48 sati''',
        category=MessageCategory.BILLING,
        priority=MessagePriority.URGENT,
        action_url='/settings/subscription',
        action_label='Pogledaj pretplatu'
    )

    db.session.commit()

    return {
        'message': 'Uključenje na reč aktivirano. Imate 48 sati da platite.',
        'trust_activated_at': tenant.trust_activated_at.isoformat(),
        'trust_hours_remaining': tenant.trust_hours_remaining,
        'trust_score': tenant.trust_score
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