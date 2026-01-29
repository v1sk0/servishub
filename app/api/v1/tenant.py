"""
Tenant Profile and Settings API
"""
import os
from flask import Blueprint, request, g, redirect, url_for, current_app
from sqlalchemy.orm.attributes import flag_modified
from app.extensions import db
from app.models import Tenant, ServiceLocation, TenantUser, ServiceRepresentative, TenantPublicProfile, PlatformSettings
from app.api.middleware.auth import jwt_required
from app.services.billing_tasks import get_next_invoice_number
from app.services.ips_service import IPSService
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta  # v3.05: kalendarski mesec
import secrets
import qrcode
import io
import base64

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


class PublicProfileUpdate(BaseModel):
    """Schema za ažuriranje public profile-a."""
    is_public: Optional[bool] = None

    # Osnovni podaci
    display_name: Optional[str] = Field(None, max_length=200)
    tagline: Optional[str] = Field(None, max_length=300)
    description: Optional[str] = None

    # Kontakt
    phone: Optional[str] = Field(None, max_length=50)
    phone_secondary: Optional[str] = Field(None, max_length=50)
    email: Optional[str] = Field(None, max_length=100)  # Allow empty string, validate separately
    address: Optional[str] = Field(None, max_length=300)
    city: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    maps_url: Optional[str] = Field(None, max_length=500)
    maps_embed_url: Optional[str] = Field(None, max_length=500)

    # Radno vreme
    working_hours: Optional[Dict[str, str]] = None

    # Branding
    logo_url: Optional[str] = Field(None, max_length=500)
    cover_image_url: Optional[str] = Field(None, max_length=500)
    primary_color: Optional[str] = Field(None, max_length=7)
    secondary_color: Optional[str] = Field(None, max_length=7)

    # Social linkovi
    facebook_url: Optional[str] = Field(None, max_length=300)
    instagram_url: Optional[str] = Field(None, max_length=300)
    twitter_url: Optional[str] = Field(None, max_length=300)
    linkedin_url: Optional[str] = Field(None, max_length=300)
    youtube_url: Optional[str] = Field(None, max_length=300)
    tiktok_url: Optional[str] = Field(None, max_length=300)
    website_url: Optional[str] = Field(None, max_length=300)

    # SEO
    meta_title: Optional[str] = Field(None, max_length=100)
    meta_description: Optional[str] = Field(None, max_length=200)
    meta_keywords: Optional[str] = Field(None, max_length=300)

    # Cenovnik
    show_prices: Optional[bool] = None
    price_disclaimer: Optional[str] = Field(None, max_length=500)

    # Dodatne sekcije
    about_title: Optional[str] = Field(None, max_length=200)
    about_content: Optional[str] = None
    why_us_title: Optional[str] = Field(None, max_length=200)
    why_us_items: Optional[List[Dict[str, Any]]] = None
    gallery_images: Optional[List[str]] = None
    testimonials: Optional[List[Dict[str, Any]]] = None

    # FAQ
    faq_title: Optional[str] = Field(None, max_length=200)
    faq_items: Optional[List[Dict[str, Any]]] = None  # [{"question": "...", "answer": "..."}]

    # Brendovi
    show_brands_section: Optional[bool] = None
    supported_brands: Optional[List[str]] = None  # ["apple", "samsung", ...]

    # Proces rada
    show_process_section: Optional[bool] = None
    process_title: Optional[str] = Field(None, max_length=200)
    process_steps: Optional[List[Dict[str, Any]]] = None  # [{"step": 1, "icon": "...", "title": "...", "description": "..."}]

    # WhatsApp
    show_whatsapp_button: Optional[bool] = None
    whatsapp_number: Optional[str] = Field(None, max_length=20)
    whatsapp_message: Optional[str] = Field(None, max_length=300)

    # Status tracking widget
    show_tracking_widget: Optional[bool] = None
    tracking_widget_title: Optional[str] = Field(None, max_length=200)

    # Hero stil
    hero_style: Optional[str] = Field(None, max_length=20)


class CustomDomainSetup(BaseModel):
    """Schema za podešavanje custom domena."""
    domain: str = Field(..., min_length=4, max_length=255)


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
        'logo_url': tenant.logo_url,
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


@bp.route('/upload/logo', methods=['POST'])
@jwt_required
def upload_logo():
    """
    Upload tenant logo to Cloudinary.

    Expects multipart/form-data with 'logo' file field.
    Only OWNER and ADMIN can upload logo.

    Returns:
        - 200: { url: "cloudinary_url", message: "Logo uploaded" }
        - 400: Validation error
        - 403: Permission denied
        - 500: Upload error
    """
    from app.utils.cloudinary_upload import upload_logo as do_upload

    user = TenantUser.query.get(g.user_id)
    if not user or user.role.value not in ['OWNER', 'ADMIN']:
        return {'error': 'Admin access required'}, 403

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    # Check if file is in request
    if 'logo' not in request.files:
        return {'error': 'Fajl nije prosleđen'}, 400

    file = request.files['logo']

    # Upload to Cloudinary
    result = do_upload(file, tenant.id)

    if not result['success']:
        return {'error': result['error']}, 400

    # Save URL to tenant
    tenant.logo_url = result['url']
    tenant.updated_at = datetime.utcnow()
    db.session.commit()

    return {
        'message': 'Logo uspešno uploadovan',
        'url': result['url'],
        'width': result.get('width'),
        'height': result.get('height')
    }


