"""
Supplier Listings API - Manage product catalog
"""
from flask import Blueprint, request, g
from app.extensions import db
from app.models import SupplierListing, Supplier
from .auth import supplier_jwt_required
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from decimal import Decimal

bp = Blueprint('supplier_listings', __name__, url_prefix='/listings')


# ============== Pydantic Schemas ==============

class ListingCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    brand: Optional[str] = Field(None, max_length=50)
    model_compatibility: Optional[str] = None
    part_category: Optional[str] = Field(None, max_length=50)
    part_number: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = None
    is_original: Optional[bool] = False
    quality_grade: Optional[str] = Field(None, max_length=20)
    price: float = Field(..., gt=0)
    currency: Optional[str] = Field('RSD', max_length=3)
    min_order_qty: Optional[int] = Field(1, ge=1)
    stock_quantity: Optional[int] = Field(0, ge=0)
    stock_status: Optional[str] = Field(None, max_length=20)
    delivery_days: Optional[int] = Field(None, ge=0)


class ListingUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=200)
    brand: Optional[str] = Field(None, max_length=50)
    model_compatibility: Optional[str] = None
    part_category: Optional[str] = Field(None, max_length=50)
    part_number: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = None
    is_original: Optional[bool] = None
    quality_grade: Optional[str] = Field(None, max_length=20)
    price: Optional[float] = Field(None, gt=0)
    currency: Optional[str] = Field(None, max_length=3)
    min_order_qty: Optional[int] = Field(None, ge=1)
    stock_quantity: Optional[int] = Field(None, ge=0)
    stock_status: Optional[str] = Field(None, max_length=20)
    delivery_days: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None


class BulkStockUpdate(BaseModel):
    listing_id: int
    stock_quantity: int = Field(..., ge=0)


# ============== Routes ==============

@bp.route('', methods=['GET'])
@supplier_jwt_required
def list_listings():
    """List all listings for current supplier"""
    include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'
    category = request.args.get('category')
    brand = request.args.get('brand')
    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 200)

    query = SupplierListing.query.filter_by(supplier_id=g.supplier_id)

    if not include_inactive:
        query = query.filter_by(is_active=True)

    if category:
        query = query.filter_by(part_category=category)

    if brand:
        query = query.filter(SupplierListing.brand.ilike(f'%{brand}%'))

    if q:
        query = query.filter(
            db.or_(
                SupplierListing.name.ilike(f'%{q}%'),
                SupplierListing.part_number.ilike(f'%{q}%'),
                SupplierListing.brand.ilike(f'%{q}%')
            )
        )

    query = query.order_by(SupplierListing.name)
    total = query.count()
    listings = query.offset((page - 1) * per_page).limit(per_page).all()

    return {
        'listings': [{
            'id': l.id,
            'name': l.name,
            'brand': l.brand,
            'model_compatibility': l.model_compatibility,
            'part_category': l.part_category,
            'part_number': l.part_number,
            'is_original': l.is_original,
            'quality_grade': l.quality_grade,
            'price': float(l.price),
            'currency': l.currency or 'RSD',
            'stock_quantity': l.stock_quantity,
            'stock_status': l.stock_status,
            'is_active': l.is_active,
            'updated_at': l.updated_at.isoformat() if l.updated_at else None
        } for l in listings],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page
    }


@bp.route('/<int:listing_id>', methods=['GET'])
@supplier_jwt_required
def get_listing(listing_id):
    """Get single listing details"""
    listing = SupplierListing.query.filter_by(
        id=listing_id,
        supplier_id=g.supplier_id
    ).first()

    if not listing:
        return {'error': 'Listing not found'}, 404

    return {
        'id': listing.id,
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
        'min_order_qty': listing.min_order_qty or 1,
        'stock_quantity': listing.stock_quantity,
        'stock_status': listing.stock_status,
        'delivery_days': listing.delivery_days,
        'is_active': listing.is_active,
        'created_at': listing.created_at.isoformat(),
        'updated_at': listing.updated_at.isoformat() if listing.updated_at else None
    }


@bp.route('', methods=['POST'])
@supplier_jwt_required
def create_listing():
    """Create new listing"""
    try:
        data = ListingCreate(**request.json)
    except Exception as e:
        return {'error': str(e)}, 400

    listing = SupplierListing(
        supplier_id=g.supplier_id,
        name=data.name,
        brand=data.brand,
        model_compatibility=data.model_compatibility,
        part_category=data.part_category,
        part_number=data.part_number,
        description=data.description,
        is_original=data.is_original,
        quality_grade=data.quality_grade,
        price=Decimal(str(data.price)),
        currency=data.currency or 'RSD',
        min_order_qty=data.min_order_qty or 1,
        stock_quantity=data.stock_quantity or 0,
        stock_status=data.stock_status,
        delivery_days=data.delivery_days,
        is_active=True
    )

    db.session.add(listing)
    db.session.commit()

    return {
        'message': 'Listing created',
        'listing_id': listing.id
    }, 201


