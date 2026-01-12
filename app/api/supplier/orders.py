"""
Supplier Orders API - Manage incoming orders
"""
from flask import Blueprint, request, g
from app.extensions import db
from app.models import (
    PartOrder, PartOrderItem, PartOrderMessage,
    OrderStatus, SellerType, Tenant
)
from .auth import supplier_jwt_required
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

bp = Blueprint('supplier_orders', __name__, url_prefix='/orders')


# ============== Pydantic Schemas ==============

class OrderMessageCreate(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class ShippingUpdate(BaseModel):
    tracking_number: Optional[str] = Field(None, max_length=100)
    tracking_url: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = None


# ============== Routes ==============

@bp.route('', methods=['GET'])
@supplier_jwt_required
def list_orders():
    """List orders for current supplier"""
    status_filter = request.args.get('status')
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)

    query = PartOrder.query.filter_by(
        seller_type=SellerType.SUPPLIER,
        seller_supplier_id=g.supplier_id
    )

    if status_filter:
        try:
            status = OrderStatus[status_filter.upper()]
            query = query.filter_by(status=status)
        except KeyError:
            pass

    query = query.order_by(PartOrder.created_at.desc())
    total = query.count()
    orders = query.offset((page - 1) * per_page).limit(per_page).all()

    result = []
    for order in orders:
        buyer = Tenant.query.get(order.buyer_tenant_id)
        items_count = PartOrderItem.query.filter_by(order_id=order.id).count()

        result.append({
            'id': order.id,
            'order_number': order.order_number,
            'buyer_name': buyer.name if buyer else 'Unknown',
            'buyer_city': None,  # Could get from location
            'status': order.status.value,
            'items_count': items_count,
            'subtotal': float(order.subtotal) if order.subtotal else None,
            'total_amount': float(order.total_amount) if order.total_amount else None,
            'currency': order.currency or 'RSD',
            'created_at': order.created_at.isoformat(),
            'sent_at': order.sent_at.isoformat() if order.sent_at else None
        })

    return {
        'orders': result,
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page
    }


@bp.route('/pending', methods=['GET'])
@supplier_jwt_required
def list_pending_orders():
    """List orders pending confirmation"""
    orders = PartOrder.query.filter_by(
        seller_type=SellerType.SUPPLIER,
        seller_supplier_id=g.supplier_id,
        status=OrderStatus.SENT
    ).order_by(PartOrder.sent_at).all()

    result = []
    for order in orders:
        buyer = Tenant.query.get(order.buyer_tenant_id)
        items = PartOrderItem.query.filter_by(order_id=order.id).all()

        result.append({
            'id': order.id,
            'order_number': order.order_number,
            'buyer_name': buyer.name if buyer else 'Unknown',
            'items': [{
                'part_name': item.part_name,
                'quantity': item.quantity,
                'unit_price': float(item.unit_price),
                'total_price': float(item.total_price)
            } for item in items],
            'subtotal': float(order.subtotal) if order.subtotal else None,
            'buyer_notes': order.buyer_notes,
            'sent_at': order.sent_at.isoformat() if order.sent_at else None
        })

    return {'pending_orders': result, 'count': len(result)}


@bp.route('/<int:order_id>', methods=['GET'])
@supplier_jwt_required
def get_order(order_id):
    """Get order details"""
    order = PartOrder.query.filter_by(
        id=order_id,
        seller_type=SellerType.SUPPLIER,
        seller_supplier_id=g.supplier_id
    ).first()

    if not order:
        return {'error': 'Order not found'}, 404

    buyer = Tenant.query.get(order.buyer_tenant_id)
    items = PartOrderItem.query.filter_by(order_id=order.id).all()
    messages = PartOrderMessage.query.filter_by(
        order_id=order.id
    ).order_by(PartOrderMessage.created_at).all()

    return {
        'id': order.id,
        'order_number': order.order_number,
        'status': order.status.value,
        'buyer': {
            'id': buyer.id if buyer else None,
            'name': buyer.name if buyer else 'Unknown',
            'email': buyer.email if buyer else None,
            'telefon': buyer.telefon if buyer else None
        },
        'items': [{
            'id': item.id,
            'part_name': item.part_name,
            'part_number': item.part_number,
            'brand': item.brand,
            'quantity': item.quantity,
            'unit_price': float(item.unit_price),
            'total_price': float(item.total_price)
        } for item in items],
        'subtotal': float(order.subtotal) if order.subtotal else None,
        'commission_amount': float(order.commission_amount) if order.commission_amount else None,
        'total_amount': float(order.total_amount) if order.total_amount else None,
        'currency': order.currency or 'RSD',
        'buyer_notes': order.buyer_notes,
        'seller_notes': order.seller_notes,
        'tracking_number': order.tracking_number,
        'tracking_url': order.tracking_url,
        'messages': [{
            'id': msg.id,
            'sender_type': msg.sender_type,
            'message': msg.message_text,
            'created_at': msg.created_at.isoformat()
        } for msg in messages],
        'timestamps': {
            'created_at': order.created_at.isoformat(),
            'sent_at': order.sent_at.isoformat() if order.sent_at else None,
            'confirmed_at': order.confirmed_at.isoformat() if order.confirmed_at else None,
            'shipped_at': order.shipped_at.isoformat() if order.shipped_at else None,
            'delivered_at': order.delivered_at.isoformat() if order.delivered_at else None,
            'completed_at': order.completed_at.isoformat() if order.completed_at else None
        },
        'rejection_reason': order.rejection_reason
    }


