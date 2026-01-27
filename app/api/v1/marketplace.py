"""
Marketplace API - Browse parts from suppliers and other tenants
"""
from flask import Blueprint, request, g
from app.extensions import db
from app.models import (
    SparePart, PartVisibility, PartCategory,
    Supplier, SupplierListing, SupplierStatus,
    Tenant, SupplierReveal
)
from app.api.middleware.auth import jwt_required
from sqlalchemy import or_, and_
from typing import Optional

bp = Blueprint('marketplace', __name__, url_prefix='/marketplace')


# ============== Routes ==============

@bp.route('/parts', methods=['GET'])
@jwt_required
def search_parts():
    """
    Search for parts across marketplace.
    Searches:
    - Supplier listings (active suppliers)
    - Other tenant parts marked as PUBLIC or PARTNER
    """
    # Search parameters
    q = request.args.get('q', '').strip()
    brand = request.args.get('brand')
    model = request.args.get('model')
    category = request.args.get('category')
    is_original = request.args.get('is_original')
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    source = request.args.get('source')  # 'supplier', 'tenant', or None for both
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)

    results = []

    # Dohvati revealed supplier ID-jeve
    revealed_supplier_ids = set(
        r.supplier_id for r in SupplierReveal.query.filter_by(
            tenant_id=g.tenant_id
        ).all()
    )

    # Search supplier listings
    if source != 'tenant':
        supplier_query = db.session.query(SupplierListing, Supplier).join(
            Supplier, SupplierListing.supplier_id == Supplier.id
        ).filter(
            Supplier.status == SupplierStatus.ACTIVE,
            SupplierListing.is_active == True,
            SupplierListing.stock_quantity > 0
        )

        if q:
            supplier_query = supplier_query.filter(
                or_(
                    SupplierListing.name.ilike(f'%{q}%'),
                    SupplierListing.part_number.ilike(f'%{q}%'),
                    SupplierListing.brand.ilike(f'%{q}%'),
                    SupplierListing.model_compatibility.ilike(f'%{q}%')
                )
            )

        if brand:
            supplier_query = supplier_query.filter(SupplierListing.brand.ilike(f'%{brand}%'))
        if model:
            supplier_query = supplier_query.filter(SupplierListing.model_compatibility.ilike(f'%{model}%'))
        if category:
            supplier_query = supplier_query.filter(SupplierListing.part_category == category)
        if is_original is not None:
            supplier_query = supplier_query.filter(SupplierListing.is_original == (is_original.lower() == 'true'))
        if min_price:
            supplier_query = supplier_query.filter(SupplierListing.price >= min_price)
        if max_price:
            supplier_query = supplier_query.filter(SupplierListing.price <= max_price)

        for listing, supplier in supplier_query.limit(per_page * 2).all():
            is_revealed = supplier.id in revealed_supplier_ids
            results.append({
                'id': listing.id,
                'source': 'supplier',
                'source_id': supplier.id,
                'source_name': supplier.name if is_revealed else None,
                'is_revealed': is_revealed,
                'source_rating': float(supplier.rating) if supplier.rating else None,
                'name': listing.name,
                'brand': listing.brand,
                'model': listing.model_compatibility,
                'part_category': listing.part_category,
                'part_number': listing.part_number,
                'is_original': listing.is_original,
                'quality_grade': listing.quality_grade,
                'price': float(listing.price),
                'currency': listing.currency or 'RSD',
                'stock_quantity': listing.stock_quantity,
                'stock_status': listing.stock_status,
                'delivery_days': listing.delivery_days,
                'min_order_qty': listing.min_order_qty or 1
            })

    # Search public/partner parts from other tenants
    if source != 'supplier':
        tenant_query = db.session.query(SparePart, Tenant).join(
            Tenant, SparePart.tenant_id == Tenant.id
        ).filter(
            SparePart.tenant_id != g.tenant_id,
            SparePart.is_active == True,
            SparePart.quantity > 0,
            SparePart.visibility.in_([PartVisibility.PUBLIC, PartVisibility.PARTNER])
        )

        if q:
            tenant_query = tenant_query.filter(
                or_(
                    SparePart.part_name.ilike(f'%{q}%'),
                    SparePart.part_number.ilike(f'%{q}%'),
                    SparePart.brand.ilike(f'%{q}%'),
                    SparePart.model.ilike(f'%{q}%')
                )
            )

        if brand:
            tenant_query = tenant_query.filter(SparePart.brand.ilike(f'%{brand}%'))
        if model:
            tenant_query = tenant_query.filter(SparePart.model.ilike(f'%{model}%'))
        if category:
            try:
                cat = PartCategory[category.upper()]
                tenant_query = tenant_query.filter(SparePart.part_category == cat)
            except KeyError:
                pass
        if is_original is not None:
            tenant_query = tenant_query.filter(SparePart.is_original == (is_original.lower() == 'true'))
        if min_price:
            tenant_query = tenant_query.filter(SparePart.public_price >= min_price)
        if max_price:
            tenant_query = tenant_query.filter(SparePart.public_price <= max_price)

        for part, tenant in tenant_query.limit(per_page * 2).all():
            # Use public_price for PUBLIC, selling_price for PARTNER
            price = part.public_price if part.visibility == PartVisibility.PUBLIC else part.selling_price

            results.append({
                'id': part.id,
                'source': 'tenant',
                'source_id': tenant.id,
                'source_name': tenant.name,
                'source_rating': None,  # TODO: Implement tenant ratings
                'name': part.part_name,
                'brand': part.brand,
                'model': part.model,
                'part_category': part.part_category.value,
                'part_number': part.part_number,
                'is_original': part.is_original,
                'quality_grade': part.quality_grade,
                'price': float(price) if price else None,
                'currency': part.currency or 'RSD',
                'stock_quantity': part.quantity,
                'stock_status': 'in_stock' if part.quantity > 0 else 'out_of_stock',
                'delivery_days': None,
                'min_order_qty': 1
            })

    # Sort by price
    results.sort(key=lambda x: x['price'] or float('inf'))

    # Paginate
    start = (page - 1) * per_page
    end = start + per_page
    paginated = results[start:end]

    return {
        'parts': paginated,
        'total': len(results),
        'page': page,
        'per_page': per_page,
        'pages': (len(results) + per_page - 1) // per_page
    }


