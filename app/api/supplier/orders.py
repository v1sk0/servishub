"""
Supplier Orders API - Manage incoming orders

Endpoints:
- GET  /orders              - List all orders
- GET  /orders/pending      - List pending orders
- GET  /orders/<id>         - Get order details
- POST /orders/<id>/confirm - Confirm order (legacy, non-smart-offer)
- POST /orders/<id>/confirm-availability - Confirm availability (smart offer, Paket E)
- POST /orders/<id>/reject  - Reject order
- POST /orders/<id>/ship    - Ship order
- POST /orders/<id>/deliver - Mark as delivered (Paket B)
- POST /orders/<id>/complete - Mark as completed (Paket B)
- POST /orders/<id>/rate    - Rate buyer (Paket D)
- GET  /orders/<id>/messages
- POST /orders/<id>/messages
- GET  /orders/stats
"""
from flask import Blueprint, request, g
from app.extensions import db
from app.models import (
    PartOrder, PartOrderItem, PartOrderMessage,
    OrderStatus, SellerType, Tenant, Supplier, SupplierListing,
    OrderRating, RaterType, OrderRatingType,
)
from .auth import supplier_jwt_required
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime, timedelta, time
from decimal import Decimal

bp = Blueprint('supplier_orders', __name__, url_prefix='/orders')


# ============== Pydantic Schemas ==============

