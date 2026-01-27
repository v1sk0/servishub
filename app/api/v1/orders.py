"""
Part Orders API - Create and manage orders from marketplace
"""
from flask import Blueprint, request, g
from app.extensions import db
from app.models import (
    PartOrder, PartOrderItem, PartOrderMessage,
    OrderStatus, SellerType,
    Supplier, SupplierListing,
    Tenant, SparePart, PartVisibility,
    TenantUser, ServiceLocation, ServiceTicket,
    SupplierReveal
)
from app.models.credits import OwnerType, CreditTransactionType
from app.api.middleware.auth import jwt_required
from app.utils.content_filter import filter_contact_info, is_blocked_file_extension
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
import secrets

bp = Blueprint('orders', __name__, url_prefix='/orders')


# ============== Pydantic Schemas ==============

class OrderItemCreate(BaseModel):
    source: str  # 'supplier' or 'tenant'
    listing_id: int
    quantity: int = Field(..., ge=1)


class OrderCreate(BaseModel):
    items: List[OrderItemCreate]
    location_id: Optional[int] = None
    service_ticket_id: Optional[int] = None
    notes: Optional[str] = None


class OrderMessageCreate(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


# ============== Helper Functions ==============

def generate_order_number():
    """Generate unique order number"""
    timestamp = datetime.utcnow().strftime('%y%m%d')
    random_part = secrets.token_hex(3).upper()
    return f'ORD-{timestamp}-{random_part}'


# ============== Routes ==============

@bp.route('', methods=['GET'])
@jwt_required
def list_orders():
    """List orders for current tenant (as buyer)"""
    status_filter = request.args.get('status')
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)

    query = PartOrder.query.filter_by(buyer_tenant_id=g.tenant_id)

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
        seller_name = None
        if order.seller_type == SellerType.SUPPLIER:
            supplier = Supplier.query.get(order.seller_supplier_id)
            seller_name = supplier.name if supplier else 'Unknown'
        else:
            tenant = Tenant.query.get(order.seller_tenant_id)
            seller_name = tenant.name if tenant else 'Unknown'

        items_count = PartOrderItem.query.filter_by(order_id=order.id).count()

        result.append({
            'id': order.id,
            'order_number': order.order_number,
            'seller_type': order.seller_type.value,
            'seller_name': seller_name,
            'status': order.status.value,
            'items_count': items_count,
            'total_amount': float(order.total_amount) if order.total_amount else None,
            'currency': order.currency or 'RSD',
            'created_at': order.created_at.isoformat(),
            'tracking_number': order.tracking_number
        })

    return {
        'orders': result,
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page
    }


