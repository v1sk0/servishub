"""
POS API - kasa endpoint-i.

Svi endpointi zahtevaju JWT i location scoping.
"""

import csv
import io
from datetime import datetime, date
from flask import Blueprint, request, g, Response
from app.extensions import db
from app.models.pos import (
    CashRegisterSession, Receipt, ReceiptItem, DailyReport,
    CashRegisterStatus, ReceiptStatus, ReceiptType
)
from app.models.feature_flag import is_feature_enabled
from app.api.middleware.auth import jwt_required
from app.services.pos_service import POSService
from sqlalchemy import func

bp = Blueprint('pos', __name__, url_prefix='/pos')


def _check_pos_enabled():
    if not is_feature_enabled('pos_enabled', g.tenant_id):
        return {'error': 'POS modul nije aktiviran'}, 403
    return None


# ============================================
# KASA SESIJE
# ============================================

@bp.route('/register/open', methods=['POST'])
@jwt_required
def open_register():
    """Otvori kasu za trenutnu lokaciju."""
    check = _check_pos_enabled()
    if check:
        return check

    data = request.get_json() or {}
    opening_cash = data.get('opening_cash', 0)
    location_id = getattr(g, 'current_location_id', None) or data.get('location_id')

    if not location_id:
        return {'error': 'location_id je obavezan'}, 400

    try:
        session = POSService.open_register(g.tenant_id, location_id, g.user_id, opening_cash)
        db.session.commit()
        return {
            'message': 'Kasa otvorena',
            'session_id': session.id,
            'date': str(session.date),
            'opening_cash': float(session.opening_cash),
        }, 201
    except ValueError as e:
        return {'error': str(e)}, 400


@bp.route('/register/close', methods=['POST'])
@jwt_required
def close_register():
    """Zatvori kasu."""
    check = _check_pos_enabled()
    if check:
        return check

    data = request.get_json() or {}
    closing_cash = data.get('closing_cash')
    if closing_cash is None:
        return {'error': 'closing_cash je obavezan'}, 400

    session_id = data.get('session_id')
    if not session_id:
        # Pronađi otvorenu sesiju
        location_id = getattr(g, 'current_location_id', None) or data.get('location_id')
        session = CashRegisterSession.query.filter_by(
            tenant_id=g.tenant_id,
            location_id=location_id,
            date=date.today(),
            status=CashRegisterStatus.OPEN
        ).first()
        if not session:
            return {'error': 'Nema otvorene kase'}, 404
        session_id = session.id

    try:
        session, report = POSService.close_register(session_id, g.user_id, closing_cash)
        db.session.commit()
        return {
            'message': 'Kasa zatvorena',
            'session_id': session.id,
            'closing_cash': float(session.closing_cash),
            'expected_cash': float(session.expected_cash),
            'cash_difference': float(session.cash_difference),
            'total_revenue': float(session.total_revenue),
            'receipt_count': session.receipt_count,
            'report_id': report.id,
        }, 200
    except ValueError as e:
        return {'error': str(e)}, 400


@bp.route('/register/current', methods=['GET'])
@jwt_required
def current_register():
    """Trenutna otvorena sesija."""
    check = _check_pos_enabled()
    if check:
        return check

    location_id = request.args.get('location_id') or getattr(g, 'current_location_id', None)
    session = CashRegisterSession.query.filter_by(
        tenant_id=g.tenant_id,
        location_id=location_id,
        date=date.today(),
        status=CashRegisterStatus.OPEN
    ).first()

    if not session:
        return {'error': 'Nema otvorene kase'}, 404

    return {
        'session_id': session.id,
        'date': str(session.date),
        'location_id': session.location_id,
        'opening_cash': float(session.opening_cash),
        'opened_at': session.opened_at.isoformat() if session.opened_at else None,
        'receipt_count': session.receipt_count,
        'total_revenue': float(session.total_revenue),
    }, 200


