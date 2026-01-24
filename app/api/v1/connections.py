"""
Connections API - Tenant-to-Tenant Networking.

Omogućava tenantima da:
- Kreiraju invite linkove
- Prihvate invite od drugih servisa
- Upravljaju konekcijama (dozvole, block)
- Vide listu povezanih servisa

SIGURNOST:
- Rate limit: max 10 invite-ova dnevno
- Token se vraća SAMO jednom pri kreiranju
- 2-step approval flow opciono
"""

from flask import Blueprint, request, jsonify, g
from datetime import datetime, timezone, timedelta
from sqlalchemy import or_
from app.extensions import db
from app.models import (
    Tenant, TenantUser,
    Invite, TenantConnection, ConnectionStatus
)
from app.api.middleware.auth import jwt_required, tenant_required
from app.services.security_service import SecurityEventLogger, SecurityEventType, rate_limit, RateLimits

bp = Blueprint('connections', __name__, url_prefix='/connections')

# Rate limits
MAX_INVITES_PER_DAY = 10
MAX_MESSAGES_TO_NEW_CONNECTION_24H = 20


# =============================================================================
# Invite Endpoints
# =============================================================================

@bp.route('/invites', methods=['POST'])
@jwt_required
@tenant_required
def create_invite():
    """
    Kreira novi invite link.

    Body:
        {
            message: string (optional) - Poruka uz invite,
            max_uses: int (optional, default 1) - Maksimalan broj korišćenja,
            expires_in_days: int (optional, default 7) - Za koliko dana ističe
        }

    Returns:
        {
            invite: {...},
            token: string - ČUVAJ OVO! Token se vraća SAMO JEDNOM!
        }

    Rate limit: Max 10 invite-ova dnevno.
    """
    tenant = g.current_tenant
    user = g.current_user
    data = request.get_json() or {}

    # Rate limit check
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = Invite.query.filter(
        Invite.created_by_tenant_id == tenant.id,
        Invite.created_at >= today_start
    ).count()

    if today_count >= MAX_INVITES_PER_DAY:
        return jsonify({
            'error': 'Rate limit exceeded',
            'message': f'Možete kreirati maksimalno {MAX_INVITES_PER_DAY} poziva dnevno'
        }), 429

    # Parse parameters
    message = data.get('message', '').strip() or None
    max_uses = min(data.get('max_uses', 1), 100)  # Max 100 uses
    expires_in_days = min(data.get('expires_in_days', 7), 30)  # Max 30 days

    # Create invite
    invite, plaintext_token = Invite.create(
        tenant_id=tenant.id,
        user_id=user.id,
        message=message,
        max_uses=max_uses,
        expires_in_days=expires_in_days
    )

    db.session.commit()

    # Audit log
    SecurityEventLogger.log_event(
        'invite_created',
        details={
            'invite_id': invite.id,
            'token_hint': invite.token_hint,
            'max_uses': max_uses,
            'expires_in_days': expires_in_days
        },
        user_id=user.id,
        tenant_id=tenant.id,
        user_type='tenant_user'
    )

    return jsonify({
        'message': 'Invite kreiran',
        'invite': invite_to_dict(invite),
        'token': plaintext_token  # VRAĆA SE SAMO JEDNOM!
    }), 201


@bp.route('/invites', methods=['GET'])
@jwt_required
@tenant_required
def list_invites():
    """
    Lista svih invite-ova koje je tenant kreirao.

    Query params:
        - active_only: true/false - samo aktivni (default true)
    """
    tenant = g.current_tenant
    active_only = request.args.get('active_only', 'true').lower() == 'true'

    query = Invite.query.filter(Invite.created_by_tenant_id == tenant.id)

    if active_only:
        now = datetime.now(timezone.utc)
        query = query.filter(
            Invite.revoked_at.is_(None),
            Invite.expires_at > now
        )

    invites = query.order_by(Invite.created_at.desc()).all()

    return jsonify({
        'invites': [invite_to_dict(i) for i in invites]
    })


@bp.route('/invites/<int:invite_id>/revoke', methods=['PUT'])
@jwt_required
@tenant_required
def revoke_invite(invite_id):
    """
    Poništava invite.

    Body:
        {
            reason: string (optional)
        }
    """
    tenant = g.current_tenant
    data = request.get_json() or {}

    invite = Invite.query.filter(
        Invite.id == invite_id,
        Invite.created_by_tenant_id == tenant.id
    ).first()

    if not invite:
        return jsonify({'error': 'Invite not found'}), 404

    if invite.revoked_at:
        return jsonify({'error': 'Invite je već poništen'}), 400

    invite.revoke(reason=data.get('reason'))
    db.session.commit()

    # Audit log
    SecurityEventLogger.log_event(
        'invite_revoked',
        details={
            'invite_id': invite.id,
            'token_hint': invite.token_hint,
            'reason': data.get('reason')
        },
        user_id=g.current_user.id,
        tenant_id=tenant.id,
        user_type='tenant_user'
    )

    return jsonify({
        'message': 'Invite poništen',
        'invite': invite_to_dict(invite)
    })


