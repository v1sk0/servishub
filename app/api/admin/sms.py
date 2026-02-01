"""
Admin SMS Management API - upravljanje SMS kvotama i analitika.

Endpointi za:
- Pregled SMS statistike platforme
- Upravljanje SMS limitima po tenantu
- Pregled SMS istorije i potrošnje
"""

from flask import Blueprint, request, jsonify, g
from pydantic import BaseModel, ValidationError
from typing import Optional
from datetime import datetime, timedelta

from ..middleware.auth import jwt_required, admin_required
from ...extensions import db
from ...models import (
    Tenant, TenantSmsConfig, TenantSmsUsage,
    get_platform_sms_stats, get_sms_stats_for_tenant
)
from ...models.admin_activity import AdminActivityLog, AdminActionType


bp = Blueprint('admin_sms', __name__, url_prefix='/sms')


class UpdateSmsConfigRequest(BaseModel):
    """Request za ažuriranje SMS konfiguracije tenanta."""
    sms_enabled: Optional[bool] = None
    monthly_limit: Optional[int] = None
    warning_threshold_percent: Optional[int] = None
    custom_sender_id: Optional[str] = None
    admin_notes: Optional[str] = None


# ===========================================================================
# PLATFORM STATISTICS
# ===========================================================================

@bp.route('/stats', methods=['GET'])
@jwt_required
@admin_required
def get_platform_stats():
    """
    Dohvata SMS statistiku za celu platformu.

    Query params:
        - days: Broj dana unazad (default 30)

    Returns:
        200: SMS statistika (ukupno, po tipu, top tenanti)
    """
    days = request.args.get('days', 30, type=int)
    days = min(max(days, 1), 365)  # Limit 1-365 dana

    stats = get_platform_sms_stats(days)

    # Dodaj imena tenanata u top_tenants
    if stats.get('top_tenants'):
        tenant_ids = [t['tenant_id'] for t in stats['top_tenants']]
        tenants = {t.id: t.name for t in Tenant.query.filter(Tenant.id.in_(tenant_ids)).all()}
        for item in stats['top_tenants']:
            item['tenant_name'] = tenants.get(item['tenant_id'], 'N/A')

    return jsonify(stats), 200


@bp.route('/stats/monthly', methods=['GET'])
@jwt_required
@admin_required
def get_monthly_stats():
    """
    Dohvata mesečnu statistiku SMS-ova za poslednjih 12 meseci.

    Returns:
        200: Lista sa mesečnom statistikom
    """
    from sqlalchemy import func, extract

    # Poslednjih 12 meseci
    results = db.session.query(
        extract('year', TenantSmsUsage.created_at).label('year'),
        extract('month', TenantSmsUsage.created_at).label('month'),
        func.count(TenantSmsUsage.id).label('total'),
        func.sum(func.cast(TenantSmsUsage.status == 'sent', db.Integer)).label('sent'),
        func.sum(func.cast(TenantSmsUsage.status == 'failed', db.Integer)).label('failed')
    ).filter(
        TenantSmsUsage.created_at >= datetime.utcnow() - timedelta(days=365)
    ).group_by(
        extract('year', TenantSmsUsage.created_at),
        extract('month', TenantSmsUsage.created_at)
    ).order_by(
        extract('year', TenantSmsUsage.created_at).desc(),
        extract('month', TenantSmsUsage.created_at).desc()
    ).limit(12).all()

    monthly = []
    for row in results:
        monthly.append({
            'year': int(row.year),
            'month': int(row.month),
            'total': row.total,
            'sent': row.sent or 0,
            'failed': row.failed or 0
        })

    return jsonify({'monthly': monthly}), 200


# ===========================================================================
# TENANT SMS CONFIGS
# ===========================================================================

@bp.route('/configs', methods=['GET'])
@jwt_required
@admin_required
def list_tenant_configs():
    """
    Lista svih tenant SMS konfiguracija sa trenutnom potrošnjom.

    Query params:
        - page: Broj stranice (default 1)
        - per_page: Po stranici (default 20, max 100)
        - search: Pretraga po imenu tenanta

    Returns:
        200: Paginirana lista SMS konfiguracija
    """
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)
    search = request.args.get('search', '').strip()

    # Query sve tenante sa njihovim SMS config-om
    query = db.session.query(Tenant, TenantSmsConfig).outerjoin(
        TenantSmsConfig, Tenant.id == TenantSmsConfig.tenant_id
    )

    if search:
        query = query.filter(Tenant.name.ilike(f'%{search}%'))

    query = query.order_by(Tenant.name)

    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    items = []
    for tenant, config in pagination.items:
        # Kreiraj config ako ne postoji
        if not config:
            config = TenantSmsConfig.get_or_create(tenant.id)

        item = {
            'tenant_id': tenant.id,
            'tenant_name': tenant.name,
            'tenant_status': tenant.status.value if tenant.status else None,
            'sms_enabled': config.sms_enabled,
            'monthly_limit': config.monthly_limit,
            'current_usage': config.get_current_month_usage(),
            'remaining': config.get_remaining(),
            'warning_threshold_percent': config.warning_threshold_percent,
            'custom_sender_id': config.custom_sender_id,
            'admin_notes': config.admin_notes,
            'updated_at': config.updated_at.isoformat() if config.updated_at else None
        }
        items.append(item)

    return jsonify({
        'items': items,
        'total': pagination.total,
        'pages': pagination.pages,
        'page': page,
        'per_page': per_page,
        'has_next': pagination.has_next,
        'has_prev': pagination.has_prev
    }), 200