@bp.route('/parts/<string:source>/<int:part_id>', methods=['GET'])
@jwt_required
def get_part_details(source, part_id):
    """Get detailed info about a marketplace part"""

    if source == 'supplier':
        listing = SupplierListing.query.get(part_id)
        if not listing or not listing.is_active:
            return {'error': 'Part not found'}, 404

        supplier = Supplier.query.get(listing.supplier_id)
        if not supplier or supplier.status != SupplierStatus.ACTIVE:
            return {'error': 'Supplier not available'}, 404

        return {
            'id': listing.id,
            'source': 'supplier',
            'supplier': {
                'id': supplier.id,
                'name': supplier.name,
                'city': supplier.city,
                'rating': float(supplier.rating) if supplier.rating else None,
                'rating_count': supplier.rating_count,
                'is_verified': supplier.is_verified
            },
            'name': listing.name,
            'brand': listing.brand,
            'model_compatibility': listing.model_compatibility,
            'part_category': listing.part_category,
            'part_number': listing.part_number,
            'description': listing.description,
            'is_original': listing.is_original,
            'quality_grade': listing.quality_grade,
            'price': float(listing.price),
            'currency': listing.currency or 'RSD',
            'stock_quantity': listing.stock_quantity,
            'stock_status': listing.stock_status,
            'delivery_days': listing.delivery_days,
            'min_order_qty': listing.min_order_qty or 1
        }

    elif source == 'tenant':
        part = SparePart.query.get(part_id)
        if not part or not part.is_active:
            return {'error': 'Part not found'}, 404

        if part.tenant_id == g.tenant_id:
            return {'error': 'Cannot view own part in marketplace'}, 400

        if part.visibility not in [PartVisibility.PUBLIC, PartVisibility.PARTNER]:
            return {'error': 'Part not available'}, 404

        tenant = Tenant.query.get(part.tenant_id)
        if not tenant:
            return {'error': 'Seller not found'}, 404

        price = part.public_price if part.visibility == PartVisibility.PUBLIC else part.selling_price

        return {
            'id': part.id,
            'source': 'tenant',
            'seller': {
                'id': tenant.id,
                'name': tenant.name,
                'city': None  # Could add from primary location
            },
            'name': part.part_name,
            'brand': part.brand,
            'model': part.model,
            'part_category': part.part_category.value,
            'part_number': part.part_number,
            'description': part.description,
            'is_original': part.is_original,
            'quality_grade': part.quality_grade,
            'price': float(price) if price else None,
            'currency': part.currency or 'RSD',
            'stock_quantity': part.quantity
        }

    else:
        return {'error': 'Invalid source'}, 400


