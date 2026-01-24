"""
Threads API - Threaded Messaging System.

Omogućava tenantima da:
- Pregledaju SYSTEM notifikacije (read-only)
- Kreiraju SUPPORT konverzacije sa podrškom
- Odgovaraju na poruke u threadovima
- Označe poruke kao pročitane

Thread tipovi:
- SYSTEM: Sistemske notifikacije (read-only) - npr. package changes
- SUPPORT: Tenant ↔ Admin podrška
- NETWORK: Tenant ↔ Tenant komunikacija (zahteva TenantConnection)
"""

from flask import Blueprint, request, g, jsonify
from datetime import datetime, timezone
from app.extensions import db
from app.models import (
    Tenant, TenantUser,
    MessageThread, ThreadParticipant, Message,
    ThreadType, ThreadStatus, HiddenByType
)
from app.api.middleware.auth import jwt_required, tenant_required
from app.services.security_service import SecurityEventLogger, rate_limit, RateLimits

bp = Blueprint('threads', __name__, url_prefix='/threads')


# =============================================================================
# Thread Endpoints
# =============================================================================

@bp.route('', methods=['GET'])
@jwt_required
@tenant_required
def get_threads():
    """
    Lista threadova za tenant.

    Query params:
        - type: filter po tipu (SYSTEM, SUPPORT, NETWORK)
        - status: filter po statusu (OPEN, PENDING, RESOLVED)
        - limit: broj rezultata (default 20, max 100)
        - offset: offset za paginaciju

    Returns:
        {
            threads: [...],
            total: int,
            unread_total: int,
            limit: int,
            offset: int
        }
    """
    tenant = g.current_tenant
    user = g.current_user

    thread_type = request.args.get('type')
    status = request.args.get('status')
    limit = min(request.args.get('limit', 20, type=int), 100)
    offset = request.args.get('offset', 0, type=int)

    # Base query - threads za ovaj tenant
    query = MessageThread.query.filter(
        MessageThread.tenant_id == tenant.id
    )

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

    # Order by last activity (newest first)
    query = query.order_by(
        MessageThread.last_reply_at.desc().nullsfirst(),
        MessageThread.created_at.desc()
    )

    # Total count
    total = query.count()

    # Paginate
    threads = query.offset(offset).limit(limit).all()

    # Calculate unread count per thread
    threads_data = []
    unread_total = 0

    for thread in threads:
        thread_dict = thread_to_dict(thread)
        unread = thread.get_unread_count('tenant_user', user.id)
        thread_dict['unread_count'] = unread
        unread_total += unread
        threads_data.append(thread_dict)

    return jsonify({
        'threads': threads_data,
        'total': total,
        'unread_total': unread_total,
        'limit': limit,
        'offset': offset
    })


@bp.route('/<int:thread_id>', methods=['GET'])
@jwt_required
@tenant_required
def get_thread(thread_id):
    """
    Detalji jednog threada.

    Automatski ažurira last_read_at za korisnika.
    """
    tenant = g.current_tenant
    user = g.current_user

    thread = MessageThread.query.filter(
        MessageThread.id == thread_id,
        MessageThread.tenant_id == tenant.id
    ).first()

    if not thread:
        return jsonify({'error': 'Thread not found'}), 404

    # Ažuriraj participant last_read
    participant = ThreadParticipant.query.filter_by(
        thread_id=thread.id,
        user_id=user.id
    ).first()

    if not participant:
        # Kreiraj participant ako ne postoji
        participant = ThreadParticipant(
            thread_id=thread.id,
            user_id=user.id,
            tenant_id=tenant.id,
            role='PARTICIPANT'
        )
        db.session.add(participant)

    participant.mark_read()
    db.session.commit()

    thread_dict = thread_to_dict(thread)
    thread_dict['unread_count'] = 0  # Upravo pročitano

    return jsonify({'thread': thread_dict})