@bp.route('/<int:order_id>', methods=['GET'])
@jwt_required
def get_order(order_id):
    """Get order details"""
    order = PartOrder.query.filter_by(
        id=order_id,
        buyer_tenant_id=g.tenant_id
    ).first()

    if not order:
        return {'error': 'Order not found'}, 404

    # Get seller info
    seller_info = {}
    if order.seller_type == SellerType.SUPPLIER:
        supplier = Supplier.query.get(order.seller_supplier_id)
        if supplier:
            seller_info = {
                'type': 'supplier',
                'id': supplier.id,
                'name': supplier.name,
                'city': supplier.city,
                'phone': supplier.phone,
                'email': supplier.email
            }
    else:
        tenant = Tenant.query.get(order.seller_tenant_id)
        if tenant:
            seller_info = {
                'type': 'tenant',
                'id': tenant.id,
                'name': tenant.name
            }

    # Get items
    items = PartOrderItem.query.filter_by(order_id=order.id).all()
    items_list = [{
        'id': item.id,
        'part_name': item.part_name,
        'part_number': item.part_number,
        'brand': item.brand,
        'model': item.model,
        'quantity': item.quantity,
        'unit_price': float(item.unit_price),
        'total_price': float(item.total_price)
    } for item in items]

    # Get messages
    messages = PartOrderMessage.query.filter_by(
        order_id=order.id
    ).order_by(PartOrderMessage.created_at).all()

    messages_list = [{
        'id': msg.id,
        'sender_type': msg.sender_type,
        'message': msg.message_text,
        'created_at': msg.created_at.isoformat()
    } for msg in messages]

    # Get linked ticket if any
    ticket_info = None
    if order.service_ticket_id:
        ticket = ServiceTicket.query.get(order.service_ticket_id)
        if ticket:
            ticket_info = {
                'id': ticket.id,
                'ticket_number': ticket.ticket_number,
                'customer_name': ticket.customer_name
            }

    return {
        'id': order.id,
        'order_number': order.order_number,
        'status': order.status.value,
        'seller': seller_info,
        'items': items_list,
        'subtotal': float(order.subtotal) if order.subtotal else None,
        'commission_amount': float(order.commission_amount) if order.commission_amount else None,
        'total_amount': float(order.total_amount) if order.total_amount else None,
        'currency': order.currency or 'RSD',
        'buyer_notes': order.buyer_notes,
        'seller_notes': order.seller_notes,
        'tracking_number': order.tracking_number,
        'tracking_url': order.tracking_url,
        'service_ticket': ticket_info,
        'messages': messages_list,
        'timestamps': {
            'created_at': order.created_at.isoformat(),
            'sent_at': order.sent_at.isoformat() if order.sent_at else None,
            'confirmed_at': order.confirmed_at.isoformat() if order.confirmed_at else None,
            'shipped_at': order.shipped_at.isoformat() if order.shipped_at else None,
            'delivered_at': order.delivered_at.isoformat() if order.delivered_at else None,
            'completed_at': order.completed_at.isoformat() if order.completed_at else None,
            'rejected_at': order.rejected_at.isoformat() if order.rejected_at else None,
            'cancelled_at': order.cancelled_at.isoformat() if order.cancelled_at else None
        },
        'rejection_reason': order.rejection_reason,
        'cancellation_reason': order.cancellation_reason
    }


