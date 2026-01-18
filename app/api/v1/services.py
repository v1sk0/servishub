"""
Services API - Cenovnik usluga tenanta.

CRUD operacije za usluge (ServiceItem) koje tenant definise
u svom cenovniku. Kategorije su potpuno fleksibilne - tenant moze
koristiti predefinisane ili kreirati nove.
"""
from flask import Blueprint, request, g
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from app.extensions import db
from app.models import ServiceItem, DEFAULT_CATEGORIES, TenantUser
from app.api.middleware.auth import jwt_required
from pydantic import BaseModel, Field
from typing import Optional
from decimal import Decimal

bp = Blueprint('services', __name__, url_prefix='/services')


# ============== Pydantic Schemas ==============

class ServiceCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    description: Optional[str] = None
    category: str = Field(default='Ostalo', max_length=100)
    price: float = Field(..., ge=0)
    currency: str = Field(default='RSD', max_length=3)
    price_note: Optional[str] = Field(None, max_length=200)
    display_order: Optional[int] = Field(default=0)
    is_active: Optional[bool] = True


class ServiceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=200)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=100)
    price: Optional[float] = Field(None, ge=0)
    currency: Optional[str] = Field(None, max_length=3)
    price_note: Optional[str] = Field(None, max_length=200)
    display_order: Optional[int] = None
    is_active: Optional[bool] = None


# ============== Helper Functions ==============

def check_duplicate_name(tenant_id: int, name: str, exclude_id: int = None) -> bool:
    """Proverava da li postoji usluga sa istim imenom."""
    query = ServiceItem.query.filter_by(tenant_id=tenant_id, name=name)
    if exclude_id:
        query = query.filter(ServiceItem.id != exclude_id)
    return query.first() is not None


def get_tenant_categories(tenant_id: int) -> list:
    """
    Vraca listu kategorija za tenant.
    Kombinuje predefinisane kategorije sa kategorijama koje tenant vec koristi.
    """
    # Dohvati kategorije koje tenant vec koristi
    used_categories = db.session.query(ServiceItem.category).filter(
        ServiceItem.tenant_id == tenant_id,
        ServiceItem.category.isnot(None)
    ).distinct().all()
    used_categories = [c[0] for c in used_categories if c[0]]

    # Kombinuj sa predefinisanim
    all_categories = set(DEFAULT_CATEGORIES) | set(used_categories)

    return sorted(all_categories)


# ============== Routes ==============

@bp.route('', methods=['GET'])
@jwt_required
def list_services():
    """
    Lista svih usluga za tenant.

    Query params:
    - include_inactive: bool (default false) - ukljuci i neaktivne usluge
    - category: string - filter po kategoriji
    - search: string - pretraga po nazivu
    """
    include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'
    category_filter = request.args.get('category')
    search = request.args.get('search', '').strip()

    query = ServiceItem.query.filter_by(tenant_id=g.tenant_id)

    if not include_inactive:
        query = query.filter_by(is_active=True)

    if category_filter:
        query = query.filter_by(category=category_filter)

    if search:
        query = query.filter(ServiceItem.name.ilike(f'%{search}%'))

    services = query.order_by(ServiceItem.category, ServiceItem.display_order, ServiceItem.name).all()

    # Dohvati dostupne kategorije za dropdown
    categories = get_tenant_categories(g.tenant_id)

    return {
        'services': [s.to_dict() for s in services],
        'total': len(services),
        'categories': categories,
        'default_categories': DEFAULT_CATEGORIES
    }


@bp.route('/<int:service_id>', methods=['GET'])
@jwt_required
def get_service(service_id):
    """Detalji jedne usluge."""
    service = ServiceItem.query.filter_by(
        id=service_id,
        tenant_id=g.tenant_id
    ).first()

    if not service:
        return {'error': 'Usluga nije pronadjena'}, 404

    return service.to_dict()


@bp.route('', methods=['POST'])
@jwt_required
def create_service():
    """
    Kreiranje nove usluge.

    Samo OWNER, ADMIN i MANAGER mogu da kreiraju usluge.
    Naziv usluge mora biti jedinstven unutar tenanta.
    """
    user = TenantUser.query.get(g.user_id)
    if not user or user.role.value not in ['OWNER', 'ADMIN', 'MANAGER']:
        return {'error': 'Nemate dozvolu za ovu akciju'}, 403

    try:
        data = ServiceCreate(**request.json)
    except Exception as e:
        return {'error': str(e)}, 400

    # Proveri da li vec postoji usluga sa tim imenom
    if check_duplicate_name(g.tenant_id, data.name):
        return {'error': 'Usluga sa tim imenom vec postoji'}, 400

    # Sanitizuj kategoriju
    category = data.category.strip() if data.category else 'Ostalo'
    if not category:
        category = 'Ostalo'

    service = ServiceItem(
        tenant_id=g.tenant_id,
        name=data.name.strip(),
        description=data.description.strip() if data.description else None,
        category=category,
        price=Decimal(str(data.price)),
        currency=data.currency,
        price_note=data.price_note.strip() if data.price_note else None,
        display_order=data.display_order or 0,
        is_active=data.is_active
    )

    try:
        db.session.add(service)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return {'error': 'Usluga sa tim imenom vec postoji'}, 400

    return {
        'message': 'Usluga kreirana',
        'service': service.to_dict()
    }, 201


