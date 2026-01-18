"""
Inventory API - telefoni i rezervni delovi na lageru.

Endpointi za upravljanje inventarom telefona i rezervnih delova.
"""

from flask import Blueprint, request, jsonify, g

from ..middleware.auth import jwt_required, tenant_required
from ...extensions import db
from ...models import (
    PhoneListing, PhoneCondition,
    SparePart, PartVisibility, PartCategory,
    AuditLog, AuditAction
)

bp = Blueprint('inventory', __name__, url_prefix='/inventory')


# =============================================================================
# TELEFONI
# =============================================================================

@bp.route('/phones', methods=['GET'])
@jwt_required
@tenant_required
def list_phones():
    """
    Lista telefona na lageru.

    Query params:
        - sold: true/false - filtrira prodate/neprodate
        - location_id: filter po lokaciji
        - search: pretraga po modelu, IMEI
        - page, per_page: paginacija
    """
    user = g.current_user
    tenant = g.current_tenant

    allowed_locations = user.get_accessible_location_ids()
    query = PhoneListing.query.filter(
        PhoneListing.tenant_id == tenant.id
    )

    # Filter po lokaciji
    location_id = request.args.get('location_id', type=int)
    if location_id:
        if location_id not in allowed_locations:
            return jsonify({'error': 'Forbidden', 'message': 'Nemate pristup lokaciji'}), 403
        query = query.filter(PhoneListing.location_id == location_id)
    else:
        query = query.filter(
            db.or_(
                PhoneListing.location_id.in_(allowed_locations),
                PhoneListing.location_id.is_(None)
            )
        )

    # Filter sold
    sold = request.args.get('sold')
    if sold is not None:
        query = query.filter(PhoneListing.sold == (sold.lower() == 'true'))

    # Pretraga
    search = request.args.get('search', '').strip()
    if search:
        search_filter = f'%{search}%'
        query = query.filter(
            db.or_(
                PhoneListing.brand.ilike(search_filter),
                PhoneListing.model.ilike(search_filter),
                PhoneListing.imei.ilike(search_filter)
            )
        )

    # Paginacija
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)

    query = query.order_by(PhoneListing.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'items': [p.to_dict() for p in pagination.items],
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
        'pages': pagination.pages
    }), 200


@bp.route('/phones', methods=['POST'])
@jwt_required
@tenant_required
def create_phone():
    """
    Dodaje telefon na lager.

    Request body:
        - brand: Marka (obavezno)
        - model: Model (obavezno)
        - imei, color, capacity, condition, description
        - purchase_price, purchase_currency
        - sales_price, sales_currency
        - supplier_name, supplier_contact
        - location_id
    """
    user = g.current_user
    tenant = g.current_tenant
    data = request.get_json()

    brand = data.get('brand', '').strip()
    model = data.get('model', '').strip()
    if not brand or not model:
        return jsonify({'error': 'Validation Error', 'message': 'brand i model su obavezni'}), 400

    phone = PhoneListing(
        tenant_id=tenant.id,
        location_id=data.get('location_id'),
        brand=brand,
        model=model,
        imei=data.get('imei'),
        color=data.get('color'),
        capacity=data.get('capacity'),
        description=data.get('description'),
        purchase_price=data.get('purchase_price'),
        purchase_currency=data.get('purchase_currency', 'RSD'),
        sales_price=data.get('sales_price'),
        sales_currency=data.get('sales_currency', 'RSD'),
        supplier_name=data.get('supplier_name'),
        supplier_contact=data.get('supplier_contact'),
    )

    # Stanje
    condition = data.get('condition', 'GOOD')
    try:
        phone.condition = PhoneCondition(condition)
    except ValueError:
        phone.condition = PhoneCondition.GOOD

    db.session.add(phone)

    AuditLog.log_create(
        entity_type='phone',
        entity_id=phone.id,
        data={'brand': brand, 'model': model},
        tenant_id=tenant.id,
        user=user
    )

    db.session.commit()

    return jsonify(phone.to_dict()), 201


@bp.route('/phones/<int:phone_id>', methods=['GET'])
@jwt_required
@tenant_required
def get_phone(phone_id):
    """Dohvata jedan telefon."""
    tenant = g.current_tenant

    phone = PhoneListing.query.filter_by(
        id=phone_id,
        tenant_id=tenant.id
    ).first()

    if not phone:
        return jsonify({'error': 'Not Found', 'message': 'Telefon nije pronadjen'}), 404

    return jsonify(phone.to_dict()), 200