# ============================================
# RAČUNI
# ============================================

@bp.route('/receipts', methods=['POST'])
@jwt_required
def create_receipt():
    """Kreiraj prazan DRAFT račun."""
    check = _check_pos_enabled()
    if check:
        return check

    data = request.get_json() or {}
    session_id = data.get('session_id')

    if not session_id:
        location_id = getattr(g, 'current_location_id', None) or data.get('location_id')
        session = CashRegisterSession.query.filter_by(
            tenant_id=g.tenant_id,
            location_id=location_id,
            date=date.today(),
            status=CashRegisterStatus.OPEN
        ).first()
        if not session:
            return {'error': 'Nema otvorene kase'}, 400
        session_id = session.id

    try:
        receipt = POSService.create_receipt(session_id, g.user_id)
        db.session.commit()
        return {
            'receipt_id': receipt.id,
            'receipt_number': receipt.receipt_number,
            'status': receipt.status.value,
        }, 201
    except ValueError as e:
        return {'error': str(e)}, 400


@bp.route('/receipts/<int:receipt_id>', methods=['GET'])
@jwt_required
def get_receipt(receipt_id):
    """Detalji računa sa stavkama."""
    check = _check_pos_enabled()
    if check:
        return check

    receipt = Receipt.query.filter_by(id=receipt_id, tenant_id=g.tenant_id).first()
    if not receipt:
        return {'error': 'Račun nije pronađen'}, 404

    items = ReceiptItem.query.filter_by(receipt_id=receipt_id).all()

    return {
        'id': receipt.id,
        'receipt_number': receipt.receipt_number,
        'receipt_type': receipt.receipt_type.value,
        'status': receipt.status.value,
        'customer_name': receipt.customer_name,
        'subtotal': float(receipt.subtotal or 0),
        'discount_amount': float(receipt.discount_amount or 0),
        'total_amount': float(receipt.total_amount or 0),
        'total_cost': float(receipt.total_cost or 0),
        'profit': float(receipt.profit or 0),
        'payment_method': receipt.payment_method.value if receipt.payment_method else None,
        'cash_received': float(receipt.cash_received) if receipt.cash_received else None,
        'cash_change': float(receipt.cash_change) if receipt.cash_change else None,
        'issued_at': receipt.issued_at.isoformat() if receipt.issued_at else None,
        'items': [{
            'id': i.id,
            'item_type': i.item_type.value,
            'item_name': i.item_name,
            'quantity': i.quantity,
            'unit_price': float(i.unit_price),
            'discount_pct': float(i.discount_pct or 0),
            'line_total': float(i.line_total),
            'line_profit': float(i.line_profit),
        } for i in items],
    }, 200


@bp.route('/receipts/<int:receipt_id>/items', methods=['POST'])
@jwt_required
def add_receipt_item(receipt_id):
    """Dodaj stavku na račun."""
    check = _check_pos_enabled()
    if check:
        return check

    receipt = Receipt.query.filter_by(id=receipt_id, tenant_id=g.tenant_id).first()
    if not receipt:
        return {'error': 'Račun nije pronađen'}, 404

    data = request.get_json() or {}
    try:
        item = POSService.add_item_to_receipt(
            receipt_id,
            item_type=data.get('item_type'),
            item_id=data.get('item_id'),
            quantity=data.get('quantity', 1),
            unit_price=data.get('unit_price'),
            purchase_price=data.get('purchase_price'),
            item_name=data.get('item_name'),
            discount_pct=data.get('discount_pct', 0),
        )
        db.session.commit()
        return {
            'message': 'Stavka dodata',
            'item_id': item.id,
            'line_total': float(item.line_total),
        }, 201
    except ValueError as e:
        db.session.rollback()
        return {'error': str(e)}, 400


