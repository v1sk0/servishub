"""
Admin Threads API - Support sistem za administratore.

Omogućava administratorima da:
- Pregledaju sve SUPPORT threadove
- Odgovaraju na poruke tenantima
- Dodeljuju threadove adminima
- Menjaju status threadova
- Vide SLA metriku

NAPOMENA: SYSTEM threads se ne mogu editovati (read-only za sve).
"""

from flask import Blueprint, request, jsonify, g
from datetime import datetime, timezone
from sqlalchemy import or_, and_
from app.extensions import db
from app.models import (
    Tenant, PlatformAdmin,
    MessageThread, ThreadParticipant, Message,
    ThreadType, ThreadStatus, HiddenByType
)
from app.api.middleware.auth import platform_admin_required
from app.services import typing_service

bp = Blueprint('admin_threads', __name__, url_prefix='/threads')


# =============================================================================
# Thread Endpoints
# =============================================================================

@bp.route('', methods=['GET'])
@platform_admin_required
def list_threads():
    """
    Lista svih threadova za admin dashboard.

    Query params:
        - type: SYSTEM, SUPPORT, NETWORK
        - status: OPEN, PENDING, RESOLVED
        - tenant_id: filter po tenantu
        - assigned_to_id: filter po dodeljenom adminu
        - unassigned: true - samo nedodeljeni
        - page: broj stranice (default 1)
        - per_page: broj po stranici (default 20, max 100)
    """
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)
    thread_type = request.args.get('type')
    status = request.args.get('status')
    tenant_id = request.args.get('tenant_id', type=int)
    assigned_to_id = request.args.get('assigned_to_id', type=int)
    unassigned = request.args.get('unassigned', 'false').lower() == 'true'

    query = MessageThread.query

    # Filter by type
    if thread_type:
        try:
            type_enum = ThreadType(thread_type)
            query = query.filter(MessageThread.thread_type == type_enum)
        except ValueError:
            pass

    # Filter by status
    if status:
        try:
            status_enum = ThreadStatus(status)
            query = query.filter(MessageThread.status == status_enum)
        except ValueError:
            pass

    # Filter by tenant
    if tenant_id:
        query = query.filter(MessageThread.tenant_id == tenant_id)

    # Filter by assigned admin
    if assigned_to_id:
        query = query.filter(MessageThread.assigned_to_id == assigned_to_id)
    elif unassigned:
        query = query.filter(MessageThread.assigned_to_id.is_(None))

    # Order by last activity (newest first), OPEN first
    query = query.order_by(
        MessageThread.status.asc(),  # OPEN first
        MessageThread.last_reply_at.desc().nullsfirst(),
        MessageThread.created_at.desc()
    )

    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    threads_data = []
    for thread in pagination.items:
        thread_dict = admin_thread_to_dict(thread)
        threads_data.append(thread_dict)

    # Stats
    open_count = MessageThread.query.filter(
        MessageThread.status == ThreadStatus.OPEN,
        MessageThread.thread_type == ThreadType.SUPPORT
    ).count()

    pending_count = MessageThread.query.filter(
        MessageThread.status == ThreadStatus.PENDING,
        MessageThread.thread_type == ThreadType.SUPPORT
    ).count()

    unassigned_count = MessageThread.query.filter(
        MessageThread.assigned_to_id.is_(None),
        MessageThread.status != ThreadStatus.RESOLVED,
        MessageThread.thread_type == ThreadType.SUPPORT
    ).count()

    return jsonify({
        'threads': threads_data,
        'pagination': {
            'page': pagination.page,
            'per_page': pagination.per_page,
            'total': pagination.total,
            'pages': pagination.pages
        },
        'stats': {
            'open': open_count,
            'pending': pending_count,
            'unassigned': unassigned_count
        }
    })


@bp.route('/<int:thread_id>', methods=['GET'])
@platform_admin_required
def get_thread(thread_id):
    """
    Detalji jednog threada za admina.
    """
    admin = g.current_admin

    thread = MessageThread.query.get(thread_id)
    if not thread:
        return jsonify({'error': 'Thread not found'}), 404

    # Ažuriraj admin participant
    participant = ThreadParticipant.query.filter_by(
        thread_id=thread.id,
        admin_id=admin.id
    ).first()

    if not participant:
        participant = ThreadParticipant(
            thread_id=thread.id,
            admin_id=admin.id,
            role='ADMIN'
        )
        db.session.add(participant)

    participant.mark_read()
    db.session.commit()

    return jsonify({'thread': admin_thread_to_dict(thread)})