@bp.route('/upload/logo', methods=['DELETE'])
@jwt_required
def delete_logo():
    """
    Delete tenant logo from Cloudinary.

    Only OWNER and ADMIN can delete logo.
    """
    from app.utils.cloudinary_upload import delete_logo as do_delete

    user = TenantUser.query.get(g.user_id)
    if not user or user.role.value not in ['OWNER', 'ADMIN']:
        return {'error': 'Admin access required'}, 403

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    if not tenant.logo_url:
        return {'error': 'Logo ne postoji'}, 400

    # Delete from Cloudinary
    result = do_delete(tenant.id)

    # Clear URL from tenant regardless of Cloudinary result
    tenant.logo_url = None
    tenant.updated_at = datetime.utcnow()
    db.session.commit()

    return {'message': 'Logo obrisan'}


@bp.route('/upload/id-card/<side>', methods=['POST'])
@jwt_required
def upload_id_card(side):
    """
    Upload ID card image (front or back) to Cloudinary.

    Args:
        side: 'front' or 'back'

    Expects multipart/form-data with 'image' file field.
    Only OWNER and ADMIN can upload.
    """
    from app.utils.cloudinary_upload import upload_image

    if side not in ['front', 'back']:
        return {'error': 'Side must be "front" or "back"'}, 400

    user = TenantUser.query.get(g.user_id)
    if not user or user.role.value not in ['OWNER', 'ADMIN']:
        return {'error': 'Admin access required'}, 403

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    # Get existing representative
    representative = ServiceRepresentative.query.filter_by(
        tenant_id=tenant.id,
        is_primary=True
    ).first()

    if not representative:
        return {'error': 'Najpre unesite podatke odgovornog lica'}, 400

    # Check if file is in request
    if 'image' not in request.files:
        return {'error': 'Fajl nije prosleđen'}, 400

    file = request.files['image']

    # Upload to Cloudinary - folder: servishub/tenant_{id}/documents/lk_{side}
    filename = f'lk_{side}'
    result = upload_image(file, tenant.id, 'documents', filename)

    if not result['success']:
        return {'error': result['error']}, 400

    # Save URL to representative
    if side == 'front':
        representative.lk_front_url = result['url']
    else:
        representative.lk_back_url = result['url']

    representative.updated_at = datetime.utcnow()
    db.session.commit()

    return {
        'message': f'Lična karta ({side}) uspešno uploadovana',
        'url': result['url'],
        'side': side
    }


@bp.route('/upload/id-card/<side>', methods=['DELETE'])
@jwt_required
def delete_id_card(side):
    """
    Delete ID card image from Cloudinary.

    Args:
        side: 'front' or 'back'
    """
    from app.utils.cloudinary_upload import delete_image

    if side not in ['front', 'back']:
        return {'error': 'Side must be "front" or "back"'}, 400

    user = TenantUser.query.get(g.user_id)
    if not user or user.role.value not in ['OWNER', 'ADMIN']:
        return {'error': 'Admin access required'}, 403

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    representative = ServiceRepresentative.query.filter_by(
        tenant_id=tenant.id,
        is_primary=True
    ).first()

    if not representative:
        return {'error': 'Nema podataka o odgovornom licu'}, 400

    # Delete from Cloudinary
    filename = f'lk_{side}'
    delete_image(tenant.id, 'documents', filename)

    # Clear URL
    if side == 'front':
        representative.lk_front_url = None
    else:
        representative.lk_back_url = None

    representative.updated_at = datetime.utcnow()
    db.session.commit()

    return {'message': f'Slika lične karte ({side}) obrisana'}


@bp.route('/login-info', methods=['GET'])
@jwt_required
def get_login_info():
    """
    Vraća informacije o login URL-u za zaposlene.

    Ovo je privatni link koji owner deli sa zaposlenima.
    Samo OWNER i ADMIN mogu da vide ovaj endpoint.
    """
    user = TenantUser.query.get(g.user_id)
    if not user or user.role.value not in ['OWNER', 'ADMIN']:
        return {'error': 'Admin access required'}, 403

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    # Generiši pun URL za login zaposlenih
    base_url = f'https://{tenant.slug}.servishub.rs'
    login_url = f'{base_url}/login/{tenant.login_secret}'

    return {
        'login_url': login_url,
        'login_secret': tenant.login_secret,
        'tenant_name': tenant.name,
        'tenant_slug': tenant.slug
    }