@bp.route('/<int:order_id>/confirm', methods=['POST'])
@supplier_jwt_required
def confirm_order(order_id):
    """Confirm order"""
    order = PartOrder.query.filter_by(
        id=order_id,
        seller_type=SellerType.SUPPLIER,
        seller_supplier_id=g.supplier_id
    ).first()

    if not order:
        return {'error': 'Order not found'}, 404

    if order.status != OrderStatus.SENT:
        return {'error': 'Order cannot be confirmed'}, 400

    notes = request.json.get('notes') if request.json else None

    order.status = OrderStatus.CONFIRMED
    order.confirmed_at = datetime.utcnow()
    order.seller_notes = notes
    order.updated_at = datetime.utcnow()
    db.session.commit()

    return {'message': 'Order confirmed', 'order_id': order.id}


@bp.route('/<int:order_id>/reject', methods=['POST'])
@supplier_jwt_required
def reject_order(order_id):
    """Reject order"""
    order = PartOrder.query.filter_by(
        id=order_id,
        seller_type=SellerType.SUPPLIER,
        seller_supplier_id=g.supplier_id
    ).first()

    if not order:
        return {'error': 'Order not found'}, 404

    if order.status != OrderStatus.SENT:
        return {'error': 'Order cannot be rejected'}, 400

    reason = request.json.get('reason') if request.json else None

    order.status = OrderStatus.REJECTED
    order.rejected_at = datetime.utcnow()
    order.rejection_reason = reason
    order.updated_at = datetime.utcnow()
    db.session.commit()

    return {'message': 'Order rejected'}


@bp.route('/<int:order_id>/ship', methods=['POST'])
@supplier_jwt_required
def ship_order(order_id):
    """Mark order as shipped"""
    order = PartOrder.query.filter_by(
        id=order_id,
        seller_type=SellerType.SUPPLIER,
        seller_supplier_id=g.supplier_id
    ).first()

    if not order:
        return {'error': 'Order not found'}, 404

    if order.status != OrderStatus.CONFIRMED:
        return {'error': 'Order must be confirmed before shipping'}, 400

    try:
        data = ShippingUpdate(**(request.json or {}))
    except Exception as e:
        return {'error': str(e)}, 400

    order.status = OrderStatus.SHIPPED
    order.shipped_at = datetime.utcnow()
    order.tracking_number = data.tracking_number
    order.tracking_url = data.tracking_url
    if data.notes:
        order.seller_notes = data.notes
    order.updated_at = datetime.utcnow()
    db.session.commit()

    return {'message': 'Order shipped', 'order_id': order.id}


@bp.route('/<int:order_id>/messages', methods=['GET'])
@supplier_jwt_required
def get_order_messages(order_id):
    """Get order messages"""
    order = PartOrder.query.filter_by(
        id=order_id,
        seller_type=SellerType.SUPPLIER,
        seller_supplier_id=g.supplier_id
    ).first()

    if not order:
        return {'error': 'Order not found'}, 404

    messages = PartOrderMessage.query.filter_by(
        order_id=order.id
    ).order_by(PartOrderMessage.created_at).all()

    # Mark buyer messages as read
    for msg in messages:
        if msg.sender_type == 'buyer' and not msg.read_at:
            msg.read_at = datetime.utcnow()
    db.session.commit()

    return {
        'messages': [{
            'id': msg.id,
            'sender_type': msg.sender_type,
            'message': msg.message_text,
            'created_at': msg.created_at.isoformat(),
            'read_at': msg.read_at.isoformat() if msg.read_at else None
        } for msg in messages]
    }


@bp.route('/<int:order_id>/messages', methods=['POST'])
@supplier_jwt_required
def send_order_message(order_id):
    """Send message on order"""
    order = PartOrder.query.filter_by(
        id=order_id,
        seller_type=SellerType.SUPPLIER,
        seller_supplier_id=g.supplier_id
    ).first()

    if not order:
        return {'error': 'Order not found'}, 404

    try:
        data = OrderMessageCreate(**request.json)
    except Exception as e:
        return {'error': str(e)}, 400

    message = PartOrderMessage(
        order_id=order.id,
        sender_type='seller',
        sender_user_id=g.supplier_user_id,
        message_text=data.message
    )
    db.session.add(message)
    db.session.commit()

    return {
        'message': 'Message sent',
        'message_id': message.id
    }, 201


@bp.route('/stats', methods=['GET'])
@supplier_jwt_required
def get_order_stats():
    """Get order statistics"""
    from sqlalchemy import func

    base_query = PartOrder.query.filter_by(
        seller_type=SellerType.SUPPLIER,
        seller_supplier_id=g.supplier_id
    )

    # Count by status
    status_counts = {}
    for status in OrderStatus:
        count = base_query.filter_by(status=status).count()
        status_counts[status.value] = count

    # Total revenue (completed orders)
    completed = base_query.filter_by(status=OrderStatus.COMPLETED)
    total_revenue = db.session.query(
        func.sum(PartOrder.subtotal)
    ).filter(
        PartOrder.seller_type == SellerType.SUPPLIER,
        PartOrder.seller_supplier_id == g.supplier_id,
        PartOrder.status == OrderStatus.COMPLETED
    ).scalar() or 0

    # Pending count
    pending = status_counts.get('SENT', 0)

    return {
        'total_orders': sum(status_counts.values()),
        'pending_confirmation': pending,
        'status_breakdown': status_counts,
        'total_revenue': float(total_revenue),
        'currency': 'RSD'
    }