@bp.route('/<int:service_id>', methods=['PUT'])
@jwt_required
def update_service(service_id):
    """
    Azuriranje usluge.

    Samo OWNER, ADMIN i MANAGER mogu da azuriraju usluge.
    """
    user = TenantUser.query.get(g.user_id)
    if not user or user.role.value not in ['OWNER', 'ADMIN', 'MANAGER']:
        return {'error': 'Nemate dozvolu za ovu akciju'}, 403

    service = ServiceItem.query.filter_by(
        id=service_id,
        tenant_id=g.tenant_id
    ).first()

    if not service:
        return {'error': 'Usluga nije pronadjena'}, 404

    try:
        data = ServiceUpdate(**request.json)
    except Exception as e:
        return {'error': str(e)}, 400

    # Proveri da li novo ime vec postoji (ako se menja ime)
    if data.name is not None and data.name.strip() != service.name:
        if check_duplicate_name(g.tenant_id, data.name.strip(), exclude_id=service_id):
            return {'error': 'Usluga sa tim imenom vec postoji'}, 400
        service.name = data.name.strip()

    if data.description is not None:
        service.description = data.description.strip() if data.description else None

    if data.category is not None:
        service.category = data.category.strip() if data.category else 'Ostalo'

    if data.price is not None:
        service.price = Decimal(str(data.price))

    if data.currency is not None:
        service.currency = data.currency

    if data.price_note is not None:
        service.price_note = data.price_note.strip() if data.price_note else None

    if data.display_order is not None:
        service.display_order = data.display_order

    if data.is_active is not None:
        service.is_active = data.is_active

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return {'error': 'Usluga sa tim imenom vec postoji'}, 400

    return {
        'message': 'Usluga azurirana',
        'service': service.to_dict()
    }


@bp.route('/<int:service_id>', methods=['DELETE'])
@jwt_required
def delete_service(service_id):
    """
    Brisanje usluge.

    Samo OWNER i ADMIN mogu da brisu usluge.
    """
    user = TenantUser.query.get(g.user_id)
    if not user or user.role.value not in ['OWNER', 'ADMIN']:
        return {'error': 'Samo administrator moze da brise usluge'}, 403

    service = ServiceItem.query.filter_by(
        id=service_id,
        tenant_id=g.tenant_id
    ).first()

    if not service:
        return {'error': 'Usluga nije pronadjena'}, 404

    db.session.delete(service)
    db.session.commit()

    return {'message': 'Usluga obrisana'}


@bp.route('/reorder', methods=['PUT'])
@jwt_required
def reorder_services():
    """
    Promena redosleda usluga.

    Body:
    {
        "items": [
            {"id": 1, "display_order": 0},
            {"id": 2, "display_order": 1},
            ...
        ]
    }
    """
    user = TenantUser.query.get(g.user_id)
    if not user or user.role.value not in ['OWNER', 'ADMIN', 'MANAGER']:
        return {'error': 'Nemate dozvolu za ovu akciju'}, 403

    data = request.json or {}
    items = data.get('items', [])

    if not items:
        return {'error': 'Lista items je obavezna'}, 400

    for item in items:
        service_id = item.get('id')
        display_order = item.get('display_order')

        if service_id is None or display_order is None:
            continue

        service = ServiceItem.query.filter_by(
            id=service_id,
            tenant_id=g.tenant_id
        ).first()

        if service:
            service.display_order = display_order

    db.session.commit()

    return {'message': 'Redosled azuriran'}


@bp.route('/stats', methods=['GET'])
@jwt_required
def get_stats():
    """
    Statistika usluga tenanta.

    Vraca:
    - total: ukupan broj usluga
    - active: broj aktivnih usluga
    - categories_count: broj usluga po kategorijama
    """
    services = ServiceItem.query.filter_by(tenant_id=g.tenant_id).all()

    total = len(services)
    active = sum(1 for s in services if s.is_active)

    # Broj usluga po kategorijama
    categories_count = {}
    for s in services:
        cat = s.category or 'Ostalo'
        categories_count[cat] = categories_count.get(cat, 0) + 1

    return {
        'total': total,
        'active': active,
        'inactive': total - active,
        'categories_count': categories_count,
        'unique_categories': len(categories_count)
    }


@bp.route('/categories', methods=['GET'])
@jwt_required
def get_categories():
    """
    Vraca listu dostupnih kategorija.

    Kombinuje predefinisane kategorije sa kategorijama koje tenant vec koristi.
    """
    categories = get_tenant_categories(g.tenant_id)
    return {
        'categories': categories,
        'default_categories': DEFAULT_CATEGORIES
    }