@bp.route('/login-info/regenerate', methods=['POST'])
@jwt_required
def regenerate_login_secret():
    """
    Generiše novi login_secret (stari prestaje da važi).

    Samo OWNER može da regeneriše secret.
    PAŽNJA: Svi stari linkovi prestaju da rade!
    """
    user = TenantUser.query.get(g.user_id)
    if not user or user.role.value != 'OWNER':
        return {'error': 'Owner access required'}, 403

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    # Generiši novi secret
    tenant.login_secret = secrets.token_urlsafe(16)
    tenant.updated_at = datetime.utcnow()
    db.session.commit()

    # Generiši novi URL
    base_url = f'https://{tenant.slug}.servishub.rs'
    login_url = f'{base_url}/login/{tenant.login_secret}'

    return {
        'message': 'Login link regenerisan. Stari link više ne važi.',
        'login_url': login_url,
        'login_secret': tenant.login_secret
    }


@bp.route('/settings', methods=['GET'])
@jwt_required
def get_settings():
    """Get tenant settings"""
    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    settings = tenant.settings_json or {}

    # Default print clause
    default_clause = (
        'Predajom uređaja u servis prihvatam da sam odgovoran za svoje podatke i backup; '
        'servis ne odgovara za gubitak podataka, kartica i opreme, niti za kvar uređaja koji je posledica '
        'prethodnih oštećenja, vlage ili samog otvaranja uređaja, kao ni za gubitak vodootpornosti. '
        'Korisnik se obavezuje da preuzme uređaj najkasnije u roku od 30 dana od obaveštenja da je uređaj '
        'spreman za preuzimanje. Nakon isteka tog roka, servis ima pravo da obračuna naknadu za čuvanje uređaja, '
        'a dalje postupanje sa uređajem vršiće se u skladu sa važećim propisima. Garancija važi od datuma završetka popravke. '
        'Servis ne odgovara za ranije prisutna estetska oštećenja (ogrebotine, udubljenja, naprsline) koja su evidentirana '
        'pri prijemu uređaja ili su usled prljavštine i oštećenja bila prikrivena. U slučaju da popravka nije moguća ili '
        'korisnik odustane nakon postavljene ponude, servis ima pravo da naplati izvršenu dijagnostiku u iznosu od 2000 RSD.'
    )

    return {
        'default_warranty_days': settings.get('default_warranty_days', 30),
        'default_currency': settings.get('default_currency', 'RSD'),
        'ticket_prefix': settings.get('ticket_prefix', ''),
        'sms_notifications': settings.get('sms_notifications', False),
        'email_notifications': settings.get('email_notifications', True),
        'auto_sms_on_ready': settings.get('auto_sms_on_ready', False),
        'working_hours': settings.get('working_hours', {}),
        'receipt_footer': settings.get('receipt_footer', ''),
        'terms_and_conditions': settings.get('terms_and_conditions', ''),
        'print_clause': tenant.print_clause or default_clause
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

    # Get current settings (make a copy to trigger mutation detection)
    settings = dict(tenant.settings_json or {})

    # Update with new values
    new_settings = request.json or {}

    # Handle print_clause separately (dedicated column, not in settings_json)
    if 'print_clause' in new_settings:
        tenant.print_clause = new_settings.pop('print_clause')

    for key, value in new_settings.items():
        if value is not None:
            settings[key] = value

    tenant.settings_json = settings
    flag_modified(tenant, 'settings_json')  # Tell SQLAlchemy JSON was modified
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


@bp.route('/subscription/payments/<int:payment_id>/pdf', methods=['GET'])
@jwt_required
def get_payment_pdf(payment_id):
    """
    Download PDF fakture.

    Returns:
        PDF file
    """
    from flask import send_file
    from app.models import SubscriptionPayment
    from app.services.pdf_service import PDFService

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    # Access control: samo svoj payment
    payment = SubscriptionPayment.query.filter_by(
        id=payment_id,
        tenant_id=tenant.id
    ).first()

    if not payment:
        return {'error': 'Payment not found'}, 404

    pdf = PDFService()
    pdf_bytes = pdf.generate_invoice_pdf(payment)

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        download_name=f'faktura_{payment.invoice_number}.pdf'
    )


@bp.route('/subscription/payments/<int:payment_id>/uplatnica', methods=['GET'])
@jwt_required
def get_payment_slip(payment_id):
    """
    Download PDF uplatnice.

    Returns:
        PDF file
    """
    from flask import send_file
    from app.models import SubscriptionPayment
    from app.services.pdf_service import PDFService

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    payment = SubscriptionPayment.query.filter_by(
        id=payment_id,
        tenant_id=tenant.id
    ).first()

    if not payment:
        return {'error': 'Payment not found'}, 404

    pdf = PDFService()
    pdf_bytes = pdf.generate_payment_slip_pdf(payment)

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        download_name=f'uplatnica_{payment.invoice_number}.pdf'
    )