@bp.route('/invites/accept', methods=['POST'])
@jwt_required
@tenant_required
@rate_limit(**RateLimits.INVITE_ACCEPT, endpoint_name='invite_accept')
def accept_invite():
    """
    Prihvata invite i kreira/ažurira konekciju.

    Body:
        {
            token: string (required) - Invite token
        }

    Flow:
    1. Validira token
    2. Proverava da nije self-connect
    3. Kreira/ažurira TenantConnection
    4. Označava invite kao iskorišćen
    """
    tenant = g.current_tenant
    data = request.get_json() or {}

    token = data.get('token', '').strip()
    if not token:
        return jsonify({'error': 'Token je obavezan'}), 400

    # Find invite
    invite = Invite.find_by_token(token)
    if not invite:
        # Log invalid token attempt
        SecurityEventLogger.log_event(
            'invite_invalid',
            details={
                'reason': 'token_not_found',
                'token_prefix': token[:6] if len(token) >= 6 else token
            },
            user_id=g.current_user.id,
            tenant_id=tenant.id,
            user_type='tenant_user',
            level='warning'
        )
        return jsonify({'error': 'Nevažeći poziv'}), 404

    # Validate
    error = invite.get_validation_error()
    if error:
        # Log validation failure
        SecurityEventLogger.log_event(
            'invite_invalid',
            details={
                'reason': 'validation_failed',
                'invite_id': invite.id,
                'token_hint': invite.token_hint,
                'error': error
            },
            user_id=g.current_user.id,
            tenant_id=tenant.id,
            user_type='tenant_user',
            level='warning'
        )
        return jsonify({'error': error}), 400

    # Can't connect to yourself
    if invite.created_by_tenant_id == tenant.id:
        return jsonify({'error': 'Ne možete se povezati sami sa sobom'}), 400

    # Check if already connected
    existing = TenantConnection.get_connection(tenant.id, invite.created_by_tenant_id)
    if existing:
        if existing.status == ConnectionStatus.ACTIVE:
            return jsonify({'error': 'Već ste povezani sa ovim servisom'}), 400
        if existing.status == ConnectionStatus.BLOCKED:
            return jsonify({'error': 'Konekcija sa ovim servisom je blokirana'}), 400

    # Create or update connection
    connection = TenantConnection.get_or_create(tenant.id, invite.created_by_tenant_id)
    connection.invite_id = invite.id
    connection.initiated_by_tenant_id = invite.created_by_tenant_id

    # Activate immediately (single-step flow)
    connection.activate()

    # Mark invite as used
    invite.use()

    db.session.commit()

    # Get inviter tenant info
    inviter = Tenant.query.get(invite.created_by_tenant_id)

    # Audit log - connection created
    SecurityEventLogger.log_event(
        'connection_created',
        details={
            'connection_id': connection.id,
            'invite_id': invite.id,
            'inviter_tenant_id': invite.created_by_tenant_id,
            'inviter_tenant_name': inviter.name if inviter else None
        },
        user_id=g.current_user.id,
        tenant_id=tenant.id,
        user_type='tenant_user'
    )

    return jsonify({
        'message': f'Povezani ste sa {inviter.name}!',
        'connection': connection.to_dict(tenant.id)
    })


# =============================================================================
# Connection Endpoints
# =============================================================================

@bp.route('', methods=['GET'])
@jwt_required
@tenant_required
def list_connections():
    """
    Lista svih konekcija za tenant.

    Query params:
        - status: ACTIVE, PENDING_INVITEE, PENDING_INVITER, BLOCKED
    """
    tenant = g.current_tenant
    status = request.args.get('status')

    query = TenantConnection.get_connections_for_tenant(tenant.id)

    if status:
        try:
            status_enum = ConnectionStatus(status)
            query = query.filter(TenantConnection.status == status_enum)
        except ValueError:
            pass

    connections = query.order_by(TenantConnection.created_at.desc()).all()

    return jsonify({
        'connections': [c.to_dict(tenant.id) for c in connections],
        'stats': {
            'active': sum(1 for c in connections if c.status == ConnectionStatus.ACTIVE),
            'pending': sum(1 for c in connections if c.status in [
                ConnectionStatus.PENDING_INVITEE, ConnectionStatus.PENDING_INVITER
            ]),
            'blocked': sum(1 for c in connections if c.status == ConnectionStatus.BLOCKED)
        }
    })


