"""
Admin API - Security Events.

Pregled bezbednosnih dogadjaja za administratore.
Omogucava pracenje login pokusaja, rate limit prekoracenja,
sumnjivih aktivnosti i drugih sigurnosnih eventova.
"""

from datetime import datetime, timedelta, timezone
from flask import Blueprint, jsonify, request
from sqlalchemy import func, desc

from app.extensions import db
from app.models.security_event import SecurityEvent, SecurityEventType, SecurityEventSeverity
from app.api.middleware.auth import platform_admin_required

bp = Blueprint('admin_security', __name__, url_prefix='/security')


@bp.route('/events', methods=['GET'])
@platform_admin_required
def list_security_events():
    """
    Lista svih security eventova sa filtrerima i paginacijom.

    Query params:
        - page: Broj stranice (default: 1)
        - per_page: Broj rezultata po stranici (default: 50, max: 100)
        - event_type: Filter po tipu eventa
        - severity: Filter po ozbiljnosti (info, warning, error, critical)
        - ip_address: Filter po IP adresi
        - user_id: Filter po user ID
        - hours: Filter za poslednjih X sati (default: 24)
        - search: Pretraga po IP, endpoint ili details

    Returns:
        200: Lista eventova sa paginacijom
    """
    # Paginacija
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 100)

    # Filteri
    event_type = request.args.get('event_type')
    severity = request.args.get('severity')
    ip_address = request.args.get('ip_address')
    user_id = request.args.get('user_id', type=int)
    hours = request.args.get('hours', 24, type=int)
    search = request.args.get('search')

    # Osnovni query
    query = SecurityEvent.query

    # Time filter
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    query = query.filter(SecurityEvent.created_at >= cutoff)

    # Apply filters
    if event_type:
        query = query.filter(SecurityEvent.event_type == event_type)

    if severity:
        query = query.filter(SecurityEvent.severity == severity)

    if ip_address:
        query = query.filter(SecurityEvent.ip_address == ip_address)

    if user_id:
        query = query.filter(SecurityEvent.user_id == user_id)

    if search:
        search_term = f'%{search}%'
        query = query.filter(
            db.or_(
                SecurityEvent.ip_address.ilike(search_term),
                SecurityEvent.endpoint.ilike(search_term),
                SecurityEvent.details.ilike(search_term)
            )
        )

    # Order by created_at desc
    query = query.order_by(desc(SecurityEvent.created_at))

    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'events': [e.to_dict() for e in pagination.items],
        'pagination': {
            'page': pagination.page,
            'per_page': pagination.per_page,
            'total': pagination.total,
            'pages': pagination.pages,
            'has_next': pagination.has_next,
            'has_prev': pagination.has_prev
        },
        'filters': {
            'hours': hours,
            'event_type': event_type,
            'severity': severity,
            'ip_address': ip_address,
            'user_id': user_id
        }
    }), 200


@bp.route('/events/stats', methods=['GET'])
@platform_admin_required
def get_security_stats():
    """
    Statistika security eventova.

    Query params:
        - hours: Period u satima (default: 24)

    Returns:
        200: Statistike eventova
    """
    hours = request.args.get('hours', 24, type=int)

    stats = SecurityEvent.get_stats(hours=hours)
    top_ips = SecurityEvent.get_top_ips(hours=hours, limit=10)

    return jsonify({
        'stats': stats,
        'top_ips': top_ips
    }), 200


@bp.route('/events/types', methods=['GET'])
@platform_admin_required
def get_event_types():
    """
    Lista svih tipova security eventova za filter dropdown.

    Returns:
        200: Lista event tipova
    """
    # Vraca sve atribute iz SecurityEventType klase
    event_types = [
        {'value': SecurityEventType.LOGIN_SUCCESS, 'label': 'Login Success', 'category': 'Auth'},
        {'value': SecurityEventType.LOGIN_FAILED, 'label': 'Login Failed', 'category': 'Auth'},
        {'value': SecurityEventType.LOGIN_LOCKED, 'label': 'Login Locked', 'category': 'Auth'},
        {'value': SecurityEventType.LOGOUT, 'label': 'Logout', 'category': 'Auth'},
        {'value': SecurityEventType.OAUTH_STARTED, 'label': 'OAuth Started', 'category': 'OAuth'},
        {'value': SecurityEventType.OAUTH_SUCCESS, 'label': 'OAuth Success', 'category': 'OAuth'},
        {'value': SecurityEventType.OAUTH_FAILED, 'label': 'OAuth Failed', 'category': 'OAuth'},
        {'value': SecurityEventType.OAUTH_CSRF_INVALID, 'label': 'OAuth CSRF Invalid', 'category': 'OAuth'},
        {'value': SecurityEventType.OAUTH_PKCE_INVALID, 'label': 'OAuth PKCE Invalid', 'category': 'OAuth'},
        {'value': SecurityEventType.TOKEN_REFRESH, 'label': 'Token Refresh', 'category': 'Token'},
        {'value': SecurityEventType.TOKEN_INVALID, 'label': 'Token Invalid', 'category': 'Token'},
        {'value': SecurityEventType.TOKEN_EXPIRED, 'label': 'Token Expired', 'category': 'Token'},
        {'value': SecurityEventType.RATE_LIMIT_EXCEEDED, 'label': 'Rate Limit Exceeded', 'category': 'Rate Limit'},
        {'value': SecurityEventType.TWO_FA_SETUP, 'label': '2FA Setup', 'category': '2FA'},
        {'value': SecurityEventType.TWO_FA_ENABLED, 'label': '2FA Enabled', 'category': '2FA'},
        {'value': SecurityEventType.TWO_FA_DISABLED, 'label': '2FA Disabled', 'category': '2FA'},
        {'value': SecurityEventType.TWO_FA_VERIFIED, 'label': '2FA Verified', 'category': '2FA'},
        {'value': SecurityEventType.TWO_FA_FAILED, 'label': '2FA Failed', 'category': '2FA'},
        {'value': SecurityEventType.TWO_FA_BACKUP_USED, 'label': '2FA Backup Used', 'category': '2FA'},
        {'value': SecurityEventType.SUSPICIOUS_IP, 'label': 'Suspicious IP', 'category': 'Suspicious'},
        {'value': SecurityEventType.BRUTE_FORCE_DETECTED, 'label': 'Brute Force Detected', 'category': 'Suspicious'},
        {'value': SecurityEventType.ADMIN_LOGIN_SUCCESS, 'label': 'Admin Login Success', 'category': 'Admin'},
        {'value': SecurityEventType.ADMIN_LOGIN_FAILED, 'label': 'Admin Login Failed', 'category': 'Admin'},
        {'value': SecurityEventType.ADMIN_ACTION, 'label': 'Admin Action', 'category': 'Admin'},
    ]

    return jsonify({
        'event_types': event_types
    }), 200