@bp.route('/subscription/payments/<int:payment_id>/qr', methods=['GET'])
@jwt_required
def get_payment_qr(payment_id):
    """
    Download IPS QR kod kao PNG.

    Returns:
        PNG image
    """
    from flask import send_file
    from app.models import SubscriptionPayment

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    payment = SubscriptionPayment.query.filter_by(
        id=payment_id,
        tenant_id=tenant.id
    ).first()

    if not payment:
        return {'error': 'Payment not found'}, 404

    settings = PlatformSettings.get_settings()
    ips = IPSService(settings)
    qr_string = ips.generate_qr_string(payment, tenant, settings)
    qr_bytes = ips.generate_qr_image(qr_string, size=300)

    return send_file(
        io.BytesIO(qr_bytes),
        mimetype='image/png',
        download_name=f'qr_{payment.invoice_number}.png'
    )


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


@bp.route('/subscription/create-invoice', methods=['POST'])
@jwt_required
def create_subscription_invoice():
    """
    Kreira uplatnicu/fakturu za pretplatu koju tenant sam bira.

    Request body:
        - months: Broj meseci (1, 3, 6, 12)

    Returns:
        - invoice: Detalji fakture
        - payment_info: Bankovni podaci za uplatu
    """
    from app.models import PlatformSettings, SubscriptionPayment

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    data = request.get_json() or {}
    months = data.get('months', 1)

    # Validacija
    if months not in [1, 3, 6, 12]:
        return {'error': 'Broj meseci mora biti 1, 3, 6 ili 12'}, 400

    # Proveri da li već postoji PENDING faktura
    existing_pending = SubscriptionPayment.query.filter_by(
        tenant_id=tenant.id,
        status='PENDING'
    ).first()

    if existing_pending:
        return {'error': 'Već imate fakturu na čekanju. Platite je ili sačekajte da istekne.'}, 400

    # Učitaj cene
    settings = PlatformSettings.get_settings()
    base_price = float(tenant.custom_base_price) if tenant.custom_base_price else float(settings.base_price)
    location_price = float(tenant.custom_location_price) if tenant.custom_location_price else float(settings.location_price)

    # Broj lokacija
    locations_count = ServiceLocation.query.filter_by(
        tenant_id=tenant.id, is_active=True
    ).count()
    locations_count = max(1, locations_count)

    # Kalkulacija cene
    additional_locations = max(0, locations_count - 1)
    monthly_price = base_price + (additional_locations * location_price)
    total_amount = monthly_price * months

    # Period - v3.05: kalendarski mesec
    period_start = datetime.utcnow().date()
    period_end = period_start + relativedelta(months=months)

    # Generiši broj fakture (race-safe sa SELECT FOR UPDATE)
    invoice_number = get_next_invoice_number(datetime.utcnow().year)

    # Generiši poziv na broj (IPS format)
    invoice_seq = int(invoice_number.split('-')[-1])  # SH-2026-000042 → 42
    ref_data = IPSService.generate_payment_reference(tenant.id, invoice_seq)
    payment_reference = ref_data['full']

    # Stavke fakture
    items = [
        {
            'description': 'Bazni paket ServisHub',
            'quantity': months,
            'unit_price': base_price,
            'total': base_price * months
        }
    ]
    if additional_locations > 0:
        items.append({
            'description': f'Dodatne lokacije ({additional_locations} x {location_price} RSD)',
            'quantity': months,
            'unit_price': location_price * additional_locations,
            'total': location_price * additional_locations * months
        })

    # Rok za plaćanje (7 dana)
    due_date = datetime.utcnow().date() + timedelta(days=7)

    # Kreiraj fakturu
    payment = SubscriptionPayment(
        tenant_id=tenant.id,
        invoice_number=invoice_number,
        period_start=period_start,
        period_end=period_end,
        items_json=items,
        subtotal=total_amount,
        total_amount=total_amount,
        currency='RSD',
        status='PENDING',
        due_date=due_date,
        payment_reference=payment_reference,
        payment_reference_model=ref_data['model'],
        is_auto_generated=False
    )
    db.session.add(payment)
    db.session.commit()

    return {
        'message': f'Faktura kreirana za {months} mesec(i)',
        'invoice': {
            'id': payment.id,
            'invoice_number': invoice_number,
            'period_start': period_start.isoformat(),
            'period_end': period_end.isoformat(),
            'months': months,
            'items': items,
            'total_amount': total_amount,
            'currency': 'RSD',
            'due_date': due_date.isoformat(),
            'status': 'PENDING'
        },
        'payment_info': _get_payment_info(payment_reference, total_amount, invoice_number, months)
    }


def _get_payment_info(payment_reference: str, amount: float, invoice_number: str, months: int) -> dict:
    """Vraća platne informacije iz PlatformSettings."""
    settings = PlatformSettings.get_settings()
    return {
        'bank_name': settings.company_bank_name or 'N/A',
        'account_number': settings.company_bank_account or 'N/A',
        'recipient': settings.company_name or 'ServisHub DOO',
        'payment_reference': payment_reference,
        'amount': amount,
        'purpose': f'Pretplata ServisHub {months} mes - {invoice_number}'
    }