class OrderMessageCreate(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class ShippingUpdate(BaseModel):
    tracking_number: Optional[str] = Field(None, max_length=100)
    tracking_url: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = None


class ConfirmAvailabilitySchema(BaseModel):
    delivery_method: str = Field(..., pattern=r'^(courier|own_delivery|pickup)$')
    courier_service: Optional[str] = Field(None, max_length=50)
    delivery_cost: Optional[Decimal] = Field(None, ge=0)
    estimated_delivery_days: Optional[int] = Field(None, ge=0, le=30)
    delivery_cutoff_time: Optional[str] = Field(None, max_length=5)
    notes: Optional[str] = Field(None, max_length=500)

    @field_validator('delivery_cutoff_time')
    @classmethod
    def validate_cutoff_time(cls, v):
        if v is not None:
            try:
                parts = v.split(':')
                time(int(parts[0]), int(parts[1]))
            except (ValueError, IndexError):
                raise ValueError('delivery_cutoff_time mora biti u formatu HH:MM')
        return v


class RatingCreate(BaseModel):
    rating: str = Field(..., pattern=r'^(POSITIVE|NEGATIVE)$')
    comment: Optional[str] = Field(None, max_length=500)


# ============== Helpers ==============

def _get_buyer_info(order, buyer):
    """
    Vraca buyer info zavisno od statusa narudzbine.
    Pre CONFIRMED: buyer je anoniman (smart offer orders).
    """
    is_smart_offer = order.service_ticket_id is not None
    is_revealed = order.status in (
        OrderStatus.CONFIRMED, OrderStatus.SHIPPED,
        OrderStatus.DELIVERED, OrderStatus.COMPLETED,
    )

    if is_smart_offer and not is_revealed:
        return {
            'id': None,
            'name': '*** (otkriva se nakon potvrde kupca)',
            'email': None,
            'telefon': None,
            'is_revealed': False,
        }

    return {
        'id': buyer.id if buyer else None,
        'name': buyer.name if buyer else 'Unknown',
        'email': buyer.email if buyer else None,
        'telefon': buyer.telefon if buyer else None,
        'is_revealed': True,
    }


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
        buyer_info = _get_buyer_info(order, buyer)

        result.append({
            'id': order.id,
            'order_number': order.order_number,
            'buyer_name': buyer_info['name'],
            'buyer_city': None,
            'status': order.status.value,
            'items_count': items_count,
            'subtotal': float(order.subtotal) if order.subtotal else None,
            'total_amount': float(order.total_amount) if order.total_amount else None,
            'currency': order.currency or 'RSD',
            'created_at': order.created_at.isoformat(),
            'sent_at': order.sent_at.isoformat() if order.sent_at else None,
            'expires_at': order.expires_at.isoformat() if order.expires_at else None,
            'is_smart_offer': order.service_ticket_id is not None,
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
    """List orders pending confirmation (SENT status)"""
    orders = PartOrder.query.filter_by(
        seller_type=SellerType.SUPPLIER,
        seller_supplier_id=g.supplier_id,
        status=OrderStatus.SENT
    ).order_by(PartOrder.sent_at).all()

    result = []
    for order in orders:
        buyer = Tenant.query.get(order.buyer_tenant_id)
        items = PartOrderItem.query.filter_by(order_id=order.id).all()
        buyer_info = _get_buyer_info(order, buyer)

        result.append({
            'id': order.id,
            'order_number': order.order_number,
            'buyer_name': buyer_info['name'],
            'items': [{
                'part_name': item.part_name,
                'quantity': item.quantity,
                'unit_price': float(item.unit_price),
                'total_price': float(item.total_price)
            } for item in items],
            'subtotal': float(order.subtotal) if order.subtotal else None,
            'buyer_notes': order.buyer_notes,
            'sent_at': order.sent_at.isoformat() if order.sent_at else None,
            'expires_at': order.expires_at.isoformat() if order.expires_at else None,
            'is_smart_offer': order.service_ticket_id is not None,
        })

    return {'pending_orders': result, 'count': len(result)}


@bp.route('/<int:order_id>', methods=['GET'])
@supplier_jwt_required
def get_order(order_id):
    """Get order details with buyer info visibility based on status"""
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

    buyer_info = _get_buyer_info(order, buyer)

    resp = {
        'id': order.id,
        'order_number': order.order_number,
        'status': order.status.value,
        'buyer': buyer_info,
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
        'delivery': {
            'method': order.delivery_method,
            'courier_service': order.courier_service,
            'cost': float(order.delivery_cost) if order.delivery_cost else None,
            'estimated_days': order.estimated_delivery_days,
            'cutoff_time': order.delivery_cutoff_time.strftime('%H:%M') if order.delivery_cutoff_time else None,
        },
        'messages': [{
            'id': msg.id,
            'sender_type': msg.sender_type,
            'message': msg.message_text,
            'created_at': msg.created_at.isoformat()
        } for msg in messages],
        'timestamps': {
            'created_at': order.created_at.isoformat(),
            'sent_at': order.sent_at.isoformat() if order.sent_at else None,
            'offered_at': order.offered_at.isoformat() if order.offered_at else None,
            'confirmed_at': order.confirmed_at.isoformat() if order.confirmed_at else None,
            'shipped_at': order.shipped_at.isoformat() if order.shipped_at else None,
            'delivered_at': order.delivered_at.isoformat() if order.delivered_at else None,
            'completed_at': order.completed_at.isoformat() if order.completed_at else None,
        },
        'expires_at': order.expires_at.isoformat() if order.expires_at else None,
        'rejection_reason': order.rejection_reason,
        'cancellation_reason': order.cancellation_reason,
        'is_smart_offer': order.service_ticket_id is not None,
    }

    return resp


@bp.route('/<int:order_id>/confirm', methods=['POST'])
@supplier_jwt_required
def confirm_order(order_id):
    """
    Confirm order (legacy flow - non-smart-offer orders only).
    Smart offer orders MUST use /confirm-availability instead.
    """
    order = PartOrder.query.filter_by(
        id=order_id,
        seller_type=SellerType.SUPPLIER,
        seller_supplier_id=g.supplier_id
    ).first()

    if not order:
        return {'error': 'Order not found'}, 404

    # Smart offer guard: smart offer orders use confirm-availability
    if order.service_ticket_id is not None:
        return {
            'error': 'Smart offer narudzbine koriste confirm-availability endpoint',
            'code': 'USE_CONFIRM_AVAILABILITY'
        }, 409

    if order.status != OrderStatus.SENT:
        return {'error': 'Order cannot be confirmed'}, 400

    notes = request.json.get('notes') if request.json else None

    order.status = OrderStatus.CONFIRMED
    order.confirmed_at = datetime.utcnow()
    order.seller_notes = notes
    order.updated_at = datetime.utcnow()
    db.session.commit()

    return {'message': 'Order confirmed', 'order_id': order.id}


# ============== Paket E: confirm-availability ==============

@bp.route('/<int:order_id>/confirm-availability', methods=['POST'])
@supplier_jwt_required
def confirm_availability(order_id):
    """
    Supplier potvrdjuje dostupnost za smart offer narudzbinu.
    SENT -> OFFERED (2-step flow, Paket E Faza 4).

    Supplier fizicki proverava magacin i potvrdjuje:
    - Delivery method (courier/own_delivery/pickup)
    - Cena dostave, procena dana
    - Opcionalni rok za slanje danas (delivery_cutoff_time)

    BEZ stock decrement - stock se smanjuje tek na CONFIRMED.
    """
    order = PartOrder.query.with_for_update().get(order_id)

    if not order or order.seller_supplier_id != g.supplier_id:
        return {'error': 'Narudzbina nije pronadjena'}, 404

    # Idempotent: vec OFFERED
    if order.status == OrderStatus.OFFERED:
        return {
            'success': True,
            'message': 'Ponuda je vec poslata kupcu.',
            'order_id': order.id,
        }

    if order.status != OrderStatus.SENT:
        return {
            'error': 'Narudzbina nije u statusu za potvrdu dostupnosti',
            'code': 'INVALID_STATUS',
            'current_status': order.status.value,
        }, 409

    try:
        data = ConfirmAvailabilitySchema(**request.json)
    except Exception as e:
        return {'error': str(e)}, 400

    # Parse cutoff time
    cutoff_time = None
    if data.delivery_cutoff_time:
        parts = data.delivery_cutoff_time.split(':')
        cutoff_time = time(int(parts[0]), int(parts[1]))

    # Set delivery info
    order.delivery_method = data.delivery_method
    order.courier_service = data.courier_service
    order.delivery_cost = data.delivery_cost
    order.estimated_delivery_days = data.estimated_delivery_days
    order.delivery_cutoff_time = cutoff_time
    if data.notes:
        order.seller_notes = data.notes

    # Status -> OFFERED + expiry (tenant ima 4h)
    order.status = OrderStatus.OFFERED
    order.offered_at = datetime.utcnow()
    order.expires_at = datetime.utcnow() + timedelta(hours=4)
    order.updated_at = datetime.utcnow()

    db.session.commit()

    # Email tenant-u (non-blocking, Paket D)
    try:
        from app.services.email_service import send_supplier_order_email
        send_supplier_order_email(order, 'offered')
    except (ImportError, Exception):
        pass

    return {
        'success': True,
        'message': 'Ponuda poslata kupcu. Ceka se potvrda.',
        'order_id': order.id,
        'expires_at': order.expires_at.isoformat(),
    }


@bp.route('/<int:order_id>/reject', methods=['POST'])
@supplier_jwt_required
def reject_order(order_id):
    """
    Reject order - from SENT or OFFERED status.
    Includes optional reason comment.
    """
    order = PartOrder.query.filter_by(
        id=order_id,
        seller_type=SellerType.SUPPLIER,
        seller_supplier_id=g.supplier_id
    ).first()

    if not order:
        return {'error': 'Order not found'}, 404

    # Idempotent: vec REJECTED
    if order.status == OrderStatus.REJECTED:
        return {'message': 'Order already rejected'}

    if order.status not in (OrderStatus.SENT, OrderStatus.OFFERED):
        return {
            'error': 'Narudzbina ne moze biti odbijena iz ovog statusa',
            'code': 'INVALID_STATUS',
        }, 409

    reason = request.json.get('reason') if request.json else None

    # BEZ stock rollback - stock nije bio dekrementiiran na OFFERED
    order.status = OrderStatus.REJECTED
    order.rejected_at = datetime.utcnow()
    order.rejection_reason = reason
    order.expires_at = None
    order.updated_at = datetime.utcnow()
    db.session.commit()

    # Email tenant-u (non-blocking)
    try:
        from app.services.email_service import send_supplier_order_email
        send_supplier_order_email(order, 'rejected')
    except (ImportError, Exception):
        pass

    return {'message': 'Order rejected'}


@bp.route('/<int:order_id>/ship', methods=['POST'])
@supplier_jwt_required
def ship_order(order_id):
    """Mark order as shipped with optional tracking info"""
    order = PartOrder.query.filter_by(
        id=order_id,
        seller_type=SellerType.SUPPLIER,
        seller_supplier_id=g.supplier_id
    ).first()

    if not order:
        return {'error': 'Order not found'}, 404

    # Idempotent: vec SHIPPED
    if order.status == OrderStatus.SHIPPED:
        return {'message': 'Order already shipped', 'order_id': order.id}

    if order.status != OrderStatus.CONFIRMED:
        return {'error': 'Order must be confirmed before shipping'}, 400

    try:
        data = ShippingUpdate(**(request.json or {}))
    except Exception as e:
        return {'error': str(e)}, 400

    order.status = OrderStatus.SHIPPED
    order.shipped_at = datetime.utcnow()
    order.tracking_number = data.tracking_number

    # Auto-generate tracking URL from courier_service if available
    if data.tracking_url:
        order.tracking_url = data.tracking_url
    elif data.tracking_number and order.courier_service:
        from app.constants.courier_services import get_tracking_url
        auto_url = get_tracking_url(order.courier_service, data.tracking_number)
        if auto_url:
            order.tracking_url = auto_url

    if data.notes:
        order.seller_notes = data.notes
    order.updated_at = datetime.utcnow()
    db.session.commit()

    # Email tenant-u (non-blocking)
    try:
        from app.services.email_service import send_supplier_order_email
        send_supplier_order_email(order, 'shipped')
    except (ImportError, Exception):
        pass

    return {'message': 'Order shipped', 'order_id': order.id}


# ============== Paket B: deliver + complete ==============

@bp.route('/<int:order_id>/deliver', methods=['POST'])
@supplier_jwt_required
def deliver_order(order_id):
    """
    Mark order as delivered (SHIPPED -> DELIVERED).
    Idempotent: vec DELIVERED -> 200.
    """
    order = PartOrder.query.filter_by(
        id=order_id,
        seller_type=SellerType.SUPPLIER,
        seller_supplier_id=g.supplier_id
    ).first()

    if not order:
        return {'error': 'Order not found'}, 404

    # Idempotent
    if order.status == OrderStatus.DELIVERED:
        return {'message': 'Order already delivered', 'order_id': order.id}

    if order.status != OrderStatus.SHIPPED:
        return {
            'error': 'Narudzbina mora biti u statusu SHIPPED pre isporuke',
            'code': 'INVALID_STATUS',
        }, 409

    order.status = OrderStatus.DELIVERED
    order.delivered_at = datetime.utcnow()
    order.updated_at = datetime.utcnow()
    db.session.commit()

    # Email (non-blocking)
    try:
        from app.services.email_service import send_supplier_order_email
        send_supplier_order_email(order, 'delivered')
    except (ImportError, Exception):
        pass

    return {'message': 'Order delivered', 'order_id': order.id}


@bp.route('/<int:order_id>/complete', methods=['POST'])
@supplier_jwt_required
def complete_order(order_id):
    """
    Mark order as completed (DELIVERED -> COMPLETED).
    Updates supplier totals (total_sales, total_commission).
    Idempotent: vec COMPLETED -> 200.
    """
    order = PartOrder.query.with_for_update().filter_by(
        id=order_id,
        seller_type=SellerType.SUPPLIER,
        seller_supplier_id=g.supplier_id
    ).first()

    if not order:
        return {'error': 'Order not found'}, 404

    # Idempotent
    if order.status == OrderStatus.COMPLETED:
        return {'message': 'Order already completed', 'order_id': order.id}

    if order.status != OrderStatus.DELIVERED:
        return {
            'error': 'Narudzbina mora biti u statusu DELIVERED pre zavrsetka',
            'code': 'INVALID_STATUS',
        }, 409

    # Update supplier financial totals
    supplier = Supplier.query.with_for_update().get(g.supplier_id)
    if supplier:
        if order.subtotal:
            supplier.total_sales = (supplier.total_sales or Decimal('0')) + order.subtotal
        if order.commission_amount:
            supplier.total_commission = (
                (supplier.total_commission or Decimal('0')) + order.commission_amount
            )

    order.status = OrderStatus.COMPLETED
    order.completed_at = datetime.utcnow()
    order.updated_at = datetime.utcnow()
    db.session.commit()

    return {'message': 'Order completed', 'order_id': order.id}


# ============== Paket D: rate ==============

@bp.route('/<int:order_id>/rate', methods=['POST'])
@supplier_jwt_required
def rate_order(order_id):
    """
    Supplier ocenjuje tenanta (SELLER -> BUYER rating).
    Samo COMPLETED narudzbine. Dupli -> 409.
    """
    order = PartOrder.query.filter_by(
        id=order_id,
        seller_type=SellerType.SUPPLIER,
        seller_supplier_id=g.supplier_id
    ).first()

    if not order:
        return {'error': 'Order not found'}, 404

    if order.status != OrderStatus.COMPLETED:
        return {
            'error': 'Ocena je moguca samo za zavrsene narudzbine',
            'code': 'NOT_COMPLETED',
        }, 400

    try:
        data = RatingCreate(**request.json)
    except Exception as e:
        return {'error': str(e)}, 400

    # Check for duplicate (UniqueConstraint)
    existing = OrderRating.query.filter_by(
        order_id=order.id,
        rater_type=RaterType.SELLER,
        rater_id=g.supplier_id,
    ).first()

    if existing:
        return {
            'error': 'Vec ste ocenili ovu narudzbinu',
            'code': 'ALREADY_RATED',
        }, 409

    rating = OrderRating(
        order_id=order.id,
        rater_type=RaterType.SELLER,
        rater_id=g.supplier_id,
        rated_id=order.buyer_tenant_id,
        rating=OrderRatingType[data.rating],
        comment=data.comment,
    )
    db.session.add(rating)
    db.session.commit()

    return {
        'success': True,
        'message': 'Ocena uspesno sacuvana',
        'rating_id': rating.id,
    }, 201


# ============== Messages ==============

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


# ============== Stats ==============

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
    total_revenue = db.session.query(
        func.sum(PartOrder.subtotal)
    ).filter(
        PartOrder.seller_type == SellerType.SUPPLIER,
        PartOrder.seller_supplier_id == g.supplier_id,
        PartOrder.status == OrderStatus.COMPLETED
    ).scalar() or 0

    # Pending count (SENT + OFFERED)
    pending = status_counts.get('SENT', 0)
    offered = status_counts.get('OFFERED', 0)

    return {
        'total_orders': sum(status_counts.values()),
        'pending_confirmation': pending,
        'pending_tenant_confirmation': offered,
        'status_breakdown': status_counts,
        'total_revenue': float(total_revenue),
        'currency': 'RSD'
    }