@bp.route('/phones/<int:phone_id>', methods=['PUT'])
@jwt_required
@tenant_required
def update_phone(phone_id):
    """Azurira podatke telefona."""
    user = g.current_user
    tenant = g.current_tenant
    data = request.get_json()

    phone = PhoneListing.query.filter_by(
        id=phone_id,
        tenant_id=tenant.id
    ).first()

    if not phone:
        return jsonify({'error': 'Not Found', 'message': 'Telefon nije pronadjen'}), 404

    # Azuriraj polja
    updatable = [
        'brand', 'model', 'imei', 'color', 'capacity', 'description',
        'purchase_price', 'purchase_currency', 'sales_price', 'sales_currency',
        'supplier_name', 'supplier_contact', 'location_id'
    ]

    for field in updatable:
        if field in data:
            setattr(phone, field, data[field])

    if 'condition' in data:
        try:
            phone.condition = PhoneCondition(data['condition'])
        except ValueError:
            pass

    AuditLog.log_update(
        entity_type='phone',
        entity_id=phone.id,
        changes={'updated': True},
        tenant_id=tenant.id,
        user=user
    )

    db.session.commit()

    return jsonify(phone.to_dict()), 200


@bp.route('/phones/<int:phone_id>/sell', methods=['POST'])
@jwt_required
@tenant_required
def sell_phone(phone_id):
    """
    Oznacava telefon kao prodat.

    Request body:
        - buyer_name: Ime kupca
        - sales_price: Prodajna cena (opciono)
    """
    user = g.current_user
    tenant = g.current_tenant
    data = request.get_json() or {}

    phone = PhoneListing.query.filter_by(
        id=phone_id,
        tenant_id=tenant.id
    ).first()

    if not phone:
        return jsonify({'error': 'Not Found', 'message': 'Telefon nije pronadjen'}), 404

    if phone.sold:
        return jsonify({'error': 'Bad Request', 'message': 'Telefon je vec prodat'}), 400

    phone.mark_as_sold(
        buyer_name=data.get('buyer_name'),
        price=data.get('sales_price')
    )

    AuditLog.log(
        entity_type='phone',
        entity_id=phone.id,
        action=AuditAction.UPDATE,
        changes={'sold': {'old': False, 'new': True}},
        tenant_id=tenant.id,
        user=user
    )

    db.session.commit()

    return jsonify(phone.to_dict()), 200


@bp.route('/phones/<int:phone_id>/collect', methods=['POST'])
@jwt_required
@tenant_required
def collect_phone(phone_id):
    """Oznacava telefon kao naplacen."""
    user = g.current_user
    tenant = g.current_tenant

    phone = PhoneListing.query.filter_by(
        id=phone_id,
        tenant_id=tenant.id
    ).first()

    if not phone:
        return jsonify({'error': 'Not Found', 'message': 'Telefon nije pronadjen'}), 404

    if not phone.sold:
        return jsonify({'error': 'Bad Request', 'message': 'Telefon nije prodat'}), 400

    if phone.collected:
        return jsonify({'error': 'Bad Request', 'message': 'Telefon je vec naplacen'}), 400

    phone.mark_as_collected()

    AuditLog.log(
        entity_type='phone',
        entity_id=phone.id,
        action=AuditAction.UPDATE,
        changes={'collected': {'old': False, 'new': True}},
        tenant_id=tenant.id,
        user=user
    )

    db.session.commit()

    return jsonify(phone.to_dict()), 200


# =============================================================================
# REZERVNI DELOVI
# =============================================================================