@bp.route('/receipts/<int:receipt_id>/items/<int:item_id>', methods=['DELETE'])
@jwt_required
def remove_receipt_item(receipt_id, item_id):
    """Ukloni stavku sa računa."""
    check = _check_pos_enabled()
    if check:
        return check

    try:
        POSService.remove_item_from_receipt(item_id)
        db.session.commit()
        return {'message': 'Stavka uklonjena'}, 200
    except ValueError as e:
        db.session.rollback()
        return {'error': str(e)}, 400


@bp.route('/receipts/<int:receipt_id>/issue', methods=['POST'])
@jwt_required
def issue_receipt(receipt_id):
    """Izdaj račun."""
    check = _check_pos_enabled()
    if check:
        return check

    data = request.get_json() or {}
    try:
        receipt = POSService.issue_receipt(
            receipt_id,
            payment_method=data.get('payment_method', 'CASH'),
            cash_received=data.get('cash_received'),
            card_amount=data.get('card_amount'),
            transfer_amount=data.get('transfer_amount'),
        )
        db.session.commit()
        return {
            'message': 'Račun izdat',
            'receipt_number': receipt.receipt_number,
            'total_amount': float(receipt.total_amount),
            'cash_change': float(receipt.cash_change) if receipt.cash_change else None,
        }, 200
    except ValueError as e:
        db.session.rollback()
        return {'error': str(e)}, 400


@bp.route('/receipts/<int:receipt_id>/void', methods=['POST'])
@jwt_required
def void_receipt(receipt_id):
    """Storniraj račun."""
    check = _check_pos_enabled()
    if check:
        return check

    data = request.get_json() or {}
    reason = data.get('reason', '')
    if not reason:
        return {'error': 'Razlog je obavezan'}, 400

    try:
        receipt = POSService.void_receipt(receipt_id, g.user_id, reason)
        db.session.commit()
        return {'message': 'Račun storniran'}, 200
    except ValueError as e:
        return {'error': str(e)}, 400


@bp.route('/receipts/<int:receipt_id>/refund', methods=['POST'])
@jwt_required
def refund_receipt(receipt_id):
    """Refund računa."""
    check = _check_pos_enabled()
    if check:
        return check

    data = request.get_json() or {}
    items_to_refund = data.get('items')

    try:
        refund = POSService.refund_receipt(receipt_id, g.user_id, items_to_refund)
        db.session.commit()
        return {
            'message': 'Refund kreiran',
            'refund_receipt_id': refund.id,
            'refund_number': refund.receipt_number,
        }, 201
    except ValueError as e:
        return {'error': str(e)}, 400


