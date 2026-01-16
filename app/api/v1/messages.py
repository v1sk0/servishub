"""
Messages API - Sistem poruka za tenante.

Omogućava tenantima da:
- Pregledaju svoje poruke (sistemske, admin)
- Označe poruke kao pročitane
- Obrišu poruke (soft delete)
- Dobiju broj nepročitanih poruka
"""

from flask import Blueprint, request, g
from app.extensions import db
from app.models import Tenant, TenantMessage
from app.models.tenant_message import MessageCategory, MessagePriority
from app.api.middleware.auth import jwt_required
from datetime import datetime

bp = Blueprint('messages', __name__, url_prefix='/messages')


@bp.route('', methods=['GET'])
@jwt_required
def get_messages():
    """
    Lista poruka za tenant.

    Query params:
        - category: filter po kategoriji (BILLING, SYSTEM, SUPPORT, etc.)
        - unread_only: true/false - samo nepročitane
        - limit: broj rezultata (default 20, max 100)
        - offset: offset za paginaciju
    """
    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    category = request.args.get('category')
    unread_only = request.args.get('unread_only', 'false').lower() == 'true'
    limit = min(request.args.get('limit', 20, type=int), 100)
    offset = request.args.get('offset', 0, type=int)

    # Base query - exclude deleted
    query = TenantMessage.query.filter(
        TenantMessage.tenant_id == tenant.id,
        TenantMessage.is_deleted == False
    )

    # Filter by category
    if category:
        try:
            cat_enum = MessageCategory(category)
            query = query.filter(TenantMessage.category == cat_enum)
        except ValueError:
            pass  # Invalid category, ignore filter

    # Filter unread only
    if unread_only:
        query = query.filter(TenantMessage.is_read == False)

    # Order by created_at desc (newest first)
    query = query.order_by(TenantMessage.created_at.desc())

    # Total count
    total = query.count()

    # Paginate
    messages = query.offset(offset).limit(limit).all()

    return {
        'messages': [m.to_dict() for m in messages],
        'total': total,
        'limit': limit,
        'offset': offset,
        'unread_count': TenantMessage.get_unread_count(tenant.id)
    }


@bp.route('/unread-count', methods=['GET'])
@jwt_required
def get_unread_count():
    """
    Broj nepročitanih poruka.

    Koristi se za badge na ikoni notifikacija.
    """
    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    count = TenantMessage.get_unread_count(tenant.id)

    return {'unread_count': count}


@bp.route('/<int:message_id>', methods=['GET'])
@jwt_required
def get_message(message_id):
    """
    Detalji jedne poruke.

    Automatski označava poruku kao pročitanu.
    """
    from app.models import TenantUser

    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    message = TenantMessage.query.filter(
        TenantMessage.id == message_id,
        TenantMessage.tenant_id == tenant.id,
        TenantMessage.is_deleted == False
    ).first()

    if not message:
        return {'error': 'Message not found'}, 404

    # Označi kao pročitano
    if not message.is_read:
        message.mark_as_read(user_id=g.user_id)
        db.session.commit()

    return {'message': message.to_dict()}


@bp.route('/<int:message_id>/read', methods=['PUT'])
@jwt_required
def mark_as_read(message_id):
    """
    Označi poruku kao pročitanu.
    """
    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    message = TenantMessage.query.filter(
        TenantMessage.id == message_id,
        TenantMessage.tenant_id == tenant.id,
        TenantMessage.is_deleted == False
    ).first()

    if not message:
        return {'error': 'Message not found'}, 404

    message.mark_as_read(user_id=g.user_id)
    db.session.commit()

    return {'message': 'Poruka označena kao pročitana', 'id': message_id}


@bp.route('/mark-all-read', methods=['PUT'])
@jwt_required
def mark_all_as_read():
    """
    Označi sve poruke kao pročitane.
    """
    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    # Update all unread messages
    updated = TenantMessage.query.filter(
        TenantMessage.tenant_id == tenant.id,
        TenantMessage.is_read == False,
        TenantMessage.is_deleted == False
    ).update({
        'is_read': True,
        'read_at': datetime.utcnow(),
        'read_by_user_id': g.user_id
    })

    db.session.commit()

    return {
        'message': f'{updated} poruka označeno kao pročitano',
        'updated_count': updated
    }


@bp.route('/<int:message_id>', methods=['DELETE'])
@jwt_required
def delete_message(message_id):
    """
    Obriši poruku (soft delete).
    """
    tenant = Tenant.query.get(g.tenant_id)
    if not tenant:
        return {'error': 'Tenant not found'}, 404

    message = TenantMessage.query.filter(
        TenantMessage.id == message_id,
        TenantMessage.tenant_id == tenant.id,
        TenantMessage.is_deleted == False
    ).first()

    if not message:
        return {'error': 'Message not found'}, 404

    message.soft_delete()
    db.session.commit()

    return {'message': 'Poruka obrisana', 'id': message_id}