@bp.route('/parts', methods=['GET'])
@jwt_required
@tenant_required
def list_parts():
    """
    Lista rezervnih delova.

    Query params:
        - visibility: PRIVATE/PARTNER/PUBLIC
        - category: filter po kategoriji
        - brand, model: filter po uredjaju
        - low_stock: true - samo delovi ispod minimalnog nivoa
        - search: pretraga
        - page, per_page
    """
    user = g.current_user
    tenant = g.current_tenant

    query = SparePart.query.filter(
        SparePart.tenant_id == tenant.id,
        SparePart.is_active == True
    )

    # Filter visibility
    visibility = request.args.get('visibility')
    if visibility:
        try:
            vis_enum = PartVisibility(visibility)
            query = query.filter(SparePart.visibility == vis_enum)
        except ValueError:
            pass

    # Filter category
    category = request.args.get('category')
    if category:
        try:
            cat_enum = PartCategory(category)
            query = query.filter(SparePart.part_category == cat_enum)
        except ValueError:
            pass

    # Filter brand/model
    brand = request.args.get('brand')
    if brand:
        query = query.filter(SparePart.brand.ilike(f'%{brand}%'))

    model = request.args.get('model')
    if model:
        query = query.filter(SparePart.model.ilike(f'%{model}%'))

    # Low stock
    low_stock = request.args.get('low_stock')
    if low_stock and low_stock.lower() == 'true':
        query = query.filter(SparePart.quantity <= SparePart.min_stock_level)

    # Pretraga
    search = request.args.get('search', '').strip()
    if search:
        search_filter = f'%{search}%'
        query = query.filter(
            db.or_(
                SparePart.part_name.ilike(search_filter),
                SparePart.part_number.ilike(search_filter),
                SparePart.brand.ilike(search_filter),
                SparePart.model.ilike(search_filter)
            )
        )

    # Paginacija
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)

    query = query.order_by(SparePart.updated_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'items': [p.to_dict() for p in pagination.items],
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
        'pages': pagination.pages
    }), 200


@bp.route('/parts', methods=['POST'])
@jwt_required
@tenant_required
def create_part():
    """
    Dodaje rezervni deo na lager.

    Request body:
        - part_name: Naziv dela (obavezno)
        - brand, model, part_category, part_number
        - quantity, min_stock_level
        - purchase_price, selling_price, public_price, currency
        - visibility: PRIVATE/PARTNER/PUBLIC
        - is_original, quality_grade
        - location_id
    """
    user = g.current_user
    tenant = g.current_tenant
    data = request.get_json()

    part_name = data.get('part_name', '').strip()
    if not part_name:
        return jsonify({'error': 'Validation Error', 'message': 'part_name je obavezan'}), 400

    part = SparePart(
        tenant_id=tenant.id,
        location_id=data.get('location_id'),
        part_name=part_name,
        brand=data.get('brand'),
        model=data.get('model'),
        part_number=data.get('part_number'),
        description=data.get('description'),
        is_original=data.get('is_original', False),
        quality_grade=data.get('quality_grade'),
        quantity=data.get('quantity', 0),
        min_stock_level=data.get('min_stock_level', 0),
        purchase_price=data.get('purchase_price'),
        selling_price=data.get('selling_price'),
        public_price=data.get('public_price'),
        currency=data.get('currency', 'RSD'),
    )

    # Kategorija
    category = data.get('part_category', 'OTHER')
    try:
        part.part_category = PartCategory(category)
    except ValueError:
        part.part_category = PartCategory.OTHER

    # Visibility
    visibility = data.get('visibility', 'PRIVATE')
    try:
        part.visibility = PartVisibility(visibility)
    except ValueError:
        part.visibility = PartVisibility.PRIVATE

    db.session.add(part)

    AuditLog.log_create(
        entity_type='spare_part',
        entity_id=part.id,
        data={'part_name': part_name, 'quantity': part.quantity},
        tenant_id=tenant.id,
        user=user
    )

    db.session.commit()

    return jsonify(part.to_dict()), 201


@bp.route('/parts/<int:part_id>', methods=['GET'])
@jwt_required
@tenant_required
def get_part(part_id):
    """Dohvata jedan rezervni deo."""
    tenant = g.current_tenant

    part = SparePart.query.filter_by(
        id=part_id,
        tenant_id=tenant.id
    ).first()

    if not part:
        return jsonify({'error': 'Not Found', 'message': 'Deo nije pronadjen'}), 404

    return jsonify(part.to_dict()), 200


@bp.route('/parts/<int:part_id>', methods=['PUT'])
@jwt_required
@tenant_required
def update_part(part_id):
    """Azurira rezervni deo."""
    user = g.current_user
    tenant = g.current_tenant
    data = request.get_json()

    part = SparePart.query.filter_by(
        id=part_id,
        tenant_id=tenant.id
    ).first()

    if not part:
        return jsonify({'error': 'Not Found', 'message': 'Deo nije pronadjen'}), 404

    # Azuriraj polja
    updatable = [
        'part_name', 'brand', 'model', 'part_number', 'description',
        'is_original', 'quality_grade', 'quantity', 'min_stock_level',
        'purchase_price', 'selling_price', 'public_price', 'currency',
        'location_id', 'is_active'
    ]

    for field in updatable:
        if field in data:
            setattr(part, field, data[field])

    if 'part_category' in data:
        try:
            part.part_category = PartCategory(data['part_category'])
        except ValueError:
            pass

    if 'visibility' in data:
        try:
            part.visibility = PartVisibility(data['visibility'])
        except ValueError:
            pass

    AuditLog.log_update(
        entity_type='spare_part',
        entity_id=part.id,
        changes={'updated': True},
        tenant_id=tenant.id,
        user=user
    )

    db.session.commit()

    return jsonify(part.to_dict()), 200


