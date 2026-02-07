"""
Supplier Dashboard API - Overview and statistics
"""
from flask import Blueprint, g
from app.extensions import db
from app.models import (
    Supplier, SupplierListing, PartOrder,
    OrderStatus, SellerType
)
from .auth import supplier_jwt_required
from datetime import datetime, timedelta
from sqlalchemy import func

bp = Blueprint('supplier_dashboard', __name__, url_prefix='/dashboard')


@bp.route('', methods=['GET'])
@supplier_jwt_required
def get_dashboard():
    """Get supplier dashboard overview"""

    supplier = Supplier.query.get(g.supplier_id)
    if not supplier:
        return {'error': 'Supplier not found'}, 404

    # === Listings Stats ===
    total_listings = SupplierListing.query.filter_by(
        supplier_id=g.supplier_id
    ).count()

    active_listings = SupplierListing.query.filter_by(
        supplier_id=g.supplier_id,
        is_active=True
    ).count()

    in_stock = SupplierListing.query.filter(
        SupplierListing.supplier_id == g.supplier_id,
        SupplierListing.is_active == True,
        SupplierListing.stock_quantity > 0
    ).count()

    out_of_stock = active_listings - in_stock

    # === Orders Stats ===
    base_orders = PartOrder.query.filter_by(
        seller_type=SellerType.SUPPLIER,
        seller_supplier_id=g.supplier_id
    )

    # Orders needing attention (pending confirmation)
    pending_orders = base_orders.filter_by(status=OrderStatus.SENT).count()

    # Orders in progress (confirmed but not shipped)
    in_progress = base_orders.filter_by(status=OrderStatus.CONFIRMED).count()

    # Shipped orders
    shipped = base_orders.filter_by(status=OrderStatus.SHIPPED).count()

    # Completed orders
    completed = base_orders.filter_by(status=OrderStatus.COMPLETED).count()

    # Total orders
    total_orders = base_orders.count()

    # === Revenue (last 30 days) ===
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    revenue_30d = db.session.query(
        func.sum(PartOrder.subtotal)
    ).filter(
        PartOrder.seller_type == SellerType.SUPPLIER,
        PartOrder.seller_supplier_id == g.supplier_id,
        PartOrder.status == OrderStatus.COMPLETED,
        PartOrder.completed_at >= thirty_days_ago
    ).scalar() or 0

    # Total revenue
    total_revenue = db.session.query(
        func.sum(PartOrder.subtotal)
    ).filter(
        PartOrder.seller_type == SellerType.SUPPLIER,
        PartOrder.seller_supplier_id == g.supplier_id,
        PartOrder.status == OrderStatus.COMPLETED
    ).scalar() or 0

    # Total commission paid
    total_commission = db.session.query(
        func.sum(PartOrder.commission_amount)
    ).filter(
        PartOrder.seller_type == SellerType.SUPPLIER,
        PartOrder.seller_supplier_id == g.supplier_id,
        PartOrder.status == OrderStatus.COMPLETED
    ).scalar() or 0

    # === Recent Orders ===
    recent_orders = base_orders.order_by(
        PartOrder.created_at.desc()
    ).limit(5).all()

    recent_orders_list = []
    for order in recent_orders:
        from app.models import Tenant
        buyer = Tenant.query.get(order.buyer_tenant_id)
        recent_orders_list.append({
            'id': order.id,
            'order_number': order.order_number,
            'buyer_name': buyer.name if buyer else 'Unknown',
            'status': order.status.value,
            'total_amount': float(order.total_amount) if order.total_amount else None,
            'created_at': order.created_at.isoformat()
        })

    return {
        'supplier': {
            'id': supplier.id,
            'name': supplier.name,
            'status': supplier.status.value,
            'is_verified': supplier.is_verified,
            'rating': float(supplier.rating) if supplier.rating else None,
            'rating_count': supplier.rating_count
        },
        'listings': {
            'total': total_listings,
            'active': active_listings,
            'in_stock': in_stock,
            'out_of_stock': out_of_stock
        },
        'orders': {
            'total': total_orders,
            'pending_confirmation': pending_orders,
            'in_progress': in_progress,
            'shipped': shipped,
            'completed': completed,
            'needs_attention': pending_orders  # Orders that need action
        },
        'revenue': {
            'last_30_days': float(revenue_30d),
            'total': float(total_revenue),
            'total_commission': float(total_commission),
            'currency': 'RSD'
        },
        'recent_orders': recent_orders_list
    }