@bp.route('', methods=['POST'])
@jwt_required
def create_order():
    """Create new order"""
    try:
        data = OrderCreate(**request.json)
    except Exception as e:
        return {'error': str(e)}, 400

    if not data.items:
        return {'error': 'At least one item required'}, 400

    # Group items by seller
    supplier_items = {}  # supplier_id -> items
    tenant_items = {}    # tenant_id -> items

    for item_data in data.items:
        if item_data.source == 'supplier':
            listing = SupplierListing.query.get(item_data.listing_id)
            if not listing or not listing.is_active:
                return {'error': f'Listing {item_data.listing_id} not found'}, 400

            if listing.stock_quantity < item_data.quantity:
                return {'error': f'Not enough stock for {listing.name}'}, 400

            supplier_id = listing.supplier_id
            if supplier_id not in supplier_items:
                supplier_items[supplier_id] = []
            supplier_items[supplier_id].append({
                'listing': listing,
                'quantity': item_data.quantity
            })

        elif item_data.source == 'tenant':
            part = SparePart.query.get(item_data.listing_id)
            if not part or not part.is_active:
                return {'error': f'Part {item_data.listing_id} not found'}, 400

            if part.tenant_id == g.tenant_id:
                return {'error': 'Cannot order from yourself'}, 400

            if part.visibility not in [PartVisibility.PUBLIC, PartVisibility.PARTNER]:
                return {'error': f'Part {part.part_name} not available'}, 400

            if part.quantity < item_data.quantity:
                return {'error': f'Not enough stock for {part.part_name}'}, 400

            tenant_id = part.tenant_id
            if tenant_id not in tenant_items:
                tenant_items[tenant_id] = []
            tenant_items[tenant_id].append({
                'part': part,
                'quantity': item_data.quantity
            })

        else:
            return {'error': 'Invalid source'}, 400

    # Validate location
    location = None
    if data.location_id:
        location = ServiceLocation.query.filter_by(
            id=data.location_id,
            tenant_id=g.tenant_id
        ).first()
        if not location:
            return {'error': 'Location not found'}, 400

    # Validate ticket
    ticket = None
    if data.service_ticket_id:
        ticket = ServiceTicket.query.filter_by(
            id=data.service_ticket_id,
            tenant_id=g.tenant_id
        ).first()
        if not ticket:
            return {'error': 'Ticket not found'}, 400

    created_orders = []

    # Create orders for each supplier
    for supplier_id, items in supplier_items.items():
        supplier = Supplier.query.get(supplier_id)

        subtotal = Decimal('0')
        for item in items:
            subtotal += Decimal(str(item['listing'].price)) * item['quantity']

        # 5% commission
        commission = subtotal * Decimal('0.05')
        total = subtotal + commission

        order = PartOrder(
            buyer_tenant_id=g.tenant_id,
            buyer_location_id=data.location_id,
            buyer_user_id=g.user_id,
            seller_type=SellerType.SUPPLIER,
            seller_supplier_id=supplier_id,
            service_ticket_id=data.service_ticket_id,
            order_number=generate_order_number(),
            status=OrderStatus.DRAFT,
            subtotal=subtotal,
            commission_amount=commission,
            total_amount=total,
            currency='RSD',
            buyer_notes=data.notes
        )
        db.session.add(order)
        db.session.flush()

        # Add items
        for item in items:
            listing = item['listing']
            order_item = PartOrderItem(
                order_id=order.id,
                supplier_listing_id=listing.id,
                part_name=listing.name,
                part_number=listing.part_number,
                brand=listing.brand,
                model=listing.model_compatibility,
                quantity=item['quantity'],
                unit_price=listing.price,
                total_price=Decimal(str(listing.price)) * item['quantity']
            )
            db.session.add(order_item)

        created_orders.append(order.id)

    # Create orders for each tenant seller
    for tenant_id, items in tenant_items.items():
        subtotal = Decimal('0')
        for item in items:
            part = item['part']
            price = part.public_price if part.visibility == PartVisibility.PUBLIC else part.selling_price
            if price:
                subtotal += Decimal(str(price)) * item['quantity']

        # 5% commission
        commission = subtotal * Decimal('0.05')
        total = subtotal + commission

        order = PartOrder(
            buyer_tenant_id=g.tenant_id,
            buyer_location_id=data.location_id,
            buyer_user_id=g.user_id,
            seller_type=SellerType.TENANT,
            seller_tenant_id=tenant_id,
            service_ticket_id=data.service_ticket_id,
            order_number=generate_order_number(),
            status=OrderStatus.DRAFT,
            subtotal=subtotal,
            commission_amount=commission,
            total_amount=total,
            currency='RSD',
            buyer_notes=data.notes
        )
        db.session.add(order)
        db.session.flush()

        # Add items
        for item in items:
            part = item['part']
            price = part.public_price if part.visibility == PartVisibility.PUBLIC else part.selling_price

            order_item = PartOrderItem(
                order_id=order.id,
                spare_part_id=part.id,
                part_name=part.part_name,
                part_number=part.part_number,
                brand=part.brand,
                model=part.model,
                quantity=item['quantity'],
                unit_price=price or Decimal('0'),
                total_price=(Decimal(str(price)) if price else Decimal('0')) * item['quantity']
            )
            db.session.add(order_item)

        created_orders.append(order.id)

    db.session.commit()

    return {
        'message': f'Created {len(created_orders)} order(s)',
        'order_ids': created_orders
    }, 201


@bp.route('/<int:order_id>/send', methods=['POST'])
@jwt_required
def send_order(order_id):
    """Send draft order to seller"""
    order = PartOrder.query.filter_by(
        id=order_id,
        buyer_tenant_id=g.tenant_id
    ).first()

    if not order:
        return {'error': 'Order not found'}, 404

    if order.status != OrderStatus.DRAFT:
        return {'error': 'Order already sent'}, 400

    order.status = OrderStatus.SENT
    order.sent_at = datetime.utcnow()
    order.updated_at = datetime.utcnow()
    db.session.commit()

    return {'message': 'Order sent', 'order_id': order.id}


