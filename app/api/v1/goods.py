"""
Goods API — artikli robe, ulazne fakture, stock korekcije.
"""

from flask import Blueprint, request, g
from app.extensions import db
from app.models.goods import (
    GoodsItem, PurchaseInvoice, PurchaseInvoiceItem,
    StockAdjustment, InvoiceStatus, suggest_selling_price
)
from app.models.feature_flag import is_feature_enabled
from app.api.middleware.auth import jwt_required
from app.services.goods_service import GoodsService

bp = Blueprint('goods', __name__, url_prefix='/goods')


def _check_pos_enabled():
    if not is_feature_enabled('pos_enabled', g.tenant_id):
        return {'error': 'POS modul nije aktiviran'}, 403
    return None


# ============================================
# ARTIKLI
# ============================================

@bp.route('', methods=['GET'])
@jwt_required
def list_goods():
    """Lista artikala robe."""
    check = _check_pos_enabled()
    if check:
        return check

    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 200)
    search = request.args.get('q', '').strip()
    category = request.args.get('category')
    low_stock = request.args.get('low_stock', type=int)
    active_only = request.args.get('active_only', '1') == '1'

    query = GoodsItem.query.filter_by(tenant_id=g.tenant_id)
    if active_only:
        query = query.filter_by(is_active=True)
    if search:
        query = query.filter(
            db.or_(
                GoodsItem.name.ilike(f'%{search}%'),
                GoodsItem.barcode.ilike(f'%{search}%'),
                GoodsItem.sku.ilike(f'%{search}%'),
            )
        )
    if category:
        query = query.filter_by(category=category)
    if low_stock:
        query = query.filter(GoodsItem.current_stock <= GoodsItem.min_stock_level)

    query = query.order_by(GoodsItem.name)
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return {
        'items': [i.to_dict() for i in pagination.items],
        'total': pagination.total,
        'page': page,
        'pages': pagination.pages,
    }, 200


@bp.route('', methods=['POST'])
@jwt_required
def create_goods():
    """Kreiraj novi artikl."""
    check = _check_pos_enabled()
    if check:
        return check

    data = request.get_json() or {}
    if not data.get('name'):
        return {'error': 'Naziv je obavezan'}, 400

    try:
        item = GoodsService.create_goods_item(g.tenant_id, data, g.user_id)
        db.session.commit()
        return {'message': 'Artikl kreiran', 'item': item.to_dict()}, 201
    except Exception as e:
        db.session.rollback()
        return {'error': str(e)}, 400


@bp.route('/<int:item_id>', methods=['GET'])
@jwt_required
def get_goods(item_id):
    """Detalji artikla."""
    check = _check_pos_enabled()
    if check:
        return check

    item = GoodsItem.query.filter_by(id=item_id, tenant_id=g.tenant_id).first()
    if not item:
        return {'error': 'Artikl nije pronađen'}, 404
    return {'item': item.to_dict()}, 200


@bp.route('/<int:item_id>', methods=['PUT'])
@jwt_required
def update_goods(item_id):
    """Ažuriraj artikl."""
    check = _check_pos_enabled()
    if check:
        return check

    data = request.get_json() or {}
    try:
        item = GoodsService.update_goods_item(item_id, g.tenant_id, data)
        db.session.commit()
        return {'message': 'Artikl ažuriran', 'item': item.to_dict()}, 200
    except ValueError as e:
        return {'error': str(e)}, 400


@bp.route('/<int:item_id>/adjust', methods=['POST'])
@jwt_required
def adjust_stock(item_id):
    """Korekcija stanja (otpis, inventura, oštećenje)."""
    check = _check_pos_enabled()
    if check:
        return check

    data = request.get_json() or {}
    quantity_change = data.get('quantity_change')
    adjustment_type = data.get('adjustment_type')
    reason = data.get('reason', '')

    if quantity_change is None or not adjustment_type:
        return {'error': 'quantity_change i adjustment_type su obavezni'}, 400

    try:
        adj = GoodsService.adjust_goods_stock(
            item_id, g.tenant_id, quantity_change, adjustment_type, reason, g.user_id
        )
        db.session.commit()
        return {
            'message': 'Stanje korigovano',
            'stock_before': adj.stock_before,
            'stock_after': adj.stock_after,
        }, 200
    except ValueError as e:
        db.session.rollback()
        return {'error': str(e)}, 400