@bp.route('/<int:connection_id>', methods=['GET'])
@jwt_required
@tenant_required
def get_connection(connection_id):
    """
    Detalji jedne konekcije.
    """
    tenant = g.current_tenant

    connection = TenantConnection.query.get(connection_id)
    if not connection:
        return jsonify({'error': 'Connection not found'}), 404

    # Check access
    if connection.tenant_a_id != tenant.id and connection.tenant_b_id != tenant.id:
        return jsonify({'error': 'Connection not found'}), 404

    return jsonify({
        'connection': connection.to_dict(tenant.id)
    })


@bp.route('/<int:connection_id>/permissions', methods=['PUT'])
@jwt_required
@tenant_required
def update_permissions(connection_id):
    """
    Ažurira dozvole za konekciju.

    Body:
        {
            can_message: bool,
            can_share_contacts: bool,
            can_order_parts: bool
        }
    """
    tenant = g.current_tenant
    data = request.get_json() or {}

    connection = TenantConnection.query.get(connection_id)
    if not connection:
        return jsonify({'error': 'Connection not found'}), 404

    # Check access
    if connection.tenant_a_id != tenant.id and connection.tenant_b_id != tenant.id:
        return jsonify({'error': 'Connection not found'}), 404

    # Only active connections can have permissions changed
    if connection.status != ConnectionStatus.ACTIVE:
        return jsonify({'error': 'Konekcija mora biti aktivna za promenu dozvola'}), 400

    # Update permissions
    permissions = {}
    if 'can_message' in data:
        permissions['can_message'] = bool(data['can_message'])
    if 'can_share_contacts' in data:
        permissions['can_share_contacts'] = bool(data['can_share_contacts'])
    if 'can_order_parts' in data:
        permissions['can_order_parts'] = bool(data['can_order_parts'])

    # Get other tenant for logging
    other_tenant_id = connection.tenant_b_id if connection.tenant_a_id == tenant.id else connection.tenant_a_id

    connection.update_permissions(permissions)
    db.session.commit()

    # Audit log
    SecurityEventLogger.log_event(
        'connection_permissions_changed',
        details={
            'connection_id': connection.id,
            'target_tenant_id': other_tenant_id,
            'new_permissions': permissions
        },
        user_id=g.current_user.id,
        tenant_id=tenant.id,
        user_type='tenant_user'
    )

    return jsonify({
        'message': 'Dozvole ažurirane',
        'connection': connection.to_dict(tenant.id)
    })


@bp.route('/<int:connection_id>/block', methods=['PUT'])
@jwt_required
@tenant_required
@rate_limit(**RateLimits.CONNECTION_BLOCK, endpoint_name='connection_block')
def block_connection(connection_id):
    """
    Blokira konekciju.

    Body:
        {
            reason: string (optional)
        }

    NAPOMENA: BLOCKED status automatski blokira sve poruke i skriva threads.
    """
    tenant = g.current_tenant
    data = request.get_json() or {}

    connection = TenantConnection.query.get(connection_id)
    if not connection:
        return jsonify({'error': 'Connection not found'}), 404

    # Check access
    if connection.tenant_a_id != tenant.id and connection.tenant_b_id != tenant.id:
        return jsonify({'error': 'Connection not found'}), 404

    if connection.status == ConnectionStatus.BLOCKED:
        return jsonify({'error': 'Konekcija je već blokirana'}), 400

    # Get other tenant for logging
    other_tenant_id = connection.tenant_b_id if connection.tenant_a_id == tenant.id else connection.tenant_a_id

    connection.block(
        blocked_by_tenant_id=tenant.id,
        reason=data.get('reason')
    )
    db.session.commit()

    # Audit log
    SecurityEventLogger.log_event(
        'connection_blocked',
        details={
            'connection_id': connection.id,
            'blocked_tenant_id': other_tenant_id,
            'reason': data.get('reason')
        },
        user_id=g.current_user.id,
        tenant_id=tenant.id,
        user_type='tenant_user',
        level='warning'
    )

    return jsonify({
        'message': 'Konekcija blokirana',
        'connection': connection.to_dict(tenant.id)
    })


