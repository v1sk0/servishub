"""
Public Tickets API - Pracenje servisnih naloga za krajnje kupce.

Endpointi:
- GET /track/:token - Prati status naloga putem QR koda
- GET /track/:token/history - Istorija promena statusa

Token je 64-karakterni hex string generisan prilikom kreiranja naloga.
Ne zahteva autentifikaciju ali je rate-limited.
"""

from flask import Blueprint, request
from app.extensions import db
from app.models import ServiceTicket, Tenant, ServiceLocation

bp = Blueprint('public_tickets', __name__, url_prefix='/track')


# ============== Status Mapping ==============

STATUS_LABELS = {
    'RECEIVED': {'sr': 'Primljeno', 'en': 'Received', 'icon': 'inbox'},
    'DIAGNOSED': {'sr': 'Dijagnostifikovano', 'en': 'Diagnosed', 'icon': 'search'},
    'IN_PROGRESS': {'sr': 'U obradi', 'en': 'In Progress', 'icon': 'wrench'},
    'WAITING_PARTS': {'sr': 'Čeka delove', 'en': 'Waiting for Parts', 'icon': 'clock'},
    'READY': {'sr': 'Spremno za preuzimanje', 'en': 'Ready for Pickup', 'icon': 'check-circle'},
    'DELIVERED': {'sr': 'Isporučeno', 'en': 'Delivered', 'icon': 'truck'},
    'CANCELLED': {'sr': 'Otkazano', 'en': 'Cancelled', 'icon': 'x-circle'}
}

STATUS_ORDER = ['RECEIVED', 'DIAGNOSED', 'IN_PROGRESS', 'WAITING_PARTS', 'READY', 'DELIVERED']


# ============== Routes ==============

@bp.route('/<string:token>', methods=['GET'])
def track_ticket(token):
    """
    Prati status servisnog naloga putem tokena.

    Token se dobija:
    - Iz QR koda na potvrdi o prijemu
    - SMS-om nakon kreiranja naloga
    - Email-om

    Returns:
        - status: Trenutni status naloga
        - progress: Lista svih statusa sa indikacijom gde je nalog
        - service: Osnovni podaci o servisu
        - device: Podaci o uredjaju (bez lozinke)
        - warranty: Info o garanciji (ako je zatvoren)
    """
    if not token or len(token) != 64:
        return {'error': 'Invalid token'}, 400

    ticket = ServiceTicket.query.filter_by(access_token=token).first()

    if not ticket:
        return {'error': 'Ticket not found'}, 404

    # Get tenant and location info
    tenant = Tenant.query.get(ticket.tenant_id)
    location = ServiceLocation.query.get(ticket.location_id) if ticket.location_id else None

    # Build progress tracker
    current_status = ticket.status.value
    progress = []
    reached_current = False

    for status in STATUS_ORDER:
        is_current = status == current_status
        is_completed = not reached_current and not is_current

        if is_current:
            reached_current = True

        # Handle cancelled separately
        if current_status == 'CANCELLED' and status != 'CANCELLED':
            is_completed = False

        progress.append({
            'status': status,
            'label': STATUS_LABELS[status]['sr'],
            'label_en': STATUS_LABELS[status]['en'],
            'icon': STATUS_LABELS[status]['icon'],
            'is_current': is_current,
            'is_completed': is_completed
        })

    # Add cancelled if ticket is cancelled
    if current_status == 'CANCELLED':
        progress.append({
            'status': 'CANCELLED',
            'label': STATUS_LABELS['CANCELLED']['sr'],
            'label_en': STATUS_LABELS['CANCELLED']['en'],
            'icon': STATUS_LABELS['CANCELLED']['icon'],
            'is_current': True,
            'is_completed': False
        })

    # Warranty info
    warranty_info = None
    if ticket.closed_at and ticket.warranty_days:
        from datetime import datetime, timedelta
        warranty_end = ticket.closed_at + timedelta(days=ticket.warranty_days)
        days_left = (warranty_end - datetime.utcnow()).days
        warranty_info = {
            'days_total': ticket.warranty_days,
            'days_left': max(0, days_left),
            'expires_at': warranty_end.isoformat(),
            'is_active': days_left > 0
        }

    return {
        'ticket_number': ticket.ticket_number,
        'status': {
            'value': current_status,
            'label': STATUS_LABELS.get(current_status, {}).get('sr', current_status),
            'label_en': STATUS_LABELS.get(current_status, {}).get('en', current_status)
        },
        'progress': progress,
        'device': {
            'type': ticket.device_type,
            'brand': ticket.brand,
            'model': ticket.model,
            'imei': ticket.imei[-4:] if ticket.imei else None,  # Only last 4 digits
            'condition_grade': ticket.device_condition_grade,
            'condition_notes': ticket.device_condition_notes,
            'not_working': ticket.device_not_working,
            'service_section': ticket.service_section
        },
        'problem': ticket.problem_description,
        'notification_count': ticket.notification_count if hasattr(ticket, 'notification_count') else 0,
        'is_written_off': ticket.is_written_off if hasattr(ticket, 'is_written_off') else False,
        'diagnosis': ticket.diagnosis,
        'resolution': ticket.resolution if current_status in ['READY', 'DELIVERED'] else None,
        'price': {
            'estimated': float(ticket.estimated_price) if ticket.estimated_price else None,
            'final': float(ticket.final_price) if ticket.final_price and current_status in ['READY', 'DELIVERED'] else None,
            'currency': ticket.currency or 'RSD',
            'is_paid': ticket.is_paid
        },
        'warranty': warranty_info,
        'service': {
            'name': tenant.name if tenant else None,
            'location': {
                'name': location.name if location else None,
                'address': location.address if location else None,
                'city': location.city if location else None,
                'phone': location.phone if location else None
            } if location else None
        },
        'created_at': ticket.created_at.isoformat(),
        'updated_at': ticket.updated_at.isoformat()
    }


