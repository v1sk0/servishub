"""
Supplier Delivery API - konfiguracija dostave.

Endpoints:
    GET  /delivery               - trenutna konfiguracija dostave
    PUT  /delivery               - azuriranje konfiguracije
    GET  /delivery/courier-services - lista dostupnih kurirskih sluzbi
"""

from flask import Blueprint, request, g, jsonify
from app.extensions import db
from .auth import supplier_jwt_required
from app.models.supplier import Supplier
from app.constants.courier_services import COURIER_SERVICES, get_courier_list

bp = Blueprint('supplier_delivery', __name__, url_prefix='/delivery')

VALID_DAY_KEYS = {'weekday', 'saturday', 'sunday'}
MAX_CITIES = 50
MAX_ROUNDS_PER_DAY = 4


def _validate_rounds(rounds):
    """Validira delivery_rounds JSON strukturu."""
    if not isinstance(rounds, dict):
        return 'delivery_rounds mora biti objekat'
    for key in rounds:
        if key not in VALID_DAY_KEYS:
            return f'Nevalidan kljuc: {key}. Dozvoljeni: weekday, saturday, sunday'
        if not isinstance(rounds[key], list):
            return f'{key} mora biti lista tura'
        if len(rounds[key]) > MAX_ROUNDS_PER_DAY:
            return f'Maksimalno {MAX_ROUNDS_PER_DAY} ture po danu'
        for r in rounds[key]:
            if not isinstance(r, dict):
                return f'Svaka tura mora biti objekat'
            if not r.get('name') or not r.get('cutoff') or not r.get('delivery_time'):
                return 'Svaka tura mora imati name, cutoff i delivery_time'
    return None


@bp.route('/', methods=['GET'])
@supplier_jwt_required
def get_delivery_config():
    """Vraca trenutnu konfiguraciju dostave dobavljaca."""
    supplier = Supplier.query.get(g.supplier_id)
    if not supplier:
        return {'error': 'Dobavljac nije pronadjen'}, 404

    return {
        'success': True,
        'data': {
            'delivery_cities': supplier.delivery_cities or [],
            'delivery_rounds': supplier.delivery_rounds or {},
            'courier_services': supplier.courier_services_config or [],
            'allows_pickup': supplier.allows_pickup or False,
            'delivery_notes': supplier.delivery_notes or '',
        }
    }


@bp.route('/', methods=['PUT'])
@supplier_jwt_required
def update_delivery_config():
    """Azurira konfiguraciju dostave dobavljaca."""
    supplier = Supplier.query.get(g.supplier_id)
    if not supplier:
        return {'error': 'Dobavljac nije pronadjen'}, 404

    data = request.json or {}

    # Validacija gradova
    cities = data.get('delivery_cities')
    if cities is not None:
        if not isinstance(cities, list):
            return {'error': 'delivery_cities mora biti lista'}, 400
        if len(cities) > MAX_CITIES:
            return {'error': f'Maksimalno {MAX_CITIES} gradova'}, 400
        # Trim i deduplikacija
        cities = list(dict.fromkeys(c.strip() for c in cities if isinstance(c, str) and c.strip()))
        supplier.delivery_cities = cities

    # Validacija tura
    rounds = data.get('delivery_rounds')
    if rounds is not None:
        err = _validate_rounds(rounds)
        if err:
            return {'error': err}, 400
        supplier.delivery_rounds = rounds

    # Validacija kurirskih sluzbi
    couriers = data.get('courier_services')
    if couriers is not None:
        if not isinstance(couriers, list):
            return {'error': 'courier_services mora biti lista'}, 400
        invalid = [c for c in couriers if c not in COURIER_SERVICES]
        if invalid:
            return {'error': f'Nepoznate kurirske sluzbe: {", ".join(invalid)}'}, 400
        supplier.courier_services_config = couriers

    # Licno preuzimanje
    pickup = data.get('allows_pickup')
    if pickup is not None:
        supplier.allows_pickup = bool(pickup)

    # Napomene
    notes = data.get('delivery_notes')
    if notes is not None:
        supplier.delivery_notes = notes.strip() if notes else None

    db.session.commit()

    return {
        'success': True,
        'message': 'Konfiguracija dostave sacuvana',
        'data': {
            'delivery_cities': supplier.delivery_cities or [],
            'delivery_rounds': supplier.delivery_rounds or {},
            'courier_services': supplier.courier_services_config or [],
            'allows_pickup': supplier.allows_pickup or False,
            'delivery_notes': supplier.delivery_notes or '',
        }
    }


@bp.route('/courier-services', methods=['GET'])
@supplier_jwt_required
def list_courier_services():
    """Vraca listu svih dostupnih kurirskih sluzbi."""
    return {
        'success': True,
        'data': get_courier_list(),
    }
