"""
Admin Notifications API - Upravljanje notification podesavanjima.

Endpointi za konfigurisanje email/SMS notifikacija i pregled loga.
"""

from flask import Blueprint, request, jsonify, g
from pydantic import BaseModel, ValidationError, EmailStr
from typing import Optional, List
from datetime import datetime

from ..middleware.auth import jwt_required, admin_required
from ...models import AdminNotificationSettings, NotificationLog
from ...models.admin_activity import AdminActivityLog, AdminActionType
from ...services.notification_service import notification_service
from ...extensions import db


bp = Blueprint('admin_notifications', __name__, url_prefix='/notifications')


class UpdateNotificationSettingsRequest(BaseModel):
    """Request za azuriranje notification settings-a."""
    # Primaoci
    email_recipients: Optional[List[str]] = None
    sms_recipients: Optional[List[str]] = None

    # Security events
    notify_failed_login: Optional[bool] = None
    notify_new_device: Optional[bool] = None
    notify_password_change: Optional[bool] = None
    notify_2fa_disabled: Optional[bool] = None
    notify_suspicious: Optional[bool] = None

    # Billing events
    notify_new_payment: Optional[bool] = None
    notify_payment_overdue: Optional[bool] = None
    notify_suspension: Optional[bool] = None
    notify_expiring: Optional[bool] = None

    # System events
    notify_new_tenant: Optional[bool] = None
    notify_kyc_submitted: Optional[bool] = None
    notify_daily_summary: Optional[bool] = None
    notify_weekly_report: Optional[bool] = None

    # Thresholds
    failed_login_threshold: Optional[int] = None
    overdue_days_threshold: Optional[int] = None


@bp.route('/settings', methods=['GET'])
@jwt_required
@admin_required
def get_notification_settings():
    """
    Dohvata notification podesavanja.

    Returns:
        200: Notification settings
    """
    settings = AdminNotificationSettings.get_settings()
    return jsonify(settings.to_dict()), 200


@bp.route('/settings', methods=['PUT'])
@jwt_required
@admin_required
def update_notification_settings():
    """
    Azurira notification podesavanja.

    Request body:
        - email_recipients: Lista email adresa
        - notify_*: Boolean za svaki tip notifikacije
        - failed_login_threshold: Broj pokusaja pre notifikacije
        - overdue_days_threshold: Dana kasnjenja za notifikaciju

    Returns:
        200: Azurirana podesavanja
        400: Validation error
    """
    try:
        data = UpdateNotificationSettingsRequest(**request.get_json())
    except ValidationError as e:
        return jsonify({
            'error': 'Validation Error',
            'details': e.errors()
        }), 400

    # Dohvati settings
    settings = AdminNotificationSettings.get_settings()
    old_values = settings.to_dict()

    # Azuriraj samo polja koja su poslata
    updates = data.model_dump(exclude_unset=True)

    # Validiraj email adrese
    if 'email_recipients' in updates:
        for email in updates['email_recipients']:
            if '@' not in email:
                return jsonify({
                    'error': 'Invalid email address',
                    'details': f'{email} nije validna email adresa'
                }), 400

    for key, value in updates.items():
        setattr(settings, key, value)

    settings.updated_at = datetime.utcnow()
    db.session.commit()

    # Log izmenu
    AdminActivityLog.log(
        action_type=AdminActionType.UPDATE_SETTINGS,
        target_type='notification_settings',
        target_id=settings.id,
        target_name='Notification Settings',
        details={
            'old_values': old_values,
            'new_values': settings.to_dict(),
            'changes': updates
        }
    )
    db.session.commit()

    return jsonify(settings.to_dict()), 200