@bp.route('/suppliers', methods=['GET'])
@jwt_required
def list_suppliers():
    """List active suppliers"""
    q = request.args.get('q', '').strip()
    city = request.args.get('city')
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)

    query = Supplier.query.filter_by(status=SupplierStatus.ACTIVE)

    if q:
        query = query.filter(
            or_(
                Supplier.name.ilike(f'%{q}%'),
                Supplier.city.ilike(f'%{q}%')
            )
        )

    if city:
        query = query.filter(Supplier.city.ilike(f'%{city}%'))

    # Order by rating, then name
    query = query.order_by(Supplier.rating.desc().nulls_last(), Supplier.name)

    total = query.count()
    suppliers = query.offset((page - 1) * per_page).limit(per_page).all()

    # Dohvati revealed supplier ID-jeve za ovog tenanta
    revealed_ids = set(
        r.supplier_id for r in SupplierReveal.query.filter_by(
            tenant_id=g.tenant_id
        ).all()
    )

    supplier_list = []
    for s in suppliers:
        if s.id in revealed_ids:
            supplier_list.append(s.to_revealed_dict())
        else:
            supplier_list.append(s.to_anonymous_dict())

    return {
        'suppliers': supplier_list,
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page
    }


@bp.route('/suppliers/<int:supplier_id>', methods=['GET'])
@jwt_required
def get_supplier(supplier_id):
    """Get supplier details with their listings"""
    supplier = Supplier.query.get(supplier_id)
    if not supplier or supplier.status != SupplierStatus.ACTIVE:
        return {'error': 'Supplier not found'}, 404

    # Proveri da li je otkriven
    is_revealed = SupplierReveal.query.filter_by(
        tenant_id=g.tenant_id,
        supplier_id=supplier_id
    ).first() is not None

    if is_revealed:
        result = supplier.to_revealed_dict()
    else:
        result = supplier.to_anonymous_dict()

    # Get listings (uvek vidljivi)
    listings = SupplierListing.query.filter_by(
        supplier_id=supplier_id,
        is_active=True
    ).filter(SupplierListing.stock_quantity > 0).limit(50).all()

    result['listings'] = [{
        'id': l.id,
        'name': l.name,
        'brand': l.brand,
        'part_category': l.part_category,
        'price': float(l.price),
        'currency': l.currency or 'RSD',
        'stock_quantity': l.stock_quantity
    } for l in listings]
    result['listings_count'] = SupplierListing.query.filter_by(
        supplier_id=supplier_id, is_active=True
    ).count()

    return result


@bp.route('/categories', methods=['GET'])
@jwt_required
def list_categories():
    """List available part categories"""
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
            {'value': 'MOTHERBOARD', 'label': 'Maticna ploca'},
            {'value': 'OTHER', 'label': 'Ostalo'}
        ]
    }


@bp.route('/brands', methods=['GET'])
@jwt_required
def list_brands():
    """Get list of popular brands from marketplace"""
    # Get brands from supplier listings
    supplier_brands = db.session.query(SupplierListing.brand).filter(
        SupplierListing.is_active == True,
        SupplierListing.brand.isnot(None)
    ).distinct().all()

    # Get brands from tenant parts
    tenant_brands = db.session.query(SparePart.brand).filter(
        SparePart.is_active == True,
        SparePart.visibility.in_([PartVisibility.PUBLIC, PartVisibility.PARTNER]),
        SparePart.brand.isnot(None)
    ).distinct().all()

    all_brands = set()
    for (brand,) in supplier_brands:
        if brand:
            all_brands.add(brand)
    for (brand,) in tenant_brands:
        if brand:
            all_brands.add(brand)

    return {
        'brands': sorted(list(all_brands))
    }