@bp.route('/<int:order_id>/cancel', methods=['POST'])
@jwt_required
def cancel_order(order_id):
    """Cancel order"""
    order = PartOrder.query.filter_by(
        id=order_id,
        buyer_tenant_id=g.tenant_id
    ).first()

    if not order:
        return {'error': 'Order not found'}, 404

    if order.status in [OrderStatus.SHIPPED, OrderStatus.DELIVERED, OrderStatus.COMPLETED]:
        return {'error': 'Cannot cancel shipped or completed order'}, 400

    reason = request.json.get('reason') if request.json else None

    order.status = OrderStatus.CANCELLED
    order.cancelled_at = datetime.utcnow()
    order.cancellation_reason = reason
    order.cancelled_by = 'buyer'
    order.updated_at = datetime.utcnow()
    db.session.commit()

    return {'message': 'Order cancelled'}


@bp.route('/<int:order_id>/confirm-delivery', methods=['POST'])
@jwt_required
def confirm_delivery(order_id):
    """Confirm order delivery"""
    order = PartOrder.query.filter_by(
        id=order_id,
        buyer_tenant_id=g.tenant_id
    ).first()

    if not order:
        return {'error': 'Order not found'}, 404

    if order.status != OrderStatus.SHIPPED:
        return {'error': 'Order not shipped yet'}, 400

    order.status = OrderStatus.DELIVERED
    order.delivered_at = datetime.utcnow()
    order.updated_at = datetime.utcnow()
    db.session.commit()

    return {'message': 'Delivery confirmed'}


@bp.route('/<int:order_id>/complete', methods=['POST'])
@jwt_required
def complete_order(order_id):
    """Mark order as complete (satisfied)"""
    order = PartOrder.query.filter_by(
        id=order_id,
        buyer_tenant_id=g.tenant_id
    ).first()

    if not order:
        return {'error': 'Order not found'}, 404

    if order.status != OrderStatus.DELIVERED:
        return {'error': 'Order not delivered yet'}, 400

    order.status = OrderStatus.COMPLETED
    order.completed_at = datetime.utcnow()
    order.updated_at = datetime.utcnow()
    db.session.commit()

    return {'message': 'Order completed'}


@bp.route('/<int:order_id>/messages', methods=['GET'])
@jwt_required
def get_order_messages(order_id):
    """Get order messages"""
    order = PartOrder.query.filter_by(
        id=order_id,
        buyer_tenant_id=g.tenant_id
    ).first()

    if not order:
        return {'error': 'Order not found'}, 404

    messages = PartOrderMessage.query.filter_by(
        order_id=order.id
    ).order_by(PartOrderMessage.created_at).all()

    return {
        'messages': [{
            'id': msg.id,
            'sender_type': msg.sender_type,
            'message': msg.message_text,
            'attachments': msg.attachments_json,
            'created_at': msg.created_at.isoformat(),
            'read_at': msg.read_at.isoformat() if msg.read_at else None
        } for msg in messages]
    }


@bp.route('/<int:order_id>/messages', methods=['POST'])
@jwt_required
def send_order_message(order_id):
    """Send message on order"""
    order = PartOrder.query.filter_by(
        id=order_id,
        buyer_tenant_id=g.tenant_id
    ).first()

    if not order:
        return {'error': 'Order not found'}, 404

    try:
        data = OrderMessageCreate(**request.json)
    except Exception as e:
        return {'error': str(e)}, 400

    # Filtriraj kontakt info pre reveal-a (za supplier ordere)
    msg_text = data.message
    if order.seller_type == SellerType.SUPPLIER and order.status in (OrderStatus.DRAFT, OrderStatus.SENT):
        is_revealed = SupplierReveal.query.filter_by(
            tenant_id=g.tenant_id,
            supplier_id=order.seller_supplier_id
        ).first() is not None
        if not is_revealed:
            msg_text = filter_contact_info(msg_text)

    message = PartOrderMessage(
        order_id=order.id,
        sender_type='buyer',
        sender_user_id=g.user_id,
        message_text=msg_text
    )
    db.session.add(message)
    db.session.commit()

    return {
        'message': 'Message sent',
        'message_id': message.id
    }, 201


