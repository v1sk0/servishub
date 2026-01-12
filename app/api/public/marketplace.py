"""
Public Marketplace API - Javni pregled delova.

Endpointi:
- GET /parts - Pretraga javnih delova (PUBLIC visibility)
- GET /parts/:id - Detalji javnog dela
- GET /suppliers - Lista verifikovanih dobavljaca

Ovi endpointi ne zahtevaju autentifikaciju i prikazuju samo javne delove.
Rate-limited za zastitu od abuse-a.
"""

from flask import Blueprint, request
from app.extensions import db
from app.models import (
    SparePart, PartVisibility, PartCategory,
    Supplier, SupplierListing, SupplierStatus,
    Tenant, ServiceLocation
)
from sqlalchemy import or_

bp = Blueprint('public_marketplace', __name__, url_prefix='/marketplace')


# ============== Routes ==============

@bp.route('/parts', methods=['GET'])
def search_parts():
    """
    Pretraga javnih delova iz marketplace-a.

    Query params:
    - q: Search query (name, brand, model)
    - brand: Filter by brand
    - category: Filter by category
    - city: Filter by city (supplier/tenant location)
    - page: Page number (default 1)
    - per_page: Items per page (default 20, max 50)

    Returns only PUBLIC visibility parts from:
    - Verified suppliers
    - Tenants who marked parts as PUBLIC
    """
    q = request.args.get('q', '').strip()
    brand = request.args.get('brand')
    category = request.args.get('category')
    city = request.args.get('city')
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 50)

    results = []

    # Search supplier listings
    supplier_query = db.session.query(SupplierListing, Supplier).join(
        Supplier, SupplierListing.supplier_id == Supplier.id
    ).filter(
        Supplier.status == SupplierStatus.ACTIVE,
        Supplier.is_verified == True,
        SupplierListing.is_active == True,
        SupplierListing.stock_quantity > 0
    )

    if q:
        supplier_query = supplier_query.filter(
            or_(
                SupplierListing.name.ilike(f'%{q}%'),
                SupplierListing.brand.ilike(f'%{q}%'),
                SupplierListing.model_compatibility.ilike(f'%{q}%')
            )
        )

    if brand:
        supplier_query = supplier_query.filter(SupplierListing.brand.ilike(f'%{brand}%'))

    if category:
        supplier_query = supplier_query.filter(SupplierListing.part_category == category)

    if city:
        supplier_query = supplier_query.filter(Supplier.city.ilike(f'%{city}%'))

    for listing, supplier in supplier_query.limit(per_page).all():
        results.append({
            'id': f'supplier_{listing.id}',
            'source': 'supplier',
            'name': listing.name,
            'brand': listing.brand,
            'model': listing.model_compatibility,
            'category': listing.part_category,
            'is_original': listing.is_original,
            'quality_grade': listing.quality_grade,
            'price': float(listing.price),
            'currency': listing.currency or 'RSD',
            'in_stock': listing.stock_quantity > 0,
            'delivery_days': listing.delivery_days,
            'seller': {
                'name': supplier.name,
                'city': supplier.city,
                'rating': float(supplier.rating) if supplier.rating else None,
                'is_verified': supplier.is_verified
            }
        })

    # Search PUBLIC tenant parts
    tenant_query = db.session.query(SparePart, Tenant).join(
        Tenant, SparePart.tenant_id == Tenant.id
    ).filter(
        SparePart.is_active == True,
        SparePart.quantity > 0,
        SparePart.visibility == PartVisibility.PUBLIC,
        SparePart.public_price.isnot(None)
    )

    if q:
        tenant_query = tenant_query.filter(
            or_(
                SparePart.part_name.ilike(f'%{q}%'),
                SparePart.brand.ilike(f'%{q}%'),
                SparePart.model.ilike(f'%{q}%')
            )
        )

    if brand:
        tenant_query = tenant_query.filter(SparePart.brand.ilike(f'%{brand}%'))

    if category:
        try:
            cat = PartCategory[category.upper()]
            tenant_query = tenant_query.filter(SparePart.part_category == cat)
        except KeyError:
            pass

    for part, tenant in tenant_query.limit(per_page).all():
        # Get primary location for city
        location = ServiceLocation.query.filter_by(
            tenant_id=tenant.id,
            is_primary=True
        ).first()

        if city and location and city.lower() not in (location.city or '').lower():
            continue

        results.append({
            'id': f'tenant_{part.id}',
            'source': 'service',
            'name': part.part_name,
            'brand': part.brand,
            'model': part.model,
            'category': part.part_category.value if part.part_category else None,
            'is_original': part.is_original,
            'quality_grade': part.quality_grade,
            'price': float(part.public_price),
            'currency': part.currency or 'RSD',
            'in_stock': part.quantity > 0,
            'delivery_days': None,
            'seller': {
                'name': tenant.name,
                'city': location.city if location else None,
                'rating': None,
                'is_verified': False
            }
        })

    # Sort by price
    results.sort(key=lambda x: x['price'])

    # Paginate
    start = (page - 1) * per_page
    end = start + per_page
    paginated = results[start:end]

    return {
        'parts': paginated,
        'total': len(results),
        'page': page,
        'per_page': per_page
    }