@bp.route('/configs/<int:tenant_id>', methods=['GET'])
@jwt_required
@admin_required
def get_tenant_config(tenant_id):
    """
    Dohvata SMS konfiguraciju za specifičnog tenanta.

    Returns:
        200: SMS konfiguracija sa statistikom
        404: Tenant nije pronađen
    """
    tenant = Tenant.query.get(tenant_id)
    if not tenant:
        return jsonify({'error': 'Not Found', 'message': 'Tenant nije pronađen'}), 404

    config = TenantSmsConfig.get_or_create(tenant_id)
    stats = get_sms_stats_for_tenant(tenant_id, days=30)

    return jsonify({
        'config': config.to_dict(),
        'tenant': {
            'id': tenant.id,
            'name': tenant.name,
            'status': tenant.status.value if tenant.status else None
        },
        'stats': stats
    }), 200


@bp.route('/configs/<int:tenant_id>', methods=['PUT'])
@jwt_required
@admin_required
def update_tenant_config(tenant_id):
    """
    Ažurira SMS konfiguraciju za tenanta.

    Request body:
        - sms_enabled: Da li je SMS omogućen
        - monthly_limit: Mesečni limit (0 = neograničeno)
        - warning_threshold_percent: % kvote za upozorenje
        - custom_sender_id: Custom sender ID
        - admin_notes: Napomene admina

    Returns:
        200: Ažurirana konfiguracija
        400: Validation error
        404: Tenant nije pronađen
    """
    tenant = Tenant.query.get(tenant_id)
    if not tenant:
        return jsonify({'error': 'Not Found', 'message': 'Tenant nije pronađen'}), 404

    try:
        data = UpdateSmsConfigRequest(**request.get_json())
    except ValidationError as e:
        return jsonify({
            'error': 'Validation Error',
            'details': e.errors()
        }), 400

    config = TenantSmsConfig.get_or_create(tenant_id)
    old_values = config.to_dict()

    # Ažuriraj samo prosleđena polja
    updates = data.model_dump(exclude_unset=True)

    # Validacija
    if 'monthly_limit' in updates:
        if updates['monthly_limit'] < 0:
            return jsonify({'error': 'Invalid limit', 'message': 'Limit mora biti >= 0'}), 400

    if 'warning_threshold_percent' in updates:
        if not 0 <= updates['warning_threshold_percent'] <= 100:
            return jsonify({'error': 'Invalid threshold', 'message': 'Threshold mora biti 0-100'}), 400

    if 'custom_sender_id' in updates and updates['custom_sender_id']:
        if len(updates['custom_sender_id']) > 11:
            return jsonify({'error': 'Invalid sender ID', 'message': 'Sender ID max 11 karaktera'}), 400

    for key, value in updates.items():
        setattr(config, key, value)

    config.updated_at = datetime.utcnow()
    db.session.commit()

    # Admin activity log
    AdminActivityLog.log(
        action_type=AdminActionType.UPDATE_SETTINGS,
        target_type='sms_config',
        target_id=tenant_id,
        target_name=f'SMS Config: {tenant.name}',
        details={
            'old_values': old_values,
            'new_values': config.to_dict(),
            'changes': updates
        }
    )
    db.session.commit()

    return jsonify(config.to_dict()), 200


# ===========================================================================
# SMS USAGE LOG
# ===========================================================================