@bp.route('/<int:listing_id>', methods=['PUT'])
@supplier_jwt_required
def update_listing(listing_id):
    """Update listing"""
    listing = SupplierListing.query.filter_by(
        id=listing_id,
        supplier_id=g.supplier_id
    ).first()

    if not listing:
        return {'error': 'Listing not found'}, 404

    try:
        data = ListingUpdate(**request.json)
    except Exception as e:
        return {'error': str(e)}, 400

    if data.name is not None:
        listing.name = data.name
    if data.brand is not None:
        listing.brand = data.brand
    if data.model_compatibility is not None:
        listing.model_compatibility = data.model_compatibility
    if data.part_category is not None:
        listing.part_category = data.part_category
    if data.part_number is not None:
        listing.part_number = data.part_number
    if data.description is not None:
        listing.description = data.description
    if data.is_original is not None:
        listing.is_original = data.is_original
    if data.quality_grade is not None:
        listing.quality_grade = data.quality_grade
    if data.price is not None:
        listing.price = Decimal(str(data.price))
    if data.currency is not None:
        listing.currency = data.currency
    if data.min_order_qty is not None:
        listing.min_order_qty = data.min_order_qty
    if data.stock_quantity is not None:
        listing.stock_quantity = data.stock_quantity
    if data.stock_status is not None:
        listing.stock_status = data.stock_status
    if data.delivery_days is not None:
        listing.delivery_days = data.delivery_days
    if data.is_active is not None:
        listing.is_active = data.is_active

    listing.updated_at = datetime.utcnow()
    db.session.commit()

    return {'message': 'Listing updated', 'listing_id': listing.id}


@bp.route('/<int:listing_id>', methods=['DELETE'])
@supplier_jwt_required
def delete_listing(listing_id):
    """Delete listing (soft delete)"""
    listing = SupplierListing.query.filter_by(
        id=listing_id,
        supplier_id=g.supplier_id
    ).first()

    if not listing:
        return {'error': 'Listing not found'}, 404

    listing.is_active = False
    listing.updated_at = datetime.utcnow()
    db.session.commit()

    return {'message': 'Listing deleted'}


@bp.route('/bulk-stock', methods=['PUT'])
@supplier_jwt_required
def bulk_update_stock():
    """Bulk update stock quantities"""
    data = request.json or {}
    updates = data.get('updates', [])

    if not updates:
        return {'error': 'No updates provided'}, 400

    updated_count = 0
    errors = []

    for update in updates:
        try:
            listing_id = update.get('listing_id')
            stock_quantity = update.get('stock_quantity')

            if listing_id is None or stock_quantity is None:
                errors.append(f'Invalid update: {update}')
                continue

            listing = SupplierListing.query.filter_by(
                id=listing_id,
                supplier_id=g.supplier_id
            ).first()

            if not listing:
                errors.append(f'Listing {listing_id} not found')
                continue

            listing.stock_quantity = max(0, int(stock_quantity))
            listing.updated_at = datetime.utcnow()
            updated_count += 1

        except Exception as e:
            errors.append(f'Error updating {listing_id}: {str(e)}')

    db.session.commit()

    return {
        'message': f'Updated {updated_count} listings',
        'updated_count': updated_count,
        'errors': errors if errors else None
    }


@bp.route('/stats', methods=['GET'])
@supplier_jwt_required
def get_stats():
    """Get listing statistics"""
    total = SupplierListing.query.filter_by(supplier_id=g.supplier_id).count()
    active = SupplierListing.query.filter_by(supplier_id=g.supplier_id, is_active=True).count()
    in_stock = SupplierListing.query.filter(
        SupplierListing.supplier_id == g.supplier_id,
        SupplierListing.is_active == True,
        SupplierListing.stock_quantity > 0
    ).count()
    out_of_stock = active - in_stock

    # Categories breakdown
    categories = db.session.query(
        SupplierListing.part_category,
        db.func.count(SupplierListing.id)
    ).filter_by(
        supplier_id=g.supplier_id,
        is_active=True
    ).group_by(SupplierListing.part_category).all()

    return {
        'total_listings': total,
        'active_listings': active,
        'in_stock': in_stock,
        'out_of_stock': out_of_stock,
        'categories': {cat or 'uncategorized': count for cat, count in categories}
    }


@bp.route('/import', methods=['POST'])
@supplier_jwt_required
def import_listings():
    """Import listings from JSON array"""
    data = request.json or {}
    listings_data = data.get('listings', [])

    if not listings_data:
        return {'error': 'No listings provided'}, 400

    created = 0
    updated = 0
    errors = []

    for item in listings_data:
        try:
            # Check if exists by part_number
            part_number = item.get('part_number')
            existing = None

            if part_number:
                existing = SupplierListing.query.filter_by(
                    supplier_id=g.supplier_id,
                    part_number=part_number
                ).first()

            if existing:
                # Update existing
                existing.name = item.get('name', existing.name)
                existing.brand = item.get('brand', existing.brand)
                existing.price = Decimal(str(item.get('price', existing.price)))
                existing.stock_quantity = item.get('stock_quantity', existing.stock_quantity)
                existing.updated_at = datetime.utcnow()
                updated += 1
            else:
                # Create new
                listing = SupplierListing(
                    supplier_id=g.supplier_id,
                    name=item.get('name', 'Untitled'),
                    brand=item.get('brand'),
                    model_compatibility=item.get('model_compatibility'),
                    part_category=item.get('part_category'),
                    part_number=part_number,
                    description=item.get('description'),
                    is_original=item.get('is_original', False),
                    quality_grade=item.get('quality_grade'),
                    price=Decimal(str(item.get('price', 0))),
                    currency=item.get('currency', 'RSD'),
                    min_order_qty=item.get('min_order_qty', 1),
                    stock_quantity=item.get('stock_quantity', 0),
                    delivery_days=item.get('delivery_days'),
                    is_active=True
                )
                db.session.add(listing)
                created += 1

        except Exception as e:
            errors.append(f"Error importing {item.get('name', 'unknown')}: {str(e)}")

    db.session.commit()

    return {
        'message': f'Created {created}, updated {updated} listings',
        'created': created,
        'updated': updated,
        'errors': errors if errors else None
    }
