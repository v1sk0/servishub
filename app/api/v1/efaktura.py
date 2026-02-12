"""
eFaktura XML Import API — parsiranje i uvoz ulaznih faktura.
"""

from decimal import Decimal
from flask import Blueprint, request, g
from app.extensions import db
from app.models.goods import (
    GoodsItem, PurchaseInvoice, PurchaseInvoiceItem,
    InvoiceStatus, suggest_selling_price
)
from app.models.feature_flag import is_feature_enabled
from app.api.middleware.auth import jwt_required
from app.services.efaktura_parser import parse_efaktura_xml

bp = Blueprint('efaktura', __name__, url_prefix='/goods/invoices/efaktura')

DEFAULT_MARGIN_PCT = 40


def _check_pos_enabled():
    if not is_feature_enabled('pos_enabled', g.tenant_id):
        return {'error': 'POS modul nije aktiviran'}, 403
    return None


@bp.route('/parse', methods=['POST'])
@jwt_required
def parse_xml():
    """Upload eFaktura XML, parse and return preview with item matching."""
    check = _check_pos_enabled()
    if check:
        return check

    if 'file' not in request.files:
        return {'error': 'Fajl nije prosleđen'}, 400

    file = request.files['file']
    if not file.filename:
        return {'error': 'Prazan filename'}, 400

    file_content = file.read()

    if len(file_content) > 5 * 1024 * 1024:
        return {'error': 'Fajl je prevelik (max 5MB)'}, 413

    if not file.filename.lower().endswith('.xml'):
        return {'error': 'Dozvoljeni su samo XML fajlovi'}, 400

    try:
        parsed = parse_efaktura_xml(file_content)
    except ValueError as e:
        return {'error': str(e)}, 400

    # Check for duplicate invoice
    duplicate_warning = None
    existing_inv = PurchaseInvoice.query.filter_by(
        tenant_id=g.tenant_id,
        invoice_number=parsed['invoice_number']
    ).first()
    if existing_inv:
        duplicate_warning = f'Faktura {parsed["invoice_number"]} je već uvezena ({existing_inv.status.value})'

    # Match items against existing GoodsItem records
    preview_items = []
    new_count = 0
    update_count = 0

    for idx, item in enumerate(parsed['items']):
        existing = None

        # Primary match: by SKU (supplier_code)
        if item['supplier_code']:
            existing = GoodsItem.query.filter_by(
                tenant_id=g.tenant_id,
                sku=item['supplier_code']
            ).first()

        # Secondary match: by exact name
        if not existing:
            existing = GoodsItem.query.filter_by(
                tenant_id=g.tenant_id
            ).filter(
                db.func.lower(GoodsItem.name) == item['name'].lower()
            ).first()

        purchase_price = float(item['unit_price'])
        tax_pct = float(item['tax_percent'])
        purchase_with_vat = purchase_price * (1 + tax_pct / 100)

        if existing:
            update_count += 1
            match_status = 'UPDATE'
            suggested_price = float(existing.selling_price or 0)
            if suggested_price > 0 and purchase_with_vat > 0:
                suggested_margin = ((suggested_price - purchase_with_vat) / purchase_with_vat) * 100
            else:
                suggested_margin = DEFAULT_MARGIN_PCT
            existing_data = {
                'id': existing.id,
                'name': existing.name,
                'selling_price': float(existing.selling_price or 0),
                'current_stock': existing.current_stock,
            }
        else:
            new_count += 1
            match_status = 'NEW'
            suggested_price = suggest_selling_price(purchase_with_vat, DEFAULT_MARGIN_PCT)
            suggested_margin = DEFAULT_MARGIN_PCT
            existing_data = None

        preview_items.append({
            'index': idx,
            'name': item['name'],
            'supplier_code': item['supplier_code'],
            'quantity': item['quantity'],
            'purchase_price': purchase_price,
            'tax_percent': tax_pct,
            'line_total': float(item['line_total']),
            'match_status': match_status,
            'existing_item': existing_data,
            'suggested_selling_price': float(suggested_price),
            'suggested_margin_pct': round(float(suggested_margin), 1),
        })

    return {
        'supplier': {
            'name': parsed['supplier_name'],
            'pib': parsed['supplier_pib'],
        },
        'invoice': {
            'number': parsed['invoice_number'],
            'date': parsed['invoice_date'],
            'due_date': parsed.get('due_date'),
            'efaktura_id': parsed.get('efaktura_id'),
        },
        'items': preview_items,
        'summary': {
            'total_items': len(preview_items),
            'new_items': new_count,
            'update_items': update_count,
            'total_without_vat': float(parsed['total_without_vat']),
            'total_with_vat': float(parsed['total_with_vat']),
        },
        'duplicate_warning': duplicate_warning,
    }, 200


