"""
Supplier Reports API - Izvestaji za dobavljace (Paket C)

Endpoints:
- GET /reports/summary       - Pregled (totals, top articles, top tenants)
- GET /reports/by-article    - Analiza po artiklu
- GET /reports/by-tenant     - Analiza po kupcu
- GET /reports/export        - Export CSV/XLSX
"""
from io import BytesIO, StringIO
import csv
from flask import Blueprint, request, g, send_file
from app.extensions import db
from app.models import (
    PartOrder, PartOrderItem, OrderStatus, SellerType, Tenant
)
from .auth import supplier_jwt_required
from sqlalchemy import func, desc
from datetime import datetime, timedelta
from decimal import Decimal

bp = Blueprint('supplier_reports', __name__, url_prefix='/reports')


# ============== Helpers ==============

def _parse_date_range():
    """Parsira start_date i end_date iz query parametara. Default: poslednjih 30 dana."""
    end_str = request.args.get('end_date')
    start_str = request.args.get('start_date')

    if end_str:
        try:
            end_date = datetime.strptime(end_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        except ValueError:
            end_date = datetime.utcnow()
    else:
        end_date = datetime.utcnow()

    if start_str:
        try:
            start_date = datetime.strptime(start_str, '%Y-%m-%d')
        except ValueError:
            start_date = end_date - timedelta(days=30)
    else:
        start_date = end_date - timedelta(days=30)

    return start_date, end_date


def _base_completed_query(start_date, end_date):
    """Bazni query za completed orders u datom periodu."""
    return PartOrder.query.filter(
        PartOrder.seller_type == SellerType.SUPPLIER,
        PartOrder.seller_supplier_id == g.supplier_id,
        PartOrder.status == OrderStatus.COMPLETED,
        PartOrder.completed_at >= start_date,
        PartOrder.completed_at <= end_date,
    )


# ============== Routes ==============

@bp.route('/summary', methods=['GET'])
@supplier_jwt_required
def get_summary():
    """
    Pregled izvestaj: ukupan broj narudzbina, prihod, provizija,
    top 5 artikala, top 5 kupaca.
    """
    start_date, end_date = _parse_date_range()
    base = _base_completed_query(start_date, end_date)

    # Totals
    totals = db.session.query(
        func.count(PartOrder.id).label('orders_count'),
        func.coalesce(func.sum(PartOrder.subtotal), 0).label('revenue_rsd'),
        func.coalesce(func.sum(PartOrder.commission_amount), 0).label('commission_rsd'),
    ).filter(
        PartOrder.seller_type == SellerType.SUPPLIER,
        PartOrder.seller_supplier_id == g.supplier_id,
        PartOrder.status == OrderStatus.COMPLETED,
        PartOrder.completed_at >= start_date,
        PartOrder.completed_at <= end_date,
    ).first()

    # Top 5 articles
    top_articles = db.session.query(
        PartOrderItem.part_name,
        func.sum(PartOrderItem.quantity).label('qty_sold'),
        func.sum(PartOrderItem.total_price).label('revenue'),
    ).join(
        PartOrder, PartOrderItem.order_id == PartOrder.id
    ).filter(
        PartOrder.seller_type == SellerType.SUPPLIER,
        PartOrder.seller_supplier_id == g.supplier_id,
        PartOrder.status == OrderStatus.COMPLETED,
        PartOrder.completed_at >= start_date,
        PartOrder.completed_at <= end_date,
    ).group_by(
        PartOrderItem.part_name
    ).order_by(
        desc('revenue')
    ).limit(5).all()

    # Top 5 tenants
    top_tenants = db.session.query(
        PartOrder.buyer_tenant_id,
        func.count(PartOrder.id).label('orders_count'),
        func.sum(PartOrder.subtotal).label('total_spent'),
    ).filter(
        PartOrder.seller_type == SellerType.SUPPLIER,
        PartOrder.seller_supplier_id == g.supplier_id,
        PartOrder.status == OrderStatus.COMPLETED,
        PartOrder.completed_at >= start_date,
        PartOrder.completed_at <= end_date,
    ).group_by(
        PartOrder.buyer_tenant_id
    ).order_by(
        desc('total_spent')
    ).limit(5).all()

    # Resolve tenant names
    tenant_results = []
    for t in top_tenants:
        tenant = Tenant.query.get(t.buyer_tenant_id)
        tenant_results.append({
            'tenant_id': t.buyer_tenant_id,
            'name': tenant.name if tenant else 'Unknown',
            'city': tenant.city if tenant else None,
            'orders_count': t.orders_count,
            'total_spent': float(t.total_spent) if t.total_spent else 0,
        })

    return {
        'success': True,
        'period': {
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
        },
        'totals': {
            'orders_count': totals.orders_count if totals else 0,
            'revenue_rsd': float(totals.revenue_rsd) if totals else 0,
            'commission_rsd': float(totals.commission_rsd) if totals else 0,
        },
        'top_articles': [{
            'part_name': a.part_name,
            'quantity_sold': a.qty_sold,
            'revenue_rsd': float(a.revenue) if a.revenue else 0,
        } for a in top_articles],
        'top_tenants': tenant_results,
    }


@bp.route('/by-article', methods=['GET'])
@supplier_jwt_required
def report_by_article():
    """Analiza prodaje po artiklu."""
    start_date, end_date = _parse_date_range()
    category = request.args.get('category')

    query = db.session.query(
        PartOrderItem.part_name,
        PartOrderItem.brand,
        func.sum(PartOrderItem.quantity).label('qty_sold'),
        func.sum(PartOrderItem.total_price).label('revenue'),
        func.avg(PartOrderItem.unit_price).label('avg_price'),
    ).join(
        PartOrder, PartOrderItem.order_id == PartOrder.id
    ).filter(
        PartOrder.seller_type == SellerType.SUPPLIER,
        PartOrder.seller_supplier_id == g.supplier_id,
        PartOrder.status == OrderStatus.COMPLETED,
        PartOrder.completed_at >= start_date,
        PartOrder.completed_at <= end_date,
    )

    if category:
        query = query.filter(PartOrderItem.brand == category)

    articles = query.group_by(
        PartOrderItem.part_name, PartOrderItem.brand
    ).order_by(desc('revenue')).all()

    total_revenue = sum(float(a.revenue or 0) for a in articles)
    total_qty = sum(a.qty_sold or 0 for a in articles)

    return {
        'success': True,
        'period': {
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
        },
        'articles': [{
            'part_name': a.part_name,
            'brand': a.brand,
            'quantity_sold': a.qty_sold,
            'revenue_rsd': float(a.revenue) if a.revenue else 0,
            'avg_unit_price': round(float(a.avg_price), 2) if a.avg_price else 0,
        } for a in articles],
        'totals': {
            'total_revenue': total_revenue,
            'total_quantity': total_qty,
        },
    }


@bp.route('/by-tenant', methods=['GET'])
@supplier_jwt_required
def report_by_tenant():
    """Analiza prodaje po kupcu."""
    start_date, end_date = _parse_date_range()

    tenants_data = db.session.query(
        PartOrder.buyer_tenant_id,
        func.count(PartOrder.id).label('orders_count'),
        func.sum(PartOrder.subtotal).label('total_spent'),
    ).filter(
        PartOrder.seller_type == SellerType.SUPPLIER,
        PartOrder.seller_supplier_id == g.supplier_id,
        PartOrder.status == OrderStatus.COMPLETED,
        PartOrder.completed_at >= start_date,
        PartOrder.completed_at <= end_date,
    ).group_by(
        PartOrder.buyer_tenant_id
    ).order_by(desc('total_spent')).all()

    result = []
    total_revenue = Decimal('0')
    total_orders = 0
    for t in tenants_data:
        tenant = Tenant.query.get(t.buyer_tenant_id)
        spent = t.total_spent or Decimal('0')
        total_revenue += spent
        total_orders += t.orders_count
        result.append({
            'tenant_id': t.buyer_tenant_id,
            'name': tenant.name if tenant else 'Unknown',
            'city': tenant.city if tenant else None,
            'orders_count': t.orders_count,
            'total_spent': float(spent),
        })

    return {
        'success': True,
        'period': {
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
        },
        'tenants': result,
        'totals': {
            'total_revenue': float(total_revenue),
            'total_orders': total_orders,
            'tenant_count': len(result),
        },
    }


@bp.route('/export', methods=['GET'])
@supplier_jwt_required
def export_report():
    """
    Export izvestaja kao CSV ili XLSX.
    ?type=summary|by-article|by-tenant&format=csv|xlsx
    """
    report_type = request.args.get('type', 'summary')
    fmt = request.args.get('format', 'csv')
    start_date, end_date = _parse_date_range()

    if fmt not in ('csv', 'xlsx'):
        return {'error': 'Format mora biti csv ili xlsx'}, 400

    # Get data based on type
    if report_type == 'by-article':
        rows, headers = _get_article_export_data(start_date, end_date)
    elif report_type == 'by-tenant':
        rows, headers = _get_tenant_export_data(start_date, end_date)
    else:
        rows, headers = _get_summary_export_data(start_date, end_date)

    date_suffix = f"{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}"
    filename = f'izvestaj_{report_type}_{date_suffix}'

    if fmt == 'csv':
        return _export_csv(rows, headers, filename)
    else:
        return _export_xlsx(rows, headers, filename)


def _get_article_export_data(start_date, end_date):
    """Priprema podatke za article export."""
    articles = db.session.query(
        PartOrderItem.part_name,
        PartOrderItem.brand,
        func.sum(PartOrderItem.quantity).label('qty'),
        func.sum(PartOrderItem.total_price).label('revenue'),
        func.avg(PartOrderItem.unit_price).label('avg_price'),
    ).join(
        PartOrder, PartOrderItem.order_id == PartOrder.id
    ).filter(
        PartOrder.seller_type == SellerType.SUPPLIER,
        PartOrder.seller_supplier_id == g.supplier_id,
        PartOrder.status == OrderStatus.COMPLETED,
        PartOrder.completed_at >= start_date,
        PartOrder.completed_at <= end_date,
    ).group_by(
        PartOrderItem.part_name, PartOrderItem.brand
    ).order_by(desc('revenue')).all()

    headers = ['Naziv artikla', 'Brend', 'Prodato (kom)', 'Prihod (RSD)', 'Prosecna cena (RSD)']
    rows = []
    for a in articles:
        rows.append([
            a.part_name,
            a.brand or '',
            a.qty or 0,
            float(a.revenue) if a.revenue else 0,
            round(float(a.avg_price), 2) if a.avg_price else 0,
        ])
    return rows, headers


def _get_tenant_export_data(start_date, end_date):
    """Priprema podatke za tenant export."""
    tenants_data = db.session.query(
        PartOrder.buyer_tenant_id,
        func.count(PartOrder.id).label('orders_count'),
        func.sum(PartOrder.subtotal).label('total_spent'),
    ).filter(
        PartOrder.seller_type == SellerType.SUPPLIER,
        PartOrder.seller_supplier_id == g.supplier_id,
        PartOrder.status == OrderStatus.COMPLETED,
        PartOrder.completed_at >= start_date,
        PartOrder.completed_at <= end_date,
    ).group_by(
        PartOrder.buyer_tenant_id
    ).order_by(desc('total_spent')).all()

    headers = ['Kupac', 'Grad', 'Broj narudzbina', 'Ukupna potrosnja (RSD)']
    rows = []
    for t in tenants_data:
        tenant = Tenant.query.get(t.buyer_tenant_id)
        rows.append([
            tenant.name if tenant else 'Unknown',
            tenant.city if tenant else '',
            t.orders_count,
            float(t.total_spent) if t.total_spent else 0,
        ])
    return rows, headers


def _get_summary_export_data(start_date, end_date):
    """Priprema podatke za summary export."""
    totals = db.session.query(
        func.count(PartOrder.id).label('orders_count'),
        func.coalesce(func.sum(PartOrder.subtotal), 0).label('revenue'),
        func.coalesce(func.sum(PartOrder.commission_amount), 0).label('commission'),
    ).filter(
        PartOrder.seller_type == SellerType.SUPPLIER,
        PartOrder.seller_supplier_id == g.supplier_id,
        PartOrder.status == OrderStatus.COMPLETED,
        PartOrder.completed_at >= start_date,
        PartOrder.completed_at <= end_date,
    ).first()

    headers = ['Metrika', 'Vrednost']
    rows = [
        ['Period', f'{start_date.strftime("%d.%m.%Y")} - {end_date.strftime("%d.%m.%Y")}'],
        ['Broj narudzbina', totals.orders_count if totals else 0],
        ['Prihod (RSD)', float(totals.revenue) if totals else 0],
        ['Provizija (RSD)', float(totals.commission) if totals else 0],
    ]
    return rows, headers


def _export_csv(rows, headers, filename):
    """Generise CSV fajl."""
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)

    output.seek(0)
    return send_file(
        BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'{filename}.csv',
    )


def _export_xlsx(rows, headers, filename):
    """Generise XLSX fajl koristeci openpyxl."""
    try:
        from openpyxl import Workbook
    except ImportError:
        return {'error': 'openpyxl nije instaliran'}, 500

    wb = Workbook()
    ws = wb.active
    ws.title = 'Izvestaj'
    ws.append(headers)
    for row in rows:
        ws.append(row)

    # Auto-width
    for col in ws.columns:
        max_length = 0
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except (TypeError, AttributeError):
                pass
        ws.column_dimensions[col[0].column_letter].width = min(max_length + 2, 50)

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'{filename}.xlsx',
    )
