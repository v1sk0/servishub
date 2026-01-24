"""
Admin Settings API - Upravljanje globalnim podesavanjima platforme.

Endpoint za citanje i izmenu platform settings-a.
"""

from flask import Blueprint, request, jsonify, g
from pydantic import BaseModel, ValidationError
from typing import Optional
from decimal import Decimal
from datetime import datetime, timezone

from ..middleware.auth import jwt_required, admin_required
from ...models import PlatformSettings, PackageChangeHistory
from ...models.admin_activity import AdminActivityLog, AdminActionType
from ...extensions import db


bp = Blueprint('admin_settings', __name__, url_prefix='/settings')


class UpdateSettingsRequest(BaseModel):
    """Request za azuriranje settings-a."""
    base_price: Optional[float] = None
    location_price: Optional[float] = None
    currency: Optional[str] = None
    trial_days: Optional[int] = None
    grace_period_days: Optional[int] = None
    default_commission: Optional[float] = None
    # demo_days - UKINUT (v102) - koristi se samo trial_days


@bp.route('', methods=['GET'])
@jwt_required
@admin_required
def get_settings():
    """
    Dohvata trenutna platform podesavanja.

    Returns:
        200: Platform settings
    """
    settings = PlatformSettings.get_settings()
    return jsonify(settings.to_dict()), 200


@bp.route('', methods=['PUT'])
@jwt_required
@admin_required
def update_settings():
    """
    Azurira platform podesavanja.

    Request body:
        - base_price: Cena baznog paketa (RSD)
        - location_price: Cena dodatne lokacije (RSD)
        - currency: Valuta
        - trial_days: Trajanje trial perioda (default 60 dana)
        - grace_period_days: Grace period pre suspenzije
        - default_commission: Default provizija dobavljaca (%)

    Returns:
        200: Azurirana podesavanja
        400: Validation error
    """
    try:
        data = UpdateSettingsRequest(**request.get_json())
    except ValidationError as e:
        return jsonify({
            'error': 'Validation Error',
            'details': e.errors()
        }), 400

    # Dohvati stare vrednosti za audit log
    old_settings = PlatformSettings.get_settings()
    old_values = old_settings.to_dict()

    # Azuriraj settings
    admin = g.current_admin
    new_settings = PlatformSettings.update_settings(
        data.model_dump(exclude_none=True),
        admin_id=admin.id
    )

    # Log promena
    new_values = new_settings.to_dict()
    changes = {}
    for key in old_values:
        if key != 'updated_at' and old_values.get(key) != new_values.get(key):
            changes[key] = {
                'old': old_values.get(key),
                'new': new_values.get(key)
            }

    if changes:
        AdminActivityLog.log(
            action_type=AdminActionType.UPDATE_SETTINGS,
            target_type='platform_settings',
            target_id=new_settings.id,
            target_name='Platform Settings',
            details={
                'changes': changes
            }
        )
        db.session.commit()

    return jsonify(new_settings.to_dict()), 200


@bp.route('/packages', methods=['GET'])
@jwt_required
@admin_required
def get_packages():
    """
    Dohvata podesavanja vezana za pakete/cenovnik.

    Returns:
        200: Package settings (samo cenovnik deo)
    """
    settings = PlatformSettings.get_settings()
    return jsonify({
        'base_price': float(settings.base_price) if settings.base_price else 3600,
        'location_price': float(settings.location_price) if settings.location_price else 1800,
        'currency': settings.currency or 'RSD',
        'trial_days': settings.trial_days or 60,  # Default 60 dana trial
        'grace_period_days': settings.grace_period_days or 7,
        'default_commission': float(settings.default_commission) if settings.default_commission else 5.0
    }), 200


class UpdatePackagesRequest(BaseModel):
    """Request za azuriranje paketa sa opcionalnim notify parametrom."""
    base_price: Optional[float] = None
    location_price: Optional[float] = None
    currency: Optional[str] = None
    trial_days: Optional[int] = None
    grace_period_days: Optional[int] = None
    default_commission: Optional[float] = None
    # Notification options
    notify_tenants: Optional[bool] = True  # Da li obavesti tenante o promeni
    change_reason: Optional[str] = None    # Razlog promene