@bp.route('/kyc', methods=['GET'])
@jwt_required
def get_kyc_status():
    """
    Get KYC verification status and representative data.

    Security:
    - JWT authentication required (tenant_id from token)
    - Sensitive data (JMBG, broj_licne_karte) only returned to OWNER/ADMIN
    - Other users see only verification status (no personal data)
    """
    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    # Check user role for sensitive data access
    user = TenantUser.query.get(g.user_id)
    is_admin = user and user.role.value in ['OWNER', 'ADMIN']

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

    # Base response with status info
    response = {
        'kyc_submitted': True,
        'kyc_status': representative.status.value,
        'verified_at': representative.verified_at.isoformat() if representative.verified_at else None,
        'rejection_reason': representative.rejection_reason
    }

    # Only OWNER/ADMIN can see full representative data (including sensitive fields)
    if is_admin:
        response['representative'] = {
            'id': representative.id,
            'ime': representative.ime,
            'prezime': representative.prezime,
            'jmbg': representative.jmbg,
            'broj_licne_karte': representative.broj_licne_karte,
            'datum_rodjenja': representative.datum_rodjenja.isoformat() if representative.datum_rodjenja else None,
            'email': representative.email,
            'telefon': representative.telefon,
            'adresa': representative.adresa,
            'grad': representative.grad,
            'lk_front_url': representative.lk_front_url,
            'lk_back_url': representative.lk_back_url
        }
    else:
        # Non-admin users only see basic status, no personal data
        response['representative'] = None

    return response


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

    # Only block if already verified
    if existing and existing.status.value == 'VERIFIED':
        return {'error': 'Već je verifikovano'}, 400

    # Allow updates while PENDING (user can correct mistakes)

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
        'message': 'Podaci poslati na verifikaciju',
        'representative_id': representative.id
    }, 201


# ============== Public Profile (Javna Stranica) ==============

@bp.route('/public-profile', methods=['GET'])
@jwt_required
def get_public_profile():
    """
    Dohvata public profile tenanta.

    Ako profil ne postoji, vraća prazan template.
    """
    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    profile = TenantPublicProfile.query.filter_by(tenant_id=tenant.id).first()

    if not profile:
        # Vrati prazan template
        return {
            'exists': False,
            'profile': None,
            'tenant_slug': tenant.slug,
            'subdomain_url': f'https://{tenant.slug}.servishub.rs'
        }

    return {
        'exists': True,
        'profile': profile.to_dict(include_private=True),
        'tenant_slug': tenant.slug,
        'subdomain_url': f'https://{tenant.slug}.servishub.rs',
        'custom_domain_url': f'https://{profile.custom_domain}' if profile.custom_domain and profile.custom_domain_verified else None
    }


def _preprocess_public_profile_data(data: dict) -> dict:
    """
    Preprocess data before Pydantic validation.

    - Converts dict-indexed objects (from FormData) to proper lists
    - Converts empty strings to None for optional fields
    """
    # Fields that should be lists
    list_fields = ['faq_items', 'supported_brands', 'process_steps', 'why_us_items',
                   'gallery_images', 'testimonials']

    for field in list_fields:
        if field in data and isinstance(data[field], dict):
            # Convert {'0': 'val1', '1': 'val2'} to ['val1', 'val2']
            try:
                # Sort by numeric key and extract values
                sorted_items = sorted(data[field].items(), key=lambda x: int(x[0]))
                data[field] = [item[1] for item in sorted_items]
            except (ValueError, TypeError):
                # If keys aren't numeric, just take values
                data[field] = list(data[field].values())

    # Convert empty strings to None for email
    if 'email' in data and data['email'] == '':
        data['email'] = None

    return data