@bp.route('/suggest-price', methods=['GET'])
@jwt_required
def get_suggested_price():
    """Predloži prodajnu cenu na osnovu nabavne i marže."""
    check = _check_pos_enabled()
    if check:
        return check

    purchase_price = request.args.get('purchase_price', type=float)
    margin_pct = request.args.get('margin_pct', type=float)
    if purchase_price is None or margin_pct is None:
        return {'error': 'purchase_price i margin_pct su obavezni'}, 400

    suggested = suggest_selling_price(purchase_price, margin_pct)
    return {'suggested_price': suggested}, 200


@bp.route('/categories', methods=['GET'])
@jwt_required
def list_categories():
    """Lista kategorija artikala."""
    check = _check_pos_enabled()
    if check:
        return check

    categories = db.session.query(GoodsItem.category).filter(
        GoodsItem.tenant_id == g.tenant_id,
        GoodsItem.category.isnot(None),
        GoodsItem.is_active == True
    ).distinct().all()

    return {'categories': [c[0] for c in categories if c[0]]}, 200


# ============================================
# ULAZNE FAKTURE
# ============================================

@bp.route('/invoices', methods=['GET'])
@jwt_required
def list_invoices():
    """Lista ulaznih faktura."""
    check = _check_pos_enabled()
    if check:
        return check

    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)

    query = PurchaseInvoice.query.filter_by(tenant_id=g.tenant_id)
    query = query.order_by(PurchaseInvoice.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return {
        'invoices': [{
            'id': inv.id,
            'supplier_name': inv.supplier_name,
            'invoice_number': inv.invoice_number,
            'invoice_date': str(inv.invoice_date) if inv.invoice_date else None,
            'total_amount': float(inv.total_amount or 0),
            'status': inv.status.value,
            'created_at': inv.created_at.isoformat(),
        } for inv in pagination.items],
        'total': pagination.total,
        'page': page,
        'pages': pagination.pages,
    }, 200


@bp.route('/invoices', methods=['POST'])
@jwt_required
def create_invoice():
    """Kreiraj ulaznu fakturu."""
    check = _check_pos_enabled()
    if check:
        return check

    data = request.get_json() or {}
    required = ['supplier_name', 'invoice_number', 'invoice_date']
    for field in required:
        if not data.get(field):
            return {'error': f'{field} je obavezan'}, 400

    try:
        invoice = GoodsService.create_invoice(g.tenant_id, data, g.user_id)
        db.session.commit()
        return {'message': 'Faktura kreirana', 'invoice_id': invoice.id}, 201
    except Exception as e:
        db.session.rollback()
        return {'error': str(e)}, 400


@bp.route('/invoices/<int:invoice_id>/items', methods=['POST'])
@jwt_required
def add_invoice_item(invoice_id):
    """Dodaj stavku na fakturu."""
    check = _check_pos_enabled()
    if check:
        return check

    data = request.get_json() or {}
    if not data.get('item_name') or not data.get('purchase_price'):
        return {'error': 'item_name i purchase_price su obavezni'}, 400

    try:
        item = GoodsService.add_invoice_item(invoice_id, data)
        db.session.commit()
        return {
            'message': 'Stavka dodata',
            'item_id': item.id,
            'line_total': float(item.line_total),
        }, 201
    except ValueError as e:
        db.session.rollback()
        return {'error': str(e)}, 400


@bp.route('/invoices/<int:invoice_id>/receive', methods=['POST'])
@jwt_required
def receive_invoice(invoice_id):
    """Primi fakturu — ažuriraj stanje."""
    check = _check_pos_enabled()
    if check:
        return check

    try:
        invoice = GoodsService.receive_invoice(invoice_id, g.tenant_id, g.user_id)
        db.session.commit()
        return {'message': 'Faktura primljena', 'status': invoice.status.value}, 200
    except ValueError as e:
        db.session.rollback()
        return {'error': str(e)}, 400