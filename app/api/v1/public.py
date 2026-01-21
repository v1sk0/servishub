"""
Public API endpoints - dostupni bez autentifikacije.

Ovi endpointi sluze za javne stranice (landing, pricing, itd.)
"""

from flask import Blueprint, jsonify
from ...models import PlatformSettings

bp = Blueprint('public', __name__, url_prefix='/public')


@bp.route('/pricing', methods=['GET'])
def get_pricing():
    """
    Vraca javne informacije o cenama paketa.

    Returns:
        JSON sa cenama:
        {
            "base_price": 3600.0,
            "location_price": 1800.0,
            "currency": "RSD",
            "trial_days": 90
        }
    """
    settings = PlatformSettings.get_settings()

    return jsonify({
        'base_price': float(settings.base_price) if settings.base_price else 3600.0,
        'location_price': float(settings.location_price) if settings.location_price else 1800.0,
        'currency': settings.currency or 'RSD',
        'trial_days': settings.trial_days or 90,
        'contact': settings.get_contact_data()
    })