@bp.route('/<string:token>/qr', methods=['GET'])
def get_qr_data(token):
    """
    Vraca podatke za generisanje QR koda.

    Frontend koristi ove podatke da generiše QR kod koji kupac
    može skenirati da prati status.
    """
    if not token or len(token) != 64:
        return {'error': 'Invalid token'}, 400

    ticket = ServiceTicket.query.filter_by(access_token=token).first()

    if not ticket:
        return {'error': 'Ticket not found'}, 404

    # URL for tracking (frontend will use this)
    import os
    frontend_url = os.environ.get('FRONTEND_URL', 'https://servishub.rs')
    tracking_url = f"{frontend_url}/track/{token}"

    return {
        'ticket_number': ticket.ticket_number,
        'tracking_url': tracking_url,
        'token': token
    }


@bp.route('/<string:token>/receipt', methods=['GET'])
def get_receipt_data(token):
    """
    Vraca podatke za printanje potvrde o prijemu.

    Koristi se za generisanje PDF potvrde sa QR kodom.
    """
    if not token or len(token) != 64:
        return {'error': 'Invalid token'}, 400

    ticket = ServiceTicket.query.filter_by(access_token=token).first()

    if not ticket:
        return {'error': 'Ticket not found'}, 404

    tenant = Tenant.query.get(ticket.tenant_id)
    location = ServiceLocation.query.get(ticket.location_id) if ticket.location_id else None

    import os
    frontend_url = os.environ.get('FRONTEND_URL', 'https://servishub.rs')

    return {
        'ticket_number': ticket.ticket_number,
        'tracking_url': f"{frontend_url}/track/{token}",
        'customer': {
            'name': ticket.customer_name,
            'phone': ticket.customer_phone
        },
        'device': {
            'type': ticket.device_type,
            'brand': ticket.brand,
            'model': ticket.model,
            'imei': ticket.imei,
            'condition': ticket.device_condition
        },
        'problem': ticket.problem_description,
        'estimated_price': float(ticket.estimated_price) if ticket.estimated_price else None,
        'currency': ticket.currency or 'RSD',
        'service': {
            'name': tenant.name if tenant else None,
            'pib': tenant.pib if tenant else None,
            'address': tenant.adresa_sedista if tenant else None,
            'phone': tenant.telefon if tenant else None,
            'location': {
                'name': location.name,
                'address': location.address,
                'city': location.city,
                'phone': location.phone
            } if location else None
        },
        'created_at': ticket.created_at.isoformat(),
        'warranty_days': ticket.warranty_days or 30
    }