@bp.route('/public-profile', methods=['PUT'])
@jwt_required
def update_public_profile():
    """
    Ažurira public profile tenanta.

    Ako profil ne postoji, kreira novi.
    Samo OWNER i ADMIN mogu da menjaju.

    Security:
    - Requires JWT authentication
    - Only OWNER and ADMIN roles can update
    - HTML content is sanitized to prevent XSS
    - URLs are validated to prevent malicious links
    - Hex colors are validated
    """
    user = TenantUser.query.get(g.user_id)
    if not user or user.role.value not in ['OWNER', 'ADMIN']:
        return {'error': 'Admin access required'}, 403

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    try:
        # Preprocess data before validation
        raw_data = _preprocess_public_profile_data(request.json.copy())
        data = PublicProfileUpdate(**raw_data)
    except Exception as e:
        return {'error': str(e)}, 400

    # Import security utilities
    from app.utils.security import sanitize_html, sanitize_url, validate_hex_color

    # Dohvati ili kreiraj profil
    profile = TenantPublicProfile.query.filter_by(tenant_id=tenant.id).first()
    if not profile:
        profile = TenantPublicProfile(tenant_id=tenant.id)
        db.session.add(profile)

    # Ažuriraj polja with security sanitization
    update_data = data.model_dump(exclude_unset=True)

    # Fields that contain HTML and need sanitization
    html_fields = {'about_content', 'description'}

    # Fields that are URLs
    url_fields = {
        'logo_url', 'cover_image_url', 'maps_url', 'maps_embed_url',
        'facebook_url', 'instagram_url', 'twitter_url', 'linkedin_url',
        'youtube_url', 'tiktok_url', 'website_url'
    }

    # Fields that are hex colors
    color_fields = {'primary_color', 'secondary_color'}

    for field, value in update_data.items():
        if not hasattr(profile, field):
            continue

        # Apply appropriate sanitization
        if field in html_fields and value:
            value = sanitize_html(value)
        elif field in url_fields and value:
            value = sanitize_url(value)
        elif field in color_fields and value:
            value = validate_hex_color(value)

        setattr(profile, field, value)

        # Mark JSON fields as modified for SQLAlchemy to detect changes
        if field in ('working_hours', 'why_us_items', 'gallery_images', 'testimonials',
                     'faq_items', 'supported_brands', 'process_steps'):
            flag_modified(profile, field)

    profile.updated_at = datetime.utcnow()
    db.session.commit()

    return {
        'message': 'Public profile updated',
        'profile': profile.to_dict(include_private=True)
    }


@bp.route('/public-profile/custom-domain', methods=['POST'])
@jwt_required
def setup_custom_domain():
    """
    Postavlja custom domen za javnu stranicu.

    Generiše verifikacioni token i vraća DNS instrukcije.
    """
    user = TenantUser.query.get(g.user_id)
    if not user or user.role.value not in ['OWNER', 'ADMIN']:
        return {'error': 'Admin access required'}, 403

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    try:
        data = CustomDomainSetup(**request.json)
    except Exception as e:
        return {'error': str(e)}, 400

    # Sanitizuj domen
    domain = data.domain.lower().strip()
    if domain.startswith('http://') or domain.startswith('https://'):
        domain = domain.split('://', 1)[1]
    if domain.startswith('www.'):
        domain = domain[4:]
    domain = domain.rstrip('/')

    # Proveri da li domen već koristi drugi tenant
    existing = TenantPublicProfile.query.filter(
        TenantPublicProfile.custom_domain == domain,
        TenantPublicProfile.tenant_id != tenant.id
    ).first()
    if existing:
        return {'error': 'Ovaj domen je već registrovan'}, 400

    # Dohvati ili kreiraj profil
    profile = TenantPublicProfile.query.filter_by(tenant_id=tenant.id).first()
    if not profile:
        profile = TenantPublicProfile(tenant_id=tenant.id)
        db.session.add(profile)

    # Generiši verifikacioni token
    verification_token = secrets.token_hex(16)

    profile.custom_domain = domain
    profile.custom_domain_verified = False
    profile.custom_domain_verification_token = verification_token
    profile.custom_domain_verified_at = None
    profile.custom_domain_ssl_status = 'pending'
    profile.updated_at = datetime.utcnow()

    db.session.commit()

    return {
        'message': 'Custom domain configured. Please verify DNS records.',
        'domain': domain,
        'verification_instructions': profile.get_domain_verification_instructions()
    }


@bp.route('/public-profile/custom-domain/verify', methods=['POST'])
@jwt_required
def verify_custom_domain():
    """
    Verifikuje DNS postavke za custom domen.
    """
    user = TenantUser.query.get(g.user_id)
    if not user or user.role.value not in ['OWNER', 'ADMIN']:
        return {'error': 'Admin access required'}, 403

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    profile = TenantPublicProfile.query.filter_by(tenant_id=tenant.id).first()
    if not profile or not profile.custom_domain:
        return {'error': 'No custom domain configured'}, 400

    if profile.custom_domain_verified:
        return {'message': 'Domain already verified', 'verified': True}

    # Verifikuj DNS
    try:
        from app.middleware.public_site import verify_custom_domain_dns
        result = verify_custom_domain_dns(
            profile.custom_domain,
            profile.custom_domain_verification_token
        )
    except ImportError:
        # Ako dns resolver nije instaliran, simuliraj
        result = {
            'verified': False,
            'verification_record': False,
            'routing_record': False,
            'errors': ['DNS resolver not available. Please contact support.']
        }

    if result['verified']:
        profile.custom_domain_verified = True
        profile.custom_domain_verified_at = datetime.utcnow()
        profile.custom_domain_ssl_status = 'active'  # Heroku će automatski SSL
        db.session.commit()

        return {
            'message': 'Domain verified successfully!',
            'verified': True,
            'domain': profile.custom_domain,
            'url': f'https://{profile.custom_domain}'
        }
    else:
        return {
            'message': 'Domain verification failed',
            'verified': False,
            'errors': result.get('errors', []),
            'verification_record': result.get('verification_record', False),
            'routing_record': result.get('routing_record', False),
            'instructions': profile.get_domain_verification_instructions()
        }, 400