@bp.route('', methods=['POST'])
@jwt_required
@tenant_required
@rate_limit(**RateLimits.THREAD_CREATE, endpoint_name='thread_create')
def create_thread():
    """
    Kreira novi SUPPORT thread.

    Body:
        {
            subject: string (required),
            body: string (required) - prva poruka,
            tags: array of strings (optional)
        }

    NAPOMENA: Tenant može kreirati samo SUPPORT threads.
    SYSTEM i NETWORK se kreiraju sistemski.
    """
    tenant = g.current_tenant
    user = g.current_user
    data = request.get_json() or {}

    subject = data.get('subject', '').strip()
    body = data.get('body', '').strip()
    tags = data.get('tags', [])

    # Validacija
    if not subject:
        return jsonify({'error': 'Subject je obavezan'}), 400
    if len(subject) > 200:
        return jsonify({'error': 'Subject ne sme biti duži od 200 karaktera'}), 400
    if not body:
        return jsonify({'error': 'Poruka je obavezna'}), 400
    if len(body) > 10000:
        return jsonify({'error': 'Poruka ne sme biti duža od 10000 karaktera'}), 400

    # Kreiraj SUPPORT thread
    thread = MessageThread.create_support_thread(
        tenant_id=tenant.id,
        subject=subject,
        tags=tags
    )
    db.session.flush()

    # Dodaj korisnika kao OWNER participant
    participant = ThreadParticipant(
        thread_id=thread.id,
        user_id=user.id,
        tenant_id=tenant.id,
        role='OWNER'
    )
    participant.mark_read()
    db.session.add(participant)

    # Kreiraj prvu poruku
    message = Message(
        thread_id=thread.id,
        sender_user_id=user.id,
        sender_tenant_id=tenant.id,
        body=body
    )
    db.session.add(message)

    # Update thread last_reply
    thread.record_reply()

    db.session.commit()

    # Audit log
    SecurityEventLogger.log_event(
        'thread_created',
        details={
            'thread_id': thread.id,
            'thread_type': 'SUPPORT',
            'subject': subject[:50]
        },
        user_id=user.id,
        tenant_id=tenant.id,
        user_type='tenant_user'
    )

    return jsonify({
        'message': 'Konverzacija kreirana',
        'thread': thread_to_dict(thread)
    }), 201


@bp.route('/<int:thread_id>/messages', methods=['GET'])
@jwt_required
@tenant_required
def get_thread_messages(thread_id):
    """
    Lista poruka u threadu.

    Query params:
        - limit: broj rezultata (default 50, max 100)
        - before_id: poruke starije od ovog ID-a (za infinite scroll)
        - after_id: poruke novije od ovog ID-a (za polling)
    """
    tenant = g.current_tenant

    thread = MessageThread.query.filter(
        MessageThread.id == thread_id,
        MessageThread.tenant_id == tenant.id
    ).first()

    if not thread:
        return jsonify({'error': 'Thread not found'}), 404

    limit = min(request.args.get('limit', 50, type=int), 100)
    before_id = request.args.get('before_id', type=int)
    after_id = request.args.get('after_id', type=int)

    # Base query - exclude hidden messages (za tenant)
    query = Message.query.filter(
        Message.thread_id == thread.id,
        Message.is_hidden == False
    )

    # Pagination
    if before_id:
        query = query.filter(Message.id < before_id)
    if after_id:
        query = query.filter(Message.id > after_id)

    # Order by created_at
    if after_id:
        # Za polling - najstarije prvo
        query = query.order_by(Message.created_at.asc())
    else:
        # Za scroll - najnovije prvo
        query = query.order_by(Message.created_at.desc())

    messages = query.limit(limit).all()

    # Reverse za prikaz (najstarije prvo)
    if not after_id:
        messages = list(reversed(messages))

    return jsonify({
        'messages': [message_to_dict(m) for m in messages],
        'thread_id': thread_id,
        'has_more': len(messages) == limit
    })


@bp.route('/<int:thread_id>/messages', methods=['POST'])
@jwt_required
@tenant_required
@rate_limit(**RateLimits.MESSAGE_SEND, endpoint_name='message_send')
def add_message(thread_id):
    """
    Dodaje poruku u thread (reply).

    Body:
        {
            body: string (required)
        }

    VAŽNO: SYSTEM threads su READ-ONLY - reply nije dozvoljen!
    """
    tenant = g.current_tenant
    user = g.current_user
    data = request.get_json() or {}

    thread = MessageThread.query.filter(
        MessageThread.id == thread_id,
        MessageThread.tenant_id == tenant.id
    ).first()

    if not thread:
        return jsonify({'error': 'Thread not found'}), 404

    # ENFORCE: SYSTEM threads su read-only
    if thread.is_read_only():
        return jsonify({
            'error': 'Forbidden',
            'message': 'Sistemske poruke su samo za čitanje'
        }), 403

    body = data.get('body', '').strip()

    # Validacija
    if not body:
        return jsonify({'error': 'Poruka je obavezna'}), 400
    if len(body) > 10000:
        return jsonify({'error': 'Poruka ne sme biti duža od 10000 karaktera'}), 400

    # Kreiraj poruku
    message = Message(
        thread_id=thread.id,
        sender_user_id=user.id,
        sender_tenant_id=tenant.id,
        body=body
    )
    db.session.add(message)

    # Update thread
    thread.record_reply()
    if thread.status == ThreadStatus.RESOLVED:
        thread.reopen()

    # Update participant last_read
    participant = ThreadParticipant.query.filter_by(
        thread_id=thread.id,
        user_id=user.id
    ).first()
    if participant:
        participant.mark_read()

    db.session.commit()

    return jsonify({
        'message': 'Poruka poslata',
        'data': message_to_dict(message)
    }), 201