@bp.route('/usage', methods=['GET'])
@jwt_required
@admin_required
def list_sms_usage():
    """
    Lista SMS potrošnje sa filterima.

    Query params:
        - page: Broj stranice (default 1)
        - per_page: Po stranici (default 20, max 100)
        - tenant_id: Filter po tenantu
        - sms_type: Filter po tipu (TICKET_READY, OTP, etc.)
        - status: Filter po statusu (sent, failed)
        - days: Broj dana unazad (default 30)

    Returns:
        200: Paginirana lista SMS poruka
    """
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)
    tenant_id = request.args.get('tenant_id', type=int)
    sms_type = request.args.get('sms_type')
    status = request.args.get('status')
    days = request.args.get('days', 30, type=int)

    since = datetime.utcnow() - timedelta(days=days)

    query = TenantSmsUsage.query.filter(TenantSmsUsage.created_at >= since)

    if tenant_id:
        query = query.filter(TenantSmsUsage.tenant_id == tenant_id)
    if sms_type:
        query = query.filter(TenantSmsUsage.sms_type == sms_type)
    if status:
        query = query.filter(TenantSmsUsage.status == status)

    query = query.order_by(TenantSmsUsage.created_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    # Dohvati imena tenanata
    tenant_ids = list(set(u.tenant_id for u in pagination.items))
    tenants = {t.id: t.name for t in Tenant.query.filter(Tenant.id.in_(tenant_ids)).all()}

    items = []
    for usage in pagination.items:
        item = usage.to_dict()
        item['tenant_name'] = tenants.get(usage.tenant_id, 'N/A')
        items.append(item)

    return jsonify({
        'items': items,
        'total': pagination.total,
        'pages': pagination.pages,
        'page': page,
        'per_page': per_page,
        'has_next': pagination.has_next,
        'has_prev': pagination.has_prev
    }), 200


@bp.route('/usage/tenant/<int:tenant_id>', methods=['GET'])
@jwt_required
@admin_required
def get_tenant_usage(tenant_id):
    """
    Dohvata SMS potrošnju za specifičnog tenanta.

    Query params:
        - days: Broj dana unazad (default 30)
        - page: Broj stranice
        - per_page: Po stranici

    Returns:
        200: Statistika i lista SMS poruka
    """
    tenant = Tenant.query.get(tenant_id)
    if not tenant:
        return jsonify({'error': 'Not Found', 'message': 'Tenant nije pronađen'}), 404

    days = request.args.get('days', 30, type=int)
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)

    stats = get_sms_stats_for_tenant(tenant_id, days)

    since = datetime.utcnow() - timedelta(days=days)
    query = TenantSmsUsage.query.filter(
        TenantSmsUsage.tenant_id == tenant_id,
        TenantSmsUsage.created_at >= since
    ).order_by(TenantSmsUsage.created_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'tenant': {
            'id': tenant.id,
            'name': tenant.name
        },
        'stats': stats,
        'usage': {
            'items': [u.to_dict() for u in pagination.items],
            'total': pagination.total,
            'pages': pagination.pages,
            'page': page,
            'per_page': per_page
        }
    }), 200


# ===========================================================================
# BULK OPERATIONS
# ===========================================================================

@bp.route('/configs/bulk', methods=['PUT'])
@jwt_required
@admin_required
def bulk_update_configs():
    """
    Ažurira SMS konfiguraciju za više tenanata odjednom.

    Request body:
        - tenant_ids: Lista ID-jeva tenanata
        - sms_enabled: Da li je SMS omogućen (opciono)
        - monthly_limit: Mesečni limit (opciono)

    Returns:
        200: Broj ažuriranih
    """
    data = request.get_json() or {}
    tenant_ids = data.get('tenant_ids', [])

    if not tenant_ids:
        return jsonify({'error': 'Bad Request', 'message': 'Morate proslediti tenant_ids'}), 400

    updates = {}
    if 'sms_enabled' in data:
        updates['sms_enabled'] = data['sms_enabled']
    if 'monthly_limit' in data:
        if data['monthly_limit'] < 0:
            return jsonify({'error': 'Invalid limit'}), 400
        updates['monthly_limit'] = data['monthly_limit']

    if not updates:
        return jsonify({'error': 'Bad Request', 'message': 'Nema šta da se ažurira'}), 400

    count = 0
    for tid in tenant_ids:
        config = TenantSmsConfig.get_or_create(tid)
        for key, value in updates.items():
            setattr(config, key, value)
        config.updated_at = datetime.utcnow()
        count += 1

    db.session.commit()

    # Log
    AdminActivityLog.log(
        action_type=AdminActionType.UPDATE_SETTINGS,
        target_type='sms_config_bulk',
        target_id=0,
        target_name=f'Bulk SMS Config ({count} tenants)',
        details={
            'tenant_ids': tenant_ids,
            'updates': updates
        }
    )
    db.session.commit()

    return jsonify({
        'message': f'Ažurirano {count} konfiguracija',
        'updated_count': count
    }), 200


@bp.route('/reset-warnings', methods=['POST'])
@jwt_required
@admin_required
def reset_monthly_warnings():
    """
    Resetuje mesečne warning flagove za sve tenante.
    Poziva se početkom svakog meseca (ili ručno).

    Returns:
        200: Broj resetovanih
    """
    count = TenantSmsConfig.query.update({
        TenantSmsConfig.warning_sent_this_month: False
    })
    db.session.commit()

    return jsonify({
        'message': f'Resetovano {count} konfiguracija',
        'reset_count': count
    }), 200
