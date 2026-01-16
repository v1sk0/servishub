"""
Admin Settings API - Upravljanje globalnim podesavanjima platforme.

Endpoint za citanje i izmenu platform settings-a.
"""

from flask import Blueprint, request, jsonify, g
from pydantic import BaseModel, ValidationError
from typing import Optional
from decimal import Decimal

from ..middleware.auth import jwt_required, admin_required
from ...models import PlatformSettings
from ...models.admin_activity import AdminActivityLog, AdminActionType
from ...extensions import db


bp = Blueprint('admin_settings', __name__, url_prefix='/settings')


class UpdateSettingsRequest(BaseModel):
    """Request za azuriranje settings-a."""
    base_price: Optional[float] = None
    location_price: Optional[float] = None
    currency: Optional[str] = None
    trial_days: Optional[int] = None
    demo_days: Optional[int] = None
    grace_period_days: Optional[int] = None
    default_commission: Optional[float] = None


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
        - trial_days: Trajanje trial perioda
        - demo_days: Trajanje demo perioda
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
        'trial_days': settings.trial_days or 90,
        'demo_days': settings.demo_days or 7,
        'grace_period_days': settings.grace_period_days or 7,
        'default_commission': float(settings.default_commission) if settings.default_commission else 5.0
    }), 200


@bp.route('/packages', methods=['PUT'])
@jwt_required
@admin_required
def update_packages():
    """
    Azurira podesavanja paketa/cenovnika.

    Request body: Isto kao update_settings

    Returns:
        200: Azurirana podesavanja
        400: Validation error
    """
    # Isti handler kao update_settings
    return update_settings()