@bp.route('/<int:thread_id>/status', methods=['PUT'])
@jwt_required
@tenant_required
def update_thread_status(thread_id):
    """
    Menja status threada.

    Body:
        {
            status: 'RESOLVED' | 'OPEN'
        }

    NAPOMENA: SYSTEM threads imaju uvek status RESOLVED.
    """
    tenant = g.current_tenant
    data = request.get_json() or {}

    thread = MessageThread.query.filter(
        MessageThread.id == thread_id,
        MessageThread.tenant_id == tenant.id
    ).first()

    if not thread:
        return jsonify({'error': 'Thread not found'}), 404

    # SYSTEM threads su uvek RESOLVED
    if thread.thread_type == ThreadType.SYSTEM:
        return jsonify({
            'error': 'Forbidden',
            'message': 'Status sistemskih poruka se ne može menjati'
        }), 403

    new_status = data.get('status')
    if new_status not in ['RESOLVED', 'OPEN']:
        return jsonify({'error': 'Status mora biti RESOLVED ili OPEN'}), 400

    if new_status == 'RESOLVED':
        thread.resolve()
    else:
        thread.reopen()

    db.session.commit()

    return jsonify({
        'message': f'Status promenjen na {new_status}',
        'thread': thread_to_dict(thread)
    })


@bp.route('/<int:thread_id>/read', methods=['PUT'])
@jwt_required
@tenant_required
def mark_thread_read(thread_id):
    """
    Označava sve poruke u threadu kao pročitane.
    """
    tenant = g.current_tenant
    user = g.current_user

    thread = MessageThread.query.filter(
        MessageThread.id == thread_id,
        MessageThread.tenant_id == tenant.id
    ).first()

    if not thread:
        return jsonify({'error': 'Thread not found'}), 404

    # Nađi ili kreiraj participant
    participant = ThreadParticipant.query.filter_by(
        thread_id=thread.id,
        user_id=user.id
    ).first()

    if not participant:
        participant = ThreadParticipant(
            thread_id=thread.id,
            user_id=user.id,
            tenant_id=tenant.id,
            role='PARTICIPANT'
        )
        db.session.add(participant)

    participant.mark_read()
    db.session.commit()

    return jsonify({
        'message': 'Thread označen kao pročitan',
        'thread_id': thread_id
    })


# =============================================================================
# Message Endpoints
# =============================================================================

@bp.route('/messages/<int:message_id>', methods=['PUT'])
@jwt_required
@tenant_required
def edit_message(message_id):
    """
    Edituje poruku (sa audit trail-om).

    Body:
        {
            body: string (required)
        }

    NAPOMENA: Samo sender može editovati svoju poruku.
    Originalna verzija se čuva u edit_history_json.
    """
    user = g.current_user
    tenant = g.current_tenant
    data = request.get_json() or {}

    message = Message.query.get(message_id)
    if not message:
        return jsonify({'error': 'Message not found'}), 404

    # Proveri da poruka pripada tenant-ovom threadu
    thread = message.thread
    if thread.tenant_id != tenant.id:
        return jsonify({'error': 'Message not found'}), 404

    # Proveri da je sender
    if message.sender_user_id != user.id:
        return jsonify({
            'error': 'Forbidden',
            'message': 'Možete editovati samo svoje poruke'
        }), 403

    # SYSTEM poruke se ne mogu editovati
    if thread.is_read_only():
        return jsonify({
            'error': 'Forbidden',
            'message': 'Sistemske poruke se ne mogu menjati'
        }), 403

    new_body = data.get('body', '').strip()
    if not new_body:
        return jsonify({'error': 'Poruka je obavezna'}), 400
    if len(new_body) > 10000:
        return jsonify({'error': 'Poruka ne sme biti duža od 10000 karaktera'}), 400

    # Edit sa audit trail
    message.edit(
        new_body=new_body,
        edited_by_id=user.id,
        edited_by_type=HiddenByType.TENANT
    )

    db.session.commit()

    # Audit log
    SecurityEventLogger.log_event(
        'message_edited',
        details={
            'message_id': message.id,
            'thread_id': thread.id,
            'edit_count': len(message.edit_history_json) if message.edit_history_json else 1
        },
        user_id=user.id,
        tenant_id=tenant.id,
        user_type='tenant_user'
    )

    return jsonify({
        'message': 'Poruka izmenjena',
        'data': message_to_dict(message)
    })