@bp.route('/suppliers', methods=['GET'])
def list_suppliers():
    """
    Lista verifikovanih dobavljača.

    Query params:
    - city: Filter by city
    - page, per_page: Pagination

    Returns basic info about verified suppliers.
    """
    city = request.args.get('city')
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 50)

    query = Supplier.query.filter_by(
        status=SupplierStatus.ACTIVE,
        is_verified=True
    )

    if city:
        query = query.filter(Supplier.city.ilike(f'%{city}%'))

    query = query.order_by(Supplier.rating.desc().nulls_last())

    total = query.count()
    suppliers = query.offset((page - 1) * per_page).limit(per_page).all()

    return {
        'suppliers': [{
            'id': s.id,
            'name': s.name,
            'city': s.city,
            'rating': float(s.rating) if s.rating else None,
            'rating_count': s.rating_count,
            'website': s.website
        } for s in suppliers],
        'total': total,
        'page': page,
        'per_page': per_page
    }


@bp.route('/categories', methods=['GET'])
def list_categories():
    """Lista dostupnih kategorija delova."""
    return {
        'categories': [
            {'value': 'DISPLAY', 'label': 'Ekran'},
            {'value': 'BATTERY', 'label': 'Baterija'},
            {'value': 'CHARGING_PORT', 'label': 'Port za punjenje'},
            {'value': 'CAMERA', 'label': 'Kamera'},
            {'value': 'SPEAKER', 'label': 'Zvučnik'},
            {'value': 'MICROPHONE', 'label': 'Mikrofon'},
            {'value': 'BUTTON', 'label': 'Dugme'},
            {'value': 'FRAME', 'label': 'Okvir'},
            {'value': 'BACK_COVER', 'label': 'Zadnja maska'},
            {'value': 'MOTHERBOARD', 'label': 'Matična ploča'},
            {'value': 'OTHER', 'label': 'Ostalo'}
        ]
    }


@bp.route('/cities', methods=['GET'])
def list_cities():
    """Lista gradova sa aktivnim dobavljačima/servisima."""
    # Get supplier cities
    supplier_cities = db.session.query(Supplier.city).filter(
        Supplier.status == SupplierStatus.ACTIVE,
        Supplier.is_verified == True,
        Supplier.city.isnot(None)
    ).distinct().all()

    # Get tenant location cities
    location_cities = db.session.query(ServiceLocation.city).filter(
        ServiceLocation.is_active == True,
        ServiceLocation.city.isnot(None)
    ).distinct().all()

    cities = set()
    for (city,) in supplier_cities:
        if city:
            cities.add(city.strip())
    for (city,) in location_cities:
        if city:
            cities.add(city.strip())

    return {
        'cities': sorted(list(cities))
    }