@bp.route('/public-profile/custom-domain', methods=['DELETE'])
@jwt_required
def remove_custom_domain():
    """
    Uklanja custom domen.
    """
    user = TenantUser.query.get(g.user_id)
    if not user or user.role.value not in ['OWNER', 'ADMIN']:
        return {'error': 'Admin access required'}, 403

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    profile = TenantPublicProfile.query.filter_by(tenant_id=tenant.id).first()
    if not profile:
        return {'error': 'No public profile'}, 404

    profile.custom_domain = None
    profile.custom_domain_verified = False
    profile.custom_domain_verification_token = None
    profile.custom_domain_verified_at = None
    profile.custom_domain_ssl_status = None
    profile.updated_at = datetime.utcnow()

    db.session.commit()

    return {'message': 'Custom domain removed'}


@bp.route('/public-profile/qrcode', methods=['GET'])
@jwt_required
def get_public_profile_qrcode():
    """
    Generiše QR kod za javnu stranicu tenanta.

    Query params:
        - type: 'subdomain' ili 'custom' (default: 'subdomain')
        - size: veličina u pikselima (default: 200)
    """
    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    profile = TenantPublicProfile.query.filter_by(tenant_id=tenant.id).first()

    domain_type = request.args.get('type', 'subdomain')
    size = min(request.args.get('size', 200, type=int), 500)

    # Odredi URL
    if domain_type == 'custom' and profile and profile.custom_domain and profile.custom_domain_verified:
        url = f'https://{profile.custom_domain}'
    else:
        url = f'https://{tenant.slug}.servishub.rs'

    # Generiši QR kod
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    # Resize
    img = img.resize((size, size))

    # Convert to base64
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

    return {
        'url': url,
        'qrcode': f'data:image/png;base64,{img_base64}'
    }


@bp.route('/public-profile/preview', methods=['GET'])
@jwt_required
def get_public_profile_preview():
    """
    Vraća preview podataka za javnu stranicu.

    Kombinuje podatke iz profila i tenanta, kao što bi se prikazali na javnoj stranici.
    """
    from app.models import ServiceItem

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    profile = TenantPublicProfile.query.filter_by(tenant_id=tenant.id).first()
    if not profile:
        return {
            'exists': False,
            'message': 'Public profile not configured'
        }

    # Dohvati usluge
    services = ServiceItem.query.filter_by(
        tenant_id=tenant.id,
        is_active=True
    ).order_by(ServiceItem.category, ServiceItem.display_order).all()

    # Grupiši po kategorijama
    services_by_category = {}
    for service in services:
        cat = service.category or 'Ostalo'
        if cat not in services_by_category:
            services_by_category[cat] = []
        services_by_category[cat].append(service.to_dict())

    return {
        'exists': True,
        'profile': profile.to_public_dict(tenant),
        'services': [s.to_dict() for s in services] if profile.show_prices else [],
        'services_by_category': services_by_category if profile.show_prices else {},
        'urls': {
            'subdomain': f'https://{tenant.slug}.servishub.rs',
            'custom_domain': f'https://{profile.custom_domain}' if profile.custom_domain and profile.custom_domain_verified else None
        }
    }


# ============== Feature Flags ==============

@bp.route('/features', methods=['GET'])
@jwt_required
def get_features():
    """Vrati aktivne feature flagove za tenant."""
    from app.models.feature_flag import is_feature_enabled
    return {
        'pos_enabled': is_feature_enabled('pos_enabled', g.tenant_id),
        'credits_enabled': is_feature_enabled('credits_enabled', g.tenant_id),
        'b2c_marketplace_enabled': is_feature_enabled('b2c_marketplace_enabled', g.tenant_id),
    }


# ============== Google Business Integration ==============

@bp.route('/google/status', methods=['GET'])
@jwt_required
def google_integration_status():
    """
    Vraća status Google Business integracije za tenant.
    """
    from app.models import TenantGoogleIntegration
    from app.services.google_integration_service import google_service

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    integration = TenantGoogleIntegration.query.filter_by(tenant_id=tenant.id).first()

    return {
        'is_configured': google_service.is_configured,
        'is_connected': integration is not None and integration.google_place_id is not None,
        'integration': integration.to_dict() if integration else None,
    }


@bp.route('/google/connect', methods=['GET'])
@jwt_required
def google_connect_url():
    """
    Vraća URL za povezivanje Google Business naloga.
    """
    from app.services.google_integration_service import google_service

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    if not google_service.is_configured:
        return {'error': 'Google integration not configured on server'}, 503

    # Build callback URL
    callback_url = url_for('v1_tenant.google_callback', _external=True)

    try:
        auth_url = google_service.get_authorization_url(tenant.id, callback_url)
        return {'auth_url': auth_url}
    except Exception as e:
        return {'error': str(e)}, 500