@bp.route('/messages/<int:message_id>', methods=['DELETE'])
@jwt_required
@tenant_required
def hide_message(message_id):
    """
    Sakriva poruku (soft delete).

    Query params:
        - reason: razlog sakrivanja (optional)

    NAPOMENA: Samo sender može sakriti svoju poruku.
    Poruka ostaje u bazi za audit, ali je is_hidden=True.
    """
    user = g.current_user
    tenant = g.current_tenant

    message = Message.query.get(message_id)
    if not message:
        return jsonify({'error': 'Message not found'}), 404

    # Proveri da poruka pripada tenant-ovom threadu
    thread = message.thread
    if thread.tenant_id != tenant.id:
        return jsonify({'error': 'Message not found'}), 404

    # Proveri da je sender
    if message.sender_user_id != user.id:
        return jsonify({
            'error': 'Forbidden',
            'message': 'Možete sakriti samo svoje poruke'
        }), 403

    # SYSTEM poruke se ne mogu sakriti
    if thread.is_read_only():
        return jsonify({
            'error': 'Forbidden',
            'message': 'Sistemske poruke se ne mogu sakriti'
        }), 403

    reason = request.args.get('reason', 'Tenant sakrio poruku')

    message.hide(
        hidden_by_id=user.id,
        hidden_by_type=HiddenByType.TENANT,
        reason=reason
    )

    db.session.commit()

    # Audit log
    SecurityEventLogger.log_event(
        'message_hidden',
        details={
            'message_id': message_id,
            'thread_id': thread.id,
            'reason': reason
        },
        user_id=user.id,
        tenant_id=tenant.id,
        user_type='tenant_user'
    )

    return jsonify({
        'message': 'Poruka sakrivena',
        'message_id': message_id
    })


# =============================================================================
# Helper Functions
# =============================================================================

def thread_to_dict(thread: MessageThread) -> dict:
    """Konvertuje thread u dictionary za API response."""
    # Dohvati poslednju poruku
    last_message = thread.messages.order_by(Message.created_at.desc()).first()

    return {
        'id': thread.id,
        'tenant_id': thread.tenant_id,
        'thread_type': thread.thread_type.value,
        'status': thread.status.value if thread.status else 'OPEN',
        'subject': thread.subject,
        'tags': thread.tags or [],
        'is_read_only': thread.is_read_only(),
        'assigned_to_id': thread.assigned_to_id,
        'first_response_at': thread.first_response_at.isoformat() if thread.first_response_at else None,
        'last_reply_at': thread.last_reply_at.isoformat() if thread.last_reply_at else None,
        'created_at': thread.created_at.isoformat() if thread.created_at else None,
        'resolved_at': thread.resolved_at.isoformat() if thread.resolved_at else None,
        'message_count': thread.messages.count(),
        'last_message_preview': last_message.body[:100] if last_message else None,
        'last_message_at': last_message.created_at.isoformat() if last_message else None
    }


def message_to_dict(message: Message) -> dict:
    """Konvertuje message u dictionary za API response."""
    return {
        'id': message.id,
        'thread_id': message.thread_id,
        'body': message.body,
        'category': message.category,
        'sender': {
            'type': get_sender_type(message),
            'id': message.sender_user_id or message.sender_admin_id or message.sender_tenant_id,
            'name': message.sender_name
        },
        'is_edited': message.is_edited,
        'edited_at': message.edited_at.isoformat() if message.edited_at else None,
        'edit_count': len(message.edit_history_json) if message.edit_history_json else 0,
        'created_at': message.created_at.isoformat() if message.created_at else None
    }


def get_sender_type(message: Message) -> str:
    """Vraća tip pošiljaoca."""
    if message.sender_admin_id:
        return 'admin'
    elif message.sender_user_id:
        return 'user'
    elif message.sender_tenant_id:
        return 'tenant'
    return 'system'