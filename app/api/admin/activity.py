"""
Admin API - Audit Log aktivnosti.

Endpoint za pregled aktivnosti platform admina -
sve aktivacije, suspenzije, KYC verifikacije itd.
"""

from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify

from app.extensions import db
from app.models.admin_activity import AdminActivityLog, AdminActionType
from app.api.middleware.auth import platform_admin_required

bp = Blueprint('admin_activity', __name__, url_prefix='/activity')


@bp.route('', methods=['GET'])
@platform_admin_required
def list_activities():
    """
    Lista svih admin aktivnosti sa filterima i paginacijom.

    Query params:
        - page: broj stranice (default 1)
        - per_page: broj po stranici (default 50, max 100)
        - action_type: filter po tipu akcije (ACTIVATE_TRIAL, SUSPEND_TENANT, itd.)
        - target_type: filter po tipu entiteta (tenant, representative)
        - admin_id: filter po adminu koji je izvrsio akciju
        - from_date: od datuma (YYYY-MM-DD)
        - to_date: do datuma (YYYY-MM-DD)
    """
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 100)
    action_type = request.args.get('action_type')
    target_type = request.args.get('target_type')
    admin_id = request.args.get('admin_id', type=int)
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')

    # Bazni query
    query = AdminActivityLog.query

    # Filter po tipu akcije
    if action_type:
        try:
            action_enum = AdminActionType[action_type]
            query = query.filter(AdminActivityLog.action_type == action_enum)
        except KeyError:
            pass  # Ignorisi nevalidan tip

    # Filter po tipu entiteta
    if target_type:
        query = query.filter(AdminActivityLog.target_type == target_type)

    # Filter po adminu
    if admin_id:
        query = query.filter(AdminActivityLog.admin_id == admin_id)

    # Filter po datumskom opsegu
    if from_date:
        try:
            from_dt = datetime.strptime(from_date, '%Y-%m-%d')
            query = query.filter(AdminActivityLog.created_at >= from_dt)
        except ValueError:
            pass

    if to_date:
        try:
            to_dt = datetime.strptime(to_date, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(AdminActivityLog.created_at < to_dt)
        except ValueError:
            pass

    # Sortiranje - najnovije prvo
    query = query.order_by(AdminActivityLog.created_at.desc())

    # Paginacija
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    activities_data = [activity.to_dict() for activity in pagination.items]

    return jsonify({
        'activities': activities_data,
        'pagination': {
            'page': pagination.page,
            'per_page': pagination.per_page,
            'total': pagination.total,
            'pages': pagination.pages,
            'has_next': pagination.has_next,
            'has_prev': pagination.has_prev
        }
    }), 200


@bp.route('/stats', methods=['GET'])
@platform_admin_required
def activity_stats():
    """
    Statistika aktivnosti - broj akcija po tipu.
    """
    from sqlalchemy import func

    # Broj akcija po tipu
    action_counts = db.session.query(
        AdminActivityLog.action_type,
        func.count(AdminActivityLog.id)
    ).group_by(AdminActivityLog.action_type).all()

    stats = {
        action_type.value: count
        for action_type, count in action_counts
    }

    # Ukupan broj
    total = sum(stats.values())

    # Broj akcija danas
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = AdminActivityLog.query.filter(
        AdminActivityLog.created_at >= today_start
    ).count()

    # Broj akcija ove nedelje
    week_start = today_start - timedelta(days=today_start.weekday())
    week_count = AdminActivityLog.query.filter(
        AdminActivityLog.created_at >= week_start
    ).count()

    return jsonify({
        'by_type': stats,
        'total': total,
        'today': today_count,
        'this_week': week_count
    }), 200


@bp.route('/action-types', methods=['GET'])
@platform_admin_required
def get_action_types():
    """
    Vraća listu svih tipova akcija za filter dropdown.
    """
    types = [
        {
            'value': action_type.value,
            'label': _get_action_label(action_type)
        }
        for action_type in AdminActionType
    ]

    return jsonify({'action_types': types}), 200


def _get_action_label(action_type):
    """Pomocna funkcija za ljudski citljiv naziv akcije."""
    labels = {
        AdminActionType.ACTIVATE_TRIAL: 'Aktiviranje TRIAL-a',
        AdminActionType.ACTIVATE_SUBSCRIPTION: 'Aktiviranje pretplate',
        AdminActionType.SUSPEND_TENANT: 'Suspendovanje servisa',
        AdminActionType.UNSUSPEND_TENANT: 'Ukidanje suspenzije',
        AdminActionType.EXTEND_TRIAL: 'Produzenje TRIAL-a',
        AdminActionType.KYC_VERIFY: 'KYC verifikacija',
        AdminActionType.KYC_REJECT: 'KYC odbijanje',
        AdminActionType.KYC_REQUEST_RESUBMIT: 'Zahtev za ponovno slanje',
        AdminActionType.UPDATE_TENANT: 'Azuriranje servisa',
        AdminActionType.DELETE_TENANT: 'Brisanje servisa',
        AdminActionType.UPDATE_LOCATIONS: 'Promena lokacija',
    }
    return labels.get(action_type, action_type.value)