@bp.route('/log', methods=['GET'])
@jwt_required
@admin_required
def get_notification_log():
    """
    Dohvata log notifikacija sa paginacijom i filterima.

    Query params:
        - page: Broj stranice (default 1)
        - per_page: Stavki po stranici (default 20, max 100)
        - type: Filter po tipu notifikacije
        - status: Filter po statusu (sent, failed, pending)
        - tenant_id: Filter po tenant-u

    Returns:
        200: Paginirani log notifikacija
    """
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)
    notification_type = request.args.get('type')
    status = request.args.get('status')
    tenant_id = request.args.get('tenant_id', type=int)

    # Build query
    query = NotificationLog.query

    if notification_type:
        query = query.filter(NotificationLog.notification_type == notification_type)
    if status:
        query = query.filter(NotificationLog.status == status)
    if tenant_id:
        query = query.filter(NotificationLog.related_tenant_id == tenant_id)

    # Order by newest first
    query = query.order_by(NotificationLog.created_at.desc())

    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'items': [item.to_dict() for item in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'page': page,
        'per_page': per_page,
        'has_next': pagination.has_next,
        'has_prev': pagination.has_prev
    }), 200


@bp.route('/test', methods=['POST'])
@jwt_required
@admin_required
def send_test_notification():
    """
    Salje test notifikaciju na konfigurisane email adrese.

    Returns:
        200: Test uspesno poslat
        400: Nema konfigurisanih primalaca
    """
    settings = AdminNotificationSettings.get_settings()
    recipients = settings.get_recipients('email')

    if not recipients:
        return jsonify({
            'error': 'Nema konfigurisanih email primalaca',
            'message': 'Dodajte bar jednu email adresu u podesavanjima'
        }), 400

    # Posalji test email direktno (zaobilazi idempotency)
    admin = g.current_admin
    subject = "[TEST] ServisHub Admin Notification"
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: #10b981; padding: 20px; border-radius: 10px 10px 0 0; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 20px;">Test Notification</h1>
        </div>
        <div style="background: #f9fafb; padding: 25px; border: 1px solid #e5e7eb;">
            <h2 style="margin-top: 0; font-size: 18px;">Test uspešan!</h2>
            <p>Ovo je test notifikacija iz ServisHub Admin panela.</p>
            <table style="width: 100%; border-collapse: collapse; margin-top: 15px;">
                <tr><td style="padding: 8px 0; color: #6b7280;">Poslao:</td><td style="padding: 8px 0; text-align: right;">{admin.email}</td></tr>
                <tr><td style="padding: 8px 0; color: #6b7280;">Vreme:</td><td style="padding: 8px 0; text-align: right;">{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</td></tr>
                <tr><td style="padding: 8px 0; color: #6b7280;">Primaoci:</td><td style="padding: 8px 0; text-align: right;">{len(recipients)}</td></tr>
            </table>
        </div>
    </body>
    </html>
    """
    text = f"Test Notification\n\nOvo je test iz ServisHub Admin panela.\nPoslao: {admin.email}"

    success, error = notification_service._send_email_with_retry(
        recipients, subject, html, text
    )

    # Log
    notification_service._log_notification(
        notification_type='TEST',
        recipient=', '.join(recipients),
        subject=subject,
        content=text,
        status='sent' if success else 'failed',
        event_key=f"TEST:{datetime.utcnow().isoformat()}",
        payload={'admin_email': admin.email, 'recipients': recipients},
        error_message=error,
        admin_id=admin.id
    )

    if success:
        return jsonify({
            'message': 'Test notifikacija uspešno poslata',
            'recipients': recipients
        }), 200
    else:
        return jsonify({
            'error': 'Slanje nije uspelo',
            'details': error
        }), 500


@bp.route('/stats', methods=['GET'])
@jwt_required
@admin_required
def get_notification_stats():
    """
    Dohvata statistiku notifikacija.

    Returns:
        200: Statistika (ukupno, po tipu, po statusu)
    """
    from sqlalchemy import func

    # Ukupno
    total = NotificationLog.query.count()

    # Po statusu
    status_counts = db.session.query(
        NotificationLog.status,
        func.count(NotificationLog.id)
    ).group_by(NotificationLog.status).all()

    # Po tipu (top 10)
    type_counts = db.session.query(
        NotificationLog.notification_type,
        func.count(NotificationLog.id)
    ).group_by(NotificationLog.notification_type).order_by(
        func.count(NotificationLog.id).desc()
    ).limit(10).all()

    return jsonify({
        'total': total,
        'by_status': {status: count for status, count in status_counts},
        'by_type': {ntype: count for ntype, count in type_counts}
    }), 200