@bp.route('/<int:thread_id>/messages', methods=['GET'])
@platform_admin_required
def get_thread_messages(thread_id):
    """
    Lista svih poruka u threadu (uključujući hidden za audit).

    Query params:
        - include_hidden: true - uključi sakrivene poruke
        - limit: broj rezultata (default 50, max 200)
        - after_id: samo poruke sa ID > after_id (za polling)
    """
    thread = MessageThread.query.get(thread_id)
    if not thread:
        return jsonify({'error': 'Thread not found'}), 404

    limit = min(request.args.get('limit', 50, type=int), 200)
    include_hidden = request.args.get('include_hidden', 'false').lower() == 'true'
    after_id = request.args.get('after_id', type=int)

    query = Message.query.filter(Message.thread_id == thread.id)

    if not include_hidden:
        query = query.filter(Message.is_hidden == False)

    # For polling - only get new messages
    if after_id:
        query = query.filter(Message.id > after_id)

    messages = query.order_by(Message.created_at.asc()).limit(limit).all()

    return jsonify({
        'messages': [admin_message_to_dict(m) for m in messages],
        'thread_id': thread_id
    })


@bp.route('/<int:thread_id>/messages', methods=['POST'])
@platform_admin_required
def add_admin_message(thread_id):
    """
    Admin odgovara na thread.

    Body:
        {
            body: string (required)
        }

    VAŽNO:
    - SYSTEM threads su READ-ONLY!
    - Ovaj reply beleži first_response_at za SLA
    """
    admin = g.current_admin
    data = request.get_json() or {}

    thread = MessageThread.query.get(thread_id)
    if not thread:
        return jsonify({'error': 'Thread not found'}), 404

    # SYSTEM threads su read-only
    if thread.is_read_only():
        return jsonify({
            'error': 'Forbidden',
            'message': 'SYSTEM threads su read-only'
        }), 403

    body = data.get('body', '').strip()
    if not body:
        return jsonify({'error': 'Poruka je obavezna'}), 400
    if len(body) > 10000:
        return jsonify({'error': 'Poruka ne sme biti duža od 10000 karaktera'}), 400

    # Kreiraj poruku
    message = Message(
        thread_id=thread.id,
        sender_admin_id=admin.id,
        body=body
    )
    db.session.add(message)

    # SLA tracking - beleži prvi admin odgovor
    thread.record_admin_response()

    # Auto-assign ako nije dodeljen
    if not thread.assigned_to_id:
        thread.assigned_to_id = admin.id

    # Status na PENDING (čeka tenant odgovor)
    thread.status = ThreadStatus.PENDING

    # Admin participant
    participant = ThreadParticipant.query.filter_by(
        thread_id=thread.id,
        admin_id=admin.id
    ).first()
    if not participant:
        participant = ThreadParticipant(
            thread_id=thread.id,
            admin_id=admin.id,
            role='ADMIN'
        )
        db.session.add(participant)
    participant.mark_read()

    db.session.commit()

    return jsonify({
        'message': 'Poruka poslata',
        'data': admin_message_to_dict(message)
    }), 201


@bp.route('/<int:thread_id>/assign', methods=['PUT'])
@platform_admin_required
def assign_thread(thread_id):
    """
    Dodeljuje thread adminu.

    Body:
        {
            admin_id: int (required, 0 za unassign)
        }
    """
    data = request.get_json() or {}
    admin_id = data.get('admin_id')

    if admin_id is None:
        return jsonify({'error': 'admin_id je obavezan'}), 400

    thread = MessageThread.query.get(thread_id)
    if not thread:
        return jsonify({'error': 'Thread not found'}), 404

    if admin_id == 0:
        thread.assigned_to_id = None
    else:
        admin = PlatformAdmin.query.get(admin_id)
        if not admin:
            return jsonify({'error': 'Admin not found'}), 404
        thread.assigned_to_id = admin_id

        # Dodaj admina kao participant
        participant = ThreadParticipant.query.filter_by(
            thread_id=thread.id,
            admin_id=admin_id
        ).first()
        if not participant:
            participant = ThreadParticipant(
                thread_id=thread.id,
                admin_id=admin_id,
                role='ADMIN'
            )
            db.session.add(participant)

    db.session.commit()

    return jsonify({
        'message': 'Thread dodeljen',
        'thread': admin_thread_to_dict(thread)
    })