@bp.route('/<int:connection_id>/unblock', methods=['PUT'])
@jwt_required
@tenant_required
def unblock_connection(connection_id):
    """
    Deblokira konekciju.

    NAPOMENA: Samo onaj ko je blokirao može deblokirati.
    """
    tenant = g.current_tenant

    connection = TenantConnection.query.get(connection_id)
    if not connection:
        return jsonify({'error': 'Connection not found'}), 404

    # Check access
    if connection.tenant_a_id != tenant.id and connection.tenant_b_id != tenant.id:
        return jsonify({'error': 'Connection not found'}), 404

    if connection.status != ConnectionStatus.BLOCKED:
        return jsonify({'error': 'Konekcija nije blokirana'}), 400

    # Only the blocker can unblock
    if connection.blocked_by_tenant_id != tenant.id:
        return jsonify({
            'error': 'Forbidden',
            'message': 'Samo onaj ko je blokirao može deblokirati'
        }), 403

    # Get other tenant for logging
    other_tenant_id = connection.tenant_b_id if connection.tenant_a_id == tenant.id else connection.tenant_a_id

    connection.unblock()
    db.session.commit()

    # Audit log
    SecurityEventLogger.log_event(
        'connection_unblocked',
        details={
            'connection_id': connection.id,
            'unblocked_tenant_id': other_tenant_id
        },
        user_id=g.current_user.id,
        tenant_id=tenant.id,
        user_type='tenant_user'
    )

    return jsonify({
        'message': 'Konekcija deblokirana',
        'connection': connection.to_dict(tenant.id)
    })


@bp.route('/<int:connection_id>', methods=['DELETE'])
@jwt_required
@tenant_required
def delete_connection(connection_id):
    """
    Briše konekciju.

    NAPOMENA: Oba tenanta mogu obrisati konekciju.
    """
    tenant = g.current_tenant

    connection = TenantConnection.query.get(connection_id)
    if not connection:
        return jsonify({'error': 'Connection not found'}), 404

    # Check access
    if connection.tenant_a_id != tenant.id and connection.tenant_b_id != tenant.id:
        return jsonify({'error': 'Connection not found'}), 404

    # Get other tenant for logging
    other_tenant_id = connection.tenant_b_id if connection.tenant_a_id == tenant.id else connection.tenant_a_id
    connection_id = connection.id

    db.session.delete(connection)
    db.session.commit()

    # Audit log
    SecurityEventLogger.log_event(
        'connection_deleted',
        details={
            'connection_id': connection_id,
            'deleted_partner_tenant_id': other_tenant_id
        },
        user_id=g.current_user.id,
        tenant_id=tenant.id,
        user_type='tenant_user',
        level='warning'
    )

    return jsonify({
        'message': 'Konekcija obrisana'
    })


# =============================================================================
# Helper: Can message check
# =============================================================================

def can_message_connection(sender_tenant_id: int, receiver_tenant_id: int) -> tuple:
    """
    Proverava da li sender može da pošalje poruku receiver-u.

    Returns:
        Tuple (can_message: bool, error_message: str or None)
    """
    conn = TenantConnection.get_connection(sender_tenant_id, receiver_tenant_id)

    if not conn:
        return False, "Niste povezani sa ovim servisom"

    if conn.status == ConnectionStatus.BLOCKED:
        return False, "Konekcija je blokirana"

    if conn.status != ConnectionStatus.ACTIVE:
        return False, "Konekcija nije aktivna"

    if not conn.can_message():
        return False, "Nemate dozvolu za slanje poruka"

    # Rate limit za nove konekcije (prvih 24h)
    if conn.connected_at:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        if conn.connected_at > cutoff:
            from app.models import Message, MessageThread
            message_count = Message.query.join(MessageThread).filter(
                Message.sender_tenant_id == sender_tenant_id,
                MessageThread.connection_id == conn.id,
                Message.created_at > conn.connected_at
            ).count()

            if message_count >= MAX_MESSAGES_TO_NEW_CONNECTION_24H:
                return False, "Dostigli ste dnevni limit poruka za nove konekcije"

    return True, None


# =============================================================================
# Helper Functions
# =============================================================================

def invite_to_dict(invite: Invite) -> dict:
    """Konvertuje invite u dict za API."""
    return {
        'id': invite.id,
        'token_hint': invite.token_hint,
        'message': invite.message,
        'max_uses': invite.max_uses,
        'used_count': invite.used_count,
        'remaining_uses': max(0, invite.max_uses - invite.used_count),
        'expires_at': invite.expires_at.isoformat() if invite.expires_at else None,
        'is_valid': invite.is_valid(),
        'is_revoked': invite.revoked_at is not None,
        'revoked_reason': invite.revoked_reason,
        'created_at': invite.created_at.isoformat() if invite.created_at else None
    }