@bp.route('/packages', methods=['PUT'])
@jwt_required
@admin_required
def update_packages():
    """
    Azurira podesavanja paketa/cenovnika sa verzioniranjem promena.

    Request body:
        - base_price: Cena baznog paketa (RSD)
        - location_price: Cena dodatne lokacije (RSD)
        - currency: Valuta
        - trial_days: Trajanje trial perioda
        - grace_period_days: Grace period pre suspenzije
        - default_commission: Default provizija dobavljaca (%)
        - notify_tenants: Da li obavesti tenante (default: true)
        - change_reason: Opcioni razlog promene

    Returns:
        200: Azurirana podesavanja + change_version
        400: Validation error
    """
    try:
        data = UpdatePackagesRequest(**request.get_json())
    except ValidationError as e:
        return jsonify({
            'error': 'Validation Error',
            'details': e.errors()
        }), 400

    admin = g.current_admin

    # Dohvati stare vrednosti
    old_settings = PlatformSettings.get_settings()
    old_values = {
        'base_price': float(old_settings.base_price) if old_settings.base_price else None,
        'location_price': float(old_settings.location_price) if old_settings.location_price else None,
        'currency': old_settings.currency,
        'trial_days': old_settings.trial_days,
        'grace_period_days': old_settings.grace_period_days,
        'default_commission': float(old_settings.default_commission) if old_settings.default_commission else None
    }

    # Primeni promene
    update_data = data.model_dump(exclude_none=True, exclude={'notify_tenants', 'change_reason'})
    if not update_data:
        return jsonify({
            'error': 'Bad Request',
            'message': 'Nema promena za snimanje'
        }), 400

    new_settings = PlatformSettings.update_settings(update_data, admin_id=admin.id)

    # Dohvati nove vrednosti
    new_values = {
        'base_price': float(new_settings.base_price) if new_settings.base_price else None,
        'location_price': float(new_settings.location_price) if new_settings.location_price else None,
        'currency': new_settings.currency,
        'trial_days': new_settings.trial_days,
        'grace_period_days': new_settings.grace_period_days,
        'default_commission': float(new_settings.default_commission) if new_settings.default_commission else None
    }

    # Proveri da li ima stvarnih promena
    has_changes = old_values != new_values

    change_version = None
    if has_changes:
        # Kreiraj PackageChangeHistory zapis (race-safe, idempotent)
        try:
            change, created = PackageChangeHistory.create_with_version(
                old_json=old_values,
                new_json=new_values,
                effective_at_utc=datetime.now(timezone.utc),
                admin_id=admin.id,
                change_reason=data.change_reason
            )
            change_version = change.change_version

            if not created:
                # Idempotency - ista promena već postoji
                return jsonify({
                    'message': 'Ova promena je već procesirana',
                    'change_id': change.id,
                    'change_version': change.change_version,
                    'settings': new_settings.to_dict()
                }), 200

        except RuntimeError as e:
            return jsonify({
                'error': 'Internal Error',
                'message': str(e)
            }), 500

        # Log promena u AdminActivityLog
        AdminActivityLog.log(
            action_type=AdminActionType.UPDATE_SETTINGS,
            target_type='platform_settings',
            target_id=new_settings.id,
            target_name='Package Settings',
            details={
                'change_version': change_version,
                'changes': {k: {'old': old_values.get(k), 'new': new_values.get(k)}
                           for k in old_values if old_values.get(k) != new_values.get(k)}
            }
        )

        db.session.commit()

        # TODO: Ako notify_tenants=True, pokreni async job za slanje notifikacija
        # if data.notify_tenants:
        #     from ..services.package_notification import schedule_notifications
        #     schedule_notifications(change.id)

    response = new_settings.to_dict()
    if change_version:
        response['change_version'] = change_version

    return jsonify(response), 200


# =============================================================================
# COMPANY DATA ENDPOINTS
# =============================================================================

class UpdateCompanyRequest(BaseModel):
    """Request za azuriranje podataka o firmi (ukljucuje i social za landing)."""
    company_name: Optional[str] = None
    company_address: Optional[str] = None
    company_city: Optional[str] = None
    company_postal_code: Optional[str] = None
    company_country: Optional[str] = None
    company_pib: Optional[str] = None
    company_mb: Optional[str] = None
    company_phone: Optional[str] = None
    company_email: Optional[str] = None
    company_website: Optional[str] = None
    company_bank_name: Optional[str] = None
    company_bank_account: Optional[str] = None
    # Social media za landing page
    social_twitter: Optional[str] = None
    social_facebook: Optional[str] = None
    social_instagram: Optional[str] = None
    social_linkedin: Optional[str] = None
    social_youtube: Optional[str] = None


@bp.route('/company', methods=['GET'])
@jwt_required
@admin_required
def get_company():
    """
    Dohvata podatke o firmi ServisHub.

    Returns:
        200: Company data
    """
    settings = PlatformSettings.get_settings()
    return jsonify(settings.get_company_data()), 200


@bp.route('/company', methods=['PUT'])
@jwt_required
@admin_required
def update_company():
    """
    Azurira podatke o firmi ServisHub.

    Request body:
        - company_name: Naziv firme
        - company_address: Adresa
        - company_city: Grad
        - company_postal_code: Postanski broj
        - company_country: Drzava
        - company_pib: PIB
        - company_mb: Maticni broj
        - company_phone: Telefon
        - company_email: Email
        - company_website: Web sajt
        - company_bank_name: Naziv banke
        - company_bank_account: Broj racuna

    Returns:
        200: Azurirani podaci o firmi
        400: Validation error
    """
    try:
        data = UpdateCompanyRequest(**request.get_json())
    except ValidationError as e:
        return jsonify({
            'error': 'Validation Error',
            'details': e.errors()
        }), 400

    # Dohvati stare vrednosti za audit log
    old_settings = PlatformSettings.get_settings()
    old_company = old_settings.get_company_data()

    # Azuriraj settings
    admin = g.current_admin
    new_settings = PlatformSettings.update_settings(
        data.model_dump(exclude_none=True),
        admin_id=admin.id
    )

    # Log promena
    new_company = new_settings.get_company_data()
    changes = {}
    for key in old_company:
        if old_company.get(key) != new_company.get(key):
            changes[key] = {
                'old': old_company.get(key),
                'new': new_company.get(key)
            }

    if changes:
        AdminActivityLog.log(
            action_type=AdminActionType.UPDATE_SETTINGS,
            target_type='platform_settings',
            target_id=new_settings.id,
            target_name='Company Data',
            details={
                'changes': changes,
                'section': 'company'
            }
        )
        db.session.commit()

    return jsonify({
        'message': 'Podaci o firmi uspesno azurirani',
        'company': new_company
    }), 200