@bp.route('/<int:thread_id>/status', methods=['PUT'])
@platform_admin_required
def update_thread_status(thread_id):
    """
    Menja status threada.

    Body:
        {
            status: 'OPEN' | 'PENDING' | 'RESOLVED'
        }
    """
    data = request.get_json() or {}
    new_status = data.get('status')

    if new_status not in ['OPEN', 'PENDING', 'RESOLVED']:
        return jsonify({'error': 'Nevažeći status'}), 400

    thread = MessageThread.query.get(thread_id)
    if not thread:
        return jsonify({'error': 'Thread not found'}), 404

    # SYSTEM threads su uvek RESOLVED
    if thread.thread_type == ThreadType.SYSTEM:
        return jsonify({
            'error': 'Forbidden',
            'message': 'SYSTEM threads su uvek RESOLVED'
        }), 403

    if new_status == 'RESOLVED':
        thread.resolve()
    elif new_status == 'OPEN':
        thread.reopen()
    else:
        thread.status = ThreadStatus(new_status)

    db.session.commit()

    return jsonify({
        'message': f'Status promenjen na {new_status}',
        'thread': admin_thread_to_dict(thread)
    })


@bp.route('/<int:thread_id>/tags', methods=['PUT'])
@platform_admin_required
def update_thread_tags(thread_id):
    """
    Ažurira tagove threada.

    Body:
        {
            tags: array of strings
        }
    """
    data = request.get_json() or {}
    tags = data.get('tags', [])

    if not isinstance(tags, list):
        return jsonify({'error': 'tags mora biti lista'}), 400

    thread = MessageThread.query.get(thread_id)
    if not thread:
        return jsonify({'error': 'Thread not found'}), 404

    thread.tags = tags
    db.session.commit()

    return jsonify({
        'message': 'Tagovi ažurirani',
        'thread': admin_thread_to_dict(thread)
    })


# =============================================================================
# Message Endpoints (Admin)
# =============================================================================

@bp.route('/messages/<int:message_id>/hide', methods=['PUT'])
@platform_admin_required
def admin_hide_message(message_id):
    """
    Admin sakriva poruku (za moderaciju).

    Body:
        {
            reason: string (required)
        }
    """
    admin = g.current_admin
    data = request.get_json() or {}

    message = Message.query.get(message_id)
    if not message:
        return jsonify({'error': 'Message not found'}), 404

    reason = data.get('reason', '').strip()
    if not reason:
        return jsonify({'error': 'Razlog je obavezan'}), 400

    message.hide(
        hidden_by_id=admin.id,
        hidden_by_type=HiddenByType.ADMIN,
        reason=reason
    )
    db.session.commit()

    return jsonify({
        'message': 'Poruka sakrivena',
        'message_id': message_id
    })


@bp.route('/messages/<int:message_id>/unhide', methods=['PUT'])
@platform_admin_required
def admin_unhide_message(message_id):
    """
    Admin vraća sakrivenu poruku.
    """
    message = Message.query.get(message_id)
    if not message:
        return jsonify({'error': 'Message not found'}), 404

    message.unhide()
    db.session.commit()

    return jsonify({
        'message': 'Poruka vraćena',
        'message_id': message_id
    })


# =============================================================================
# SLA Dashboard
# =============================================================================

@bp.route('/sla-metrics', methods=['GET'])
@platform_admin_required
def get_sla_metrics():
    """
    SLA metriku za dashboard.

    Vraća:
    - Prosečno vreme do prvog odgovora
    - Broj threadova bez odgovora > 24h
    - Threadovi po adminu
    """
    from sqlalchemy import func, extract
    from datetime import timedelta

    # Prosečno vreme do prvog odgovora (za threadove sa odgovorom)
    threads_with_response = MessageThread.query.filter(
        MessageThread.first_response_at.isnot(None),
        MessageThread.thread_type == ThreadType.SUPPORT
    ).all()

    if threads_with_response:
        total_response_time = sum(
            (t.first_response_at - t.created_at).total_seconds()
            for t in threads_with_response
        )
        avg_response_seconds = total_response_time / len(threads_with_response)
        avg_response_hours = round(avg_response_seconds / 3600, 1)
    else:
        avg_response_hours = 0

    # Threadovi bez odgovora > 24h
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    overdue_count = MessageThread.query.filter(
        MessageThread.first_response_at.is_(None),
        MessageThread.created_at < cutoff,
        MessageThread.status != ThreadStatus.RESOLVED,
        MessageThread.thread_type == ThreadType.SUPPORT
    ).count()

    # Threadovi po adminu
    threads_by_admin = db.session.query(
        PlatformAdmin.id,
        PlatformAdmin.full_name,
        func.count(MessageThread.id).label('thread_count')
    ).outerjoin(
        MessageThread, MessageThread.assigned_to_id == PlatformAdmin.id
    ).filter(
        PlatformAdmin.is_active == True
    ).group_by(
        PlatformAdmin.id, PlatformAdmin.full_name
    ).all()

    return jsonify({
        'avg_response_hours': avg_response_hours,
        'overdue_count': overdue_count,
        'threads_by_admin': [
            {'admin_id': a.id, 'admin_name': a.full_name, 'count': a.thread_count}
            for a in threads_by_admin
        ]
    })