@bp.route('/google/callback', methods=['GET'])
def google_callback():
    """
    OAuth callback - završava povezivanje Google naloga.

    Ova ruta se poziva nakon što korisnik odobri pristup na Google-u.
    Redirect na frontend settings stranu sa statusom.
    """
    from app.services.google_integration_service import google_service

    code = request.args.get('code')
    state = request.args.get('state')  # tenant_id
    error = request.args.get('error')

    # Frontend URL za redirect
    frontend_base = os.environ.get('FRONTEND_URL', 'https://app.servishub.rs')

    if error:
        return redirect(f"{frontend_base}/settings?google_error={error}")

    if not code or not state:
        return redirect(f"{frontend_base}/settings?google_error=missing_params")

    try:
        tenant_id = int(state)
        callback_url = url_for('v1_tenant.google_callback', _external=True)

        # Exchange code for tokens
        google_service.connect_tenant(tenant_id, code, callback_url)

        return redirect(f"{frontend_base}/settings?google_connected=true")
    except Exception as e:
        current_app.logger.error(f"Google OAuth callback failed: {e}")
        return redirect(f"{frontend_base}/settings?google_error=auth_failed")


@bp.route('/google/place', methods=['POST'])
@jwt_required
def set_google_place():
    """
    Postavlja Google Place ID za tenant.

    Body:
        place_id: Google Place ID
        OR
        search_query: Naziv biznisa za pretragu
    """
    from app.models import TenantGoogleIntegration
    from app.services.google_integration_service import google_service

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    data = request.json or {}
    place_id = data.get('place_id')
    search_query = data.get('search_query')

    if not place_id and not search_query:
        return {'error': 'place_id or search_query required'}, 400

    try:
        if not place_id:
            # Search for place
            place = google_service.search_place_by_name(
                search_query,
                tenant.adresa_sedista
            )
            if not place:
                return {'error': 'Place not found', 'query': search_query}, 404
            place_id = place.get('id')

        # Set place ID and sync reviews
        integration = google_service.set_place_id(tenant.id, place_id)

        return {
            'message': 'Google Place connected',
            'integration': integration.to_dict()
        }
    except Exception as e:
        return {'error': str(e)}, 500


@bp.route('/google/search', methods=['GET'])
@jwt_required
def search_google_place():
    """
    Pretražuje Google Places po nazivu.
    Vraća listu rezultata za selekciju.
    """
    from app.services.google_integration_service import google_service

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    query = request.args.get('q', tenant.name)

    try:
        places = google_service.search_place_by_name(query)

        results = []
        for place in places[:10]:  # Limit to 10 results
            results.append({
                'place_id': place.get('id'),
                'name': place.get('displayName', {}).get('text'),
                'address': place.get('formattedAddress'),
                'rating': place.get('rating'),
                'reviews_count': place.get('userRatingCount'),
            })

        return {'results': results}
    except Exception as e:
        current_app.logger.error(f"Google search error: {e}")
        return {'error': str(e)}, 500


@bp.route('/google/sync', methods=['POST'])
@jwt_required
def sync_google_reviews():
    """
    Ručno pokreće sinhronizaciju Google recenzija.
    """
    from app.services.google_integration_service import google_service

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    try:
        success = google_service.sync_reviews(tenant.id)
        if success:
            return {'message': 'Reviews synced successfully'}
        return {'error': 'Sync failed'}, 500
    except Exception as e:
        return {'error': str(e)}, 500


@bp.route('/google/reviews', methods=['GET'])
@jwt_required
def get_google_reviews():
    """
    Vraća Google recenzije za tenant.
    """
    from app.models import TenantGoogleIntegration, TenantGoogleReview

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    integration = TenantGoogleIntegration.query.filter_by(tenant_id=tenant.id).first()
    if not integration:
        return {'reviews': [], 'integration': None}

    reviews = TenantGoogleReview.query.filter_by(
        tenant_id=tenant.id
    ).order_by(TenantGoogleReview.review_time.desc()).all()

    return {
        'integration': integration.to_dict(),
        'reviews': [r.to_dict() for r in reviews]
    }


@bp.route('/google/reviews/<int:review_id>/visibility', methods=['PUT'])
@jwt_required
def toggle_review_visibility(review_id):
    """
    Menja vidljivost recenzije na javnoj stranici.
    """
    from app.models import TenantGoogleReview

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    review = TenantGoogleReview.query.filter_by(
        id=review_id,
        tenant_id=tenant.id
    ).first()

    if not review:
        return {'error': 'Review not found'}, 404

    data = request.json or {}
    review.is_visible = data.get('is_visible', not review.is_visible)
    db.session.commit()

    return {'review': review.to_dict()}


@bp.route('/google/disconnect', methods=['DELETE'])
@jwt_required
def disconnect_google():
    """
    Prekida vezu sa Google Business nalogom.
    """
    from app.services.google_integration_service import google_service

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    google_service.disconnect_tenant(tenant.id)
    return {'message': 'Google integration disconnected'}