@bp.route('/alerts', methods=['GET'])
@supplier_jwt_required
def get_alerts():
    """Get alerts and notifications for supplier"""

    alerts = []

    # Check for pending orders
    pending_orders = PartOrder.query.filter_by(
        seller_type=SellerType.SUPPLIER,
        seller_supplier_id=g.supplier_id,
        status=OrderStatus.SENT
    ).count()

    if pending_orders > 0:
        alerts.append({
            'type': 'warning',
            'title': 'Porudžbine čekaju potvrdu',
            'message': f'Imate {pending_orders} porudžbin{"u" if pending_orders == 1 else "e" if pending_orders < 5 else "a"} koje čekaju potvrdu',
            'action': '/supplier/orders/pending'
        })

    # Check for out of stock items
    out_of_stock = SupplierListing.query.filter(
        SupplierListing.supplier_id == g.supplier_id,
        SupplierListing.is_active == True,
        SupplierListing.stock_quantity <= 0
    ).count()

    if out_of_stock > 0:
        alerts.append({
            'type': 'info',
            'title': 'Artikli bez zaliha',
            'message': f'{out_of_stock} artik{"al" if out_of_stock == 1 else "la"} je bez zaliha',
            'action': '/supplier/listings?filter=out_of_stock'
        })

    # Check supplier verification status
    supplier = Supplier.query.get(g.supplier_id)
    if supplier and not supplier.is_verified:
        alerts.append({
            'type': 'info',
            'title': 'Verifikacija u toku',
            'message': 'Vaš nalog čeka verifikaciju. Neki preduslovi mogu biti ograničeni.',
            'action': None
        })

    # Check for unread messages
    from app.models import PartOrderMessage
    unread_messages = PartOrderMessage.query.join(PartOrder).filter(
        PartOrder.seller_type == SellerType.SUPPLIER,
        PartOrder.seller_supplier_id == g.supplier_id,
        PartOrderMessage.sender_type == 'buyer',
        PartOrderMessage.read_at == None
    ).count()

    if unread_messages > 0:
        alerts.append({
            'type': 'info',
            'title': 'Nepročitane poruke',
            'message': f'Imate {unread_messages} nepročitan{"u" if unread_messages == 1 else "e" if unread_messages < 5 else "ih"} poruk{"u" if unread_messages == 1 else "e" if unread_messages < 5 else "a"}',
            'action': '/supplier/orders'
        })

    return {'alerts': alerts, 'count': len(alerts)}


@bp.route('/activity', methods=['GET'])
@supplier_jwt_required
def get_recent_activity():
    """Get recent activity feed"""

    activities = []

    # Get recent orders with status changes
    recent_orders = PartOrder.query.filter_by(
        seller_type=SellerType.SUPPLIER,
        seller_supplier_id=g.supplier_id
    ).order_by(PartOrder.updated_at.desc()).limit(10).all()

    from app.models import Tenant

    for order in recent_orders:
        buyer = Tenant.query.get(order.buyer_tenant_id)
        buyer_name = buyer.name if buyer else 'Unknown'

        if order.status == OrderStatus.SENT:
            activities.append({
                'type': 'order_new',
                'title': f'Nova porudžbina od {buyer_name}',
                'order_number': order.order_number,
                'timestamp': order.sent_at.isoformat() if order.sent_at else order.created_at.isoformat()
            })
        elif order.status == OrderStatus.COMPLETED:
            activities.append({
                'type': 'order_completed',
                'title': f'Porudžbina {order.order_number} završena',
                'order_number': order.order_number,
                'timestamp': order.completed_at.isoformat() if order.completed_at else order.updated_at.isoformat()
            })

    # Sort by timestamp
    activities.sort(key=lambda x: x['timestamp'], reverse=True)

    return {'activities': activities[:10]}