# =============================================================================
# Typing Indicator Endpoints
# =============================================================================

@bp.route('/<int:thread_id>/typing', methods=['POST'])
@platform_admin_required
def set_admin_typing(thread_id):
    """
    Postavlja typing status za admina.
    Status istice posle 3 sekunde.

    Body:
        {
            typing: boolean (true = kuca, false = prestao)
        }
    """
    admin = g.current_admin
    data = request.get_json() or {}

    thread = MessageThread.query.get(thread_id)
    if not thread:
        return jsonify({'error': 'Thread not found'}), 404

    is_typing = data.get('typing', False)
    user_key = f"admin_{admin.id}"
    name = admin.full_name or admin.email.split('@')[0]

    typing_service.set_typing(thread_id, user_key, name, 'admin', is_typing)

    return jsonify({'status': 'ok'})


@bp.route('/<int:thread_id>/typing', methods=['GET'])
@platform_admin_required
def get_admin_typing(thread_id):
    """
    Vraća ko trenutno kuca u threadu.
    """
    admin = g.current_admin

    thread = MessageThread.query.get(thread_id)
    if not thread:
        return jsonify({'error': 'Thread not found'}), 404

    my_key = f"admin_{admin.id}"
    typing_users = typing_service.get_typing(thread_id, exclude_key=my_key)

    return jsonify({
        'typing': typing_users,
        'thread_id': thread_id
    })


# =============================================================================
# Helper Functions
# =============================================================================

def admin_thread_to_dict(thread: MessageThread) -> dict:
    """Konvertuje thread u dict za admin API."""
    tenant = Tenant.query.get(thread.tenant_id)
    assigned_admin = PlatformAdmin.query.get(thread.assigned_to_id) if thread.assigned_to_id else None
    last_message = thread.messages.order_by(Message.created_at.desc()).first()

    # SLA - vreme do prvog odgovora
    response_time_hours = None
    if thread.first_response_at and thread.created_at:
        response_time = thread.first_response_at - thread.created_at
        response_time_hours = round(response_time.total_seconds() / 3600, 1)

    return {
        'id': thread.id,
        'thread_type': thread.thread_type.value,
        'status': thread.status.value if thread.status else 'OPEN',
        'subject': thread.subject,
        'tags': thread.tags or [],
        'tenant': {
            'id': tenant.id,
            'name': tenant.name,
            'slug': tenant.slug
        } if tenant else None,
        'assigned_to': {
            'id': assigned_admin.id,
            'name': assigned_admin.full_name
        } if assigned_admin else None,
        'sla': {
            'first_response_at': thread.first_response_at.isoformat() if thread.first_response_at else None,
            'response_time_hours': response_time_hours,
            'is_waiting': thread.first_response_at is None and thread.status != ThreadStatus.RESOLVED
        },
        'last_reply_at': thread.last_reply_at.isoformat() if thread.last_reply_at else None,
        'created_at': thread.created_at.isoformat() if thread.created_at else None,
        'resolved_at': thread.resolved_at.isoformat() if thread.resolved_at else None,
        'message_count': thread.messages.count(),
        'last_message': {
            'preview': last_message.body[:100] if last_message else None,
            'sender': last_message.sender_name if last_message else None,
            'at': last_message.created_at.isoformat() if last_message else None
        } if last_message else None
    }


def admin_message_to_dict(message: Message) -> dict:
    """Konvertuje message u dict za admin API (uključuje hidden info)."""
    return {
        'id': message.id,
        'thread_id': message.thread_id,
        'body': message.body,
        'category': message.category,
        'sender': {
            'type': 'admin' if message.sender_admin_id else 'tenant',
            'id': message.sender_admin_id or message.sender_user_id or message.sender_tenant_id,
            'name': message.sender_name
        },
        'is_edited': message.is_edited,
        'edited_at': message.edited_at.isoformat() if message.edited_at else None,
        'edit_history': message.edit_history_json,
        'is_hidden': message.is_hidden,
        'hidden_at': message.hidden_at.isoformat() if message.hidden_at else None,
        'hidden_by_type': message.hidden_by_type.value if message.hidden_by_type else None,
        'hidden_reason': message.hidden_reason,
        'created_at': message.created_at.isoformat() if message.created_at else None
    }