@bp.route('/receipts', methods=['GET'])
@jwt_required
def list_receipts():
    """Lista računa."""
    check = _check_pos_enabled()
    if check:
        return check

    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)
    status_filter = request.args.get('status')
    date_filter = request.args.get('date')
    session_filter = request.args.get('session_id', type=int)

    query = Receipt.query.filter_by(tenant_id=g.tenant_id)
    if status_filter:
        try:
            query = query.filter_by(status=ReceiptStatus(status_filter))
        except ValueError:
            pass
    if date_filter:
        query = query.filter(func.date(Receipt.created_at) == date_filter)
    if session_filter:
        query = query.filter_by(session_id=session_filter)

    query = query.order_by(Receipt.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return {
        'receipts': [{
            'id': r.id,
            'receipt_number': r.receipt_number,
            'receipt_type': r.receipt_type.value,
            'status': r.status.value,
            'total_amount': float(r.total_amount or 0),
            'payment_method': r.payment_method.value if r.payment_method else None,
            'customer_name': r.customer_name,
            'issued_at': r.issued_at.isoformat() if r.issued_at else None,
            'created_at': r.created_at.isoformat(),
        } for r in pagination.items],
        'total': pagination.total,
        'page': page,
        'pages': pagination.pages,
    }, 200


# ============================================
# IZVEŠTAJI
# ============================================

@bp.route('/reports/daily', methods=['GET'])
@jwt_required
def daily_report():
    """Dnevni izveštaj."""
    check = _check_pos_enabled()
    if check:
        return check

    report_date = request.args.get('date', str(date.today()))
    location_id = request.args.get('location_id') or getattr(g, 'current_location_id', None)

    report = DailyReport.query.filter_by(
        tenant_id=g.tenant_id,
        location_id=location_id,
        date=report_date,
    ).first()

    if not report:
        return {'error': 'Izveštaj nije pronađen'}, 404

    return {
        'id': report.id,
        'date': str(report.date),
        'total_revenue': float(report.total_revenue or 0),
        'total_cost': float(report.total_cost or 0),
        'total_profit': float(report.total_profit or 0),
        'profit_margin_pct': float(report.profit_margin_pct or 0),
        'total_cash': float(report.total_cash or 0),
        'total_card': float(report.total_card or 0),
        'total_transfer': float(report.total_transfer or 0),
        'opening_cash': float(report.opening_cash or 0),
        'closing_cash': float(report.closing_cash or 0),
        'cash_difference': float(report.cash_difference or 0),
        'receipt_count': report.receipt_count,
        'voided_count': report.voided_count,
        'items_sold': report.items_sold,
        'phones_sold': report.phones_sold,
        'parts_sold': report.parts_sold,
        'services_sold': report.services_sold,
    }, 200


@bp.route('/reports/range', methods=['GET'])
@jwt_required
def range_report():
    """Period izveštaj."""
    check = _check_pos_enabled()
    if check:
        return check

    date_from = request.args.get('from')
    date_to = request.args.get('to')
    location_id = request.args.get('location_id') or getattr(g, 'current_location_id', None)

    if not date_from or not date_to:
        return {'error': 'from i to su obavezni'}, 400

    reports = DailyReport.query.filter(
        DailyReport.tenant_id == g.tenant_id,
        DailyReport.location_id == location_id,
        DailyReport.date >= date_from,
        DailyReport.date <= date_to,
    ).order_by(DailyReport.date).all()

    total_revenue = sum(float(r.total_revenue or 0) for r in reports)
    total_cost = sum(float(r.total_cost or 0) for r in reports)
    total_profit = sum(float(r.total_profit or 0) for r in reports)

    return {
        'from': date_from,
        'to': date_to,
        'days': len(reports),
        'total_revenue': total_revenue,
        'total_cost': total_cost,
        'total_profit': total_profit,
        'profit_margin_pct': round(total_profit / total_revenue * 100, 2) if total_revenue else 0,
        'total_receipts': sum(r.receipt_count or 0 for r in reports),
        'daily': [{
            'date': str(r.date),
            'revenue': float(r.total_revenue or 0),
            'profit': float(r.total_profit or 0),
            'receipts': r.receipt_count,
        } for r in reports],
    }, 200


@bp.route('/reports/<int:report_id>/export', methods=['GET'])
@jwt_required
def export_report(report_id):
    """CSV export dnevnog izveštaja."""
    check = _check_pos_enabled()
    if check:
        return check

    report = DailyReport.query.filter_by(id=report_id, tenant_id=g.tenant_id).first()
    if not report:
        return {'error': 'Izveštaj nije pronađen'}, 404

    receipts = Receipt.query.filter_by(
        session_id=report.session_id,
        status=ReceiptStatus.ISSUED
    ).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Račun', 'Datum', 'Stavka', 'Količina', 'Nabavna', 'Prodajna', 'Profit', 'Plaćanje'])

    for r in receipts:
        items = ReceiptItem.query.filter_by(receipt_id=r.id).all()
        for item in items:
            writer.writerow([
                r.receipt_number,
                r.issued_at.strftime('%Y-%m-%d %H:%M') if r.issued_at else '',
                item.item_name,
                item.quantity,
                float(item.purchase_price),
                float(item.unit_price),
                float(item.line_profit),
                r.payment_method.value if r.payment_method else '',
            ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=pos_report_{report.date}.csv'}
    )