@bp.route('/confirm', methods=['POST'])
@jwt_required
def confirm_import():
    """Confirm eFaktura import — create invoice, items, update stock."""
    check = _check_pos_enabled()
    if check:
        return check

    data = request.get_json() or {}

    supplier_name = data.get('supplier_name')
    invoice_number = data.get('invoice_number')
    invoice_date = data.get('invoice_date')
    items = data.get('items', [])

    if not supplier_name or not invoice_number or not items:
        return {'error': 'supplier_name, invoice_number i items su obavezni'}, 400

    try:
        # Create invoice as RECEIVED directly
        invoice = PurchaseInvoice(
            tenant_id=g.tenant_id,
            supplier_name=supplier_name,
            supplier_pib=data.get('supplier_pib', ''),
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            status=InvoiceStatus.RECEIVED,
            received_by_id=g.user_id,
            notes=f'eFaktura import',
            currency='RSD',
        )
        db.session.add(invoice)
        db.session.flush()

        new_count = 0
        update_count = 0
        total_amount = Decimal('0')

        for item_data in items:
            name = item_data.get('name', '')
            supplier_code = item_data.get('supplier_code', '')
            quantity = int(item_data.get('quantity', 1))
            purchase_price = Decimal(str(item_data.get('purchase_price', 0)))
            selling_price = Decimal(str(item_data.get('selling_price', 0)))
            existing_item_id = item_data.get('existing_item_id')

            line_total = purchase_price * quantity
            total_amount += line_total

            if existing_item_id:
                # Update existing item
                goods_item = GoodsItem.query.filter_by(
                    id=existing_item_id, tenant_id=g.tenant_id
                ).first()
                if goods_item:
                    goods_item.purchase_price = purchase_price
                    goods_item.selling_price = selling_price
                    goods_item.current_stock += quantity
                    if supplier_code and not goods_item.sku:
                        goods_item.sku = supplier_code
                    update_count += 1
            else:
                # Create new item
                goods_item = GoodsItem(
                    tenant_id=g.tenant_id,
                    name=name,
                    sku=supplier_code or None,
                    category=item_data.get('category', ''),
                    purchase_price=purchase_price,
                    selling_price=selling_price,
                    current_stock=quantity,
                    min_stock_level=0,
                    tax_label='A',
                    unit_of_measure='kom',
                    currency='RSD',
                    is_active=True,
                )
                db.session.add(goods_item)
                db.session.flush()
                new_count += 1

            # Create invoice item
            inv_item = PurchaseInvoiceItem(
                invoice_id=invoice.id,
                goods_item_id=goods_item.id if goods_item else None,
                item_name=name,
                quantity=quantity,
                purchase_price=purchase_price,
                selling_price=selling_price,
                line_total=line_total,
            )
            db.session.add(inv_item)

        invoice.total_amount = total_amount
        db.session.commit()

        return {
            'message': f'Uvezeno {new_count} novih, ažurirano {update_count} postojećih artikala',
            'invoice_id': invoice.id,
            'new_items': new_count,
            'updated_items': update_count,
        }, 201

    except Exception as e:
        db.session.rollback()
        return {'error': f'Greška pri uvozu: {str(e)}'}, 500