@bp.route('/<int:order_id>/accept', methods=['POST'])
@jwt_required
def accept_order(order_id):
    """
    Accept order - otkriva kontakt dobavljača uz kredit dedukciju.

    Za supplier ordere: 1 kredit za otkrivanje dobavljačevih podataka.
    Idempotentno - ako je već otkriven, ne naplaćuje ponovo.
    """
    order = PartOrder.query.filter_by(
        id=order_id,
        buyer_tenant_id=g.tenant_id
    ).first()

    if not order:
        return {'error': 'Order not found'}, 404

    if order.seller_type != SellerType.SUPPLIER:
        return {'error': 'Accept is only for supplier orders'}, 400

    supplier_id = order.seller_supplier_id
    supplier = Supplier.query.get(supplier_id)
    if not supplier:
        return {'error': 'Supplier not found'}, 404

    # Proveri da li je već otkriven (idempotentno)
    existing_reveal = SupplierReveal.query.filter_by(
        tenant_id=g.tenant_id,
        supplier_id=supplier_id
    ).first()

    if existing_reveal:
        return {
            'message': 'Dobavljač je već otkriven',
            'supplier': supplier.to_revealed_dict()
        }, 200

    # Dedukcija 1 kredita
    from app.services.credit_service import deduct_credits
    idempotency_key = f"reveal_{g.tenant_id}_{supplier_id}"
    txn = deduct_credits(
        owner_type=OwnerType.TENANT,
        owner_id=g.tenant_id,
        amount=1,
        transaction_type=CreditTransactionType.CONNECTION_FEE,
        description=f"Otkrivanje dobavljača #{supplier_id}",
        ref_type='supplier_reveal',
        ref_id=supplier_id,
        idempotency_key=idempotency_key,
    )

    if txn is False:
        return {'error': 'Nemate dovoljno kredita', 'credits_required': 1}, 402

    # Kreiraj SupplierReveal zapis
    reveal = SupplierReveal(
        tenant_id=g.tenant_id,
        supplier_id=supplier_id,
        credit_transaction_id=txn.id,
    )
    db.session.add(reveal)
    db.session.commit()

    return {
        'message': 'Dobavljač otkriven',
        'supplier': supplier.to_revealed_dict(),
        'credits_spent': 1
    }, 200


@bp.route('/statuses', methods=['GET'])
@jwt_required
def list_statuses():
    """List order statuses"""
    return {
        'statuses': [
            {'value': 'DRAFT', 'label': 'Nacrt', 'description': 'Not yet sent'},
            {'value': 'SENT', 'label': 'Poslato', 'description': 'Awaiting seller confirmation'},
            {'value': 'CONFIRMED', 'label': 'Potvrđeno', 'description': 'Seller confirmed'},
            {'value': 'REJECTED', 'label': 'Odbijeno', 'description': 'Seller rejected'},
            {'value': 'SHIPPED', 'label': 'Poslato', 'description': 'In transit'},
            {'value': 'DELIVERED', 'label': 'Isporučeno', 'description': 'Delivered'},
            {'value': 'COMPLETED', 'label': 'Završeno', 'description': 'Order complete'},
            {'value': 'CANCELLED', 'label': 'Otkazano', 'description': 'Cancelled'},
            {'value': 'DISPUTED', 'label': 'Sporno', 'description': 'Under dispute'}
        ]
    }