@bp.route('/events/severity-levels', methods=['GET'])
@platform_admin_required
def get_severity_levels():
    """
    Lista severity nivoa za filter dropdown.

    Returns:
        200: Lista severity nivoa
    """
    severity_levels = [
        {'value': SecurityEventSeverity.INFO.value, 'label': 'Info', 'color': 'blue'},
        {'value': SecurityEventSeverity.WARNING.value, 'label': 'Warning', 'color': 'yellow'},
        {'value': SecurityEventSeverity.ERROR.value, 'label': 'Error', 'color': 'red'},
        {'value': SecurityEventSeverity.CRITICAL.value, 'label': 'Critical', 'color': 'purple'},
    ]

    return jsonify({
        'severity_levels': severity_levels
    }), 200


@bp.route('/events/<int:event_id>', methods=['GET'])
@platform_admin_required
def get_security_event(event_id):
    """
    Detalji jednog security eventa.

    Args:
        event_id: ID eventa

    Returns:
        200: Detalji eventa
        404: Event nije pronadjen
    """
    event = SecurityEvent.query.get(event_id)

    if not event:
        return jsonify({
            'error': 'Not Found',
            'message': 'Security event nije pronadjen'
        }), 404

    return jsonify({
        'event': event.to_dict()
    }), 200


@bp.route('/events/by-ip/<ip_address>', methods=['GET'])
@platform_admin_required
def get_events_by_ip(ip_address):
    """
    Lista eventova za odredjenu IP adresu.

    Args:
        ip_address: IP adresa

    Query params:
        - hours: Period u satima (default: 24)
        - page: Broj stranice (default: 1)
        - per_page: Broj rezultata po stranici (default: 50)

    Returns:
        200: Lista eventova za IP
    """
    hours = request.args.get('hours', 24, type=int)
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 100)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    query = SecurityEvent.query.filter(
        SecurityEvent.ip_address == ip_address,
        SecurityEvent.created_at >= cutoff
    ).order_by(desc(SecurityEvent.created_at))

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    # Statistike za ovaj IP
    stats = {
        'total_events': pagination.total,
        'failed_logins': SecurityEvent.query.filter(
            SecurityEvent.ip_address == ip_address,
            SecurityEvent.created_at >= cutoff,
            SecurityEvent.event_type.in_(['login_failed', 'admin_login_failed'])
        ).count(),
        'rate_limits': SecurityEvent.query.filter(
            SecurityEvent.ip_address == ip_address,
            SecurityEvent.created_at >= cutoff,
            SecurityEvent.event_type == 'rate_limit_exceeded'
        ).count()
    }

    return jsonify({
        'ip_address': ip_address,
        'events': [e.to_dict() for e in pagination.items],
        'stats': stats,
        'pagination': {
            'page': pagination.page,
            'per_page': pagination.per_page,
            'total': pagination.total,
            'pages': pagination.pages
        }
    }), 200


@bp.route('/events/cleanup', methods=['POST'])
@platform_admin_required
def cleanup_old_events():
    """
    Brise stare security evente.
    Zahteva SUPER_ADMIN ulogu.

    Request body:
        - days: Broj dana nakon kojih se brisu eventi (min: 30)

    Returns:
        200: Broj obrisanih eventa
    """
    from flask import g

    # Samo SUPER_ADMIN moze brisati
    if not g.current_admin.is_super_admin():
        return jsonify({
            'error': 'Forbidden',
            'message': 'Samo SUPER_ADMIN moze brisati security evente'
        }), 403

    data = request.get_json() or {}
    days = data.get('days', 90)

    # Minimum 30 dana
    if days < 30:
        return jsonify({
            'error': 'Validation Error',
            'message': 'Minimum period za brisanje je 30 dana'
        }), 400

    deleted_count = SecurityEvent.cleanup_old_events(days=days)

    return jsonify({
        'message': f'Obrisano {deleted_count} starih security eventa',
        'deleted_count': deleted_count,
        'older_than_days': days
    }), 200