@bp.route('/parts/<int:part_id>/adjust', methods=['POST'])
@jwt_required
@tenant_required
def adjust_part_quantity(part_id):
    """
    Prilagodjava kolicinu dela.

    Request body:
        - delta: Promena kolicine (pozitivno = dodaj, negativno = oduzmi)
        - reason: Razlog promene (opciono)
    """
    user = g.current_user
    tenant = g.current_tenant
    data = request.get_json()

    part = SparePart.query.filter_by(
        id=part_id,
        tenant_id=tenant.id
    ).first()

    if not part:
        return jsonify({'error': 'Not Found', 'message': 'Deo nije pronadjen'}), 404

    delta = data.get('delta', 0)
    if not isinstance(delta, int):
        return jsonify({'error': 'Validation Error', 'message': 'delta mora biti ceo broj'}), 400

    old_qty = part.quantity

    if not part.adjust_quantity(delta):
        return jsonify({'error': 'Bad Request', 'message': 'Nema dovoljno na stanju'}), 400

    AuditLog.log_update(
        entity_type='spare_part',
        entity_id=part.id,
        changes={
            'quantity': {'old': old_qty, 'new': part.quantity},
            'reason': data.get('reason', 'manual adjustment')
        },
        tenant_id=tenant.id,
        user=user
    )

    db.session.commit()

    return jsonify(part.to_dict()), 200


# =============================================================================
# STATISTIKA
# =============================================================================

@bp.route('/phones/stats/trend', methods=['GET'])
@jwt_required
@tenant_required
def get_phone_trend():
    """
    Trend statistike telefona za dashboard grafike (30 dana).

    Vraca dnevne podatke za:
    - added: Broj dodanih telefona
    - sold: Broj prodatih telefona
    - revenue: Ukupna zarada od prodaje

    Query params:
        - days: Broj dana unazad (default 30, max 90)
        - location_id: Filter po lokaciji (opciono)

    Returns:
        200: Trend podaci
    """
    from datetime import date, timedelta

    user = g.current_user
    tenant = g.current_tenant

    # Dozvoljene lokacije
    allowed_locations = user.get_accessible_location_ids()
    location_id = request.args.get('location_id', type=int)

    if location_id:
        if location_id not in allowed_locations:
            return jsonify({'error': 'Forbidden', 'message': 'Nemate pristup ovoj lokaciji'}), 403
        location_filter = [location_id]
    else:
        location_filter = allowed_locations

    # Broj dana
    days = min(request.args.get('days', 30, type=int), 90)

    # Datumi
    today = date.today()
    start_date = today - timedelta(days=days - 1)

    # Bazni query
    base_query = PhoneListing.query.filter(
        PhoneListing.tenant_id == tenant.id,
        db.or_(
            PhoneListing.location_id.in_(location_filter),
            PhoneListing.location_id.is_(None)
        )
    )

    # Dohvati sve telefone u periodu
    phones = base_query.filter(
        db.or_(
            db.func.date(PhoneListing.created_at) >= start_date,
            db.func.date(PhoneListing.sold_at) >= start_date
        )
    ).all()

    # Grupisanje po datumu
    dates = []
    added = []
    sold = []
    revenue = []

    for i in range(days):
        day = start_date + timedelta(days=i)
        dates.append(day.strftime('%d.%m'))

        # Dodati tog dana
        added_count = sum(1 for p in phones
            if p.created_at and p.created_at.date() == day)
        added.append(added_count)

        # Prodati tog dana
        sold_phones = [p for p in phones
            if p.sold_at and p.sold_at.date() == day]
        sold.append(len(sold_phones))

        # Zarada tog dana
        day_revenue = sum(float(p.selling_price or 0) - float(p.purchase_price or 0)
            for p in sold_phones)
        revenue.append(round(day_revenue, 2))

    return jsonify({
        'dates': dates,
        'added': added,
        'sold': sold,
        'revenue': revenue
    }), 200
