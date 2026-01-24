"""
Public Tickets API - Pracenje servisnih naloga za krajnje kupce.

Endpointi:
- GET /track/:token - Prati status naloga putem QR koda ili broja naloga
- GET /track/:token/history - Istorija promena statusa

Token može biti:
- access_token (~43 karaktera, URL-safe base64) - generisan prilikom kreiranja naloga
- Broj naloga u formatu "SRV-XXXX" ili samo broj "XXXX" - traži se po tenant_id

Ne zahteva autentifikaciju ali je rate-limited.
"""

import re
from flask import Blueprint, request, g
from app.extensions import db
from app.models import ServiceTicket, Tenant, ServiceLocation
from app.services.security_service import rate_limit

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


# ============== Helper Functions ==============

def _parse_ticket_identifier(identifier):
    """
    Parsira identifikator naloga i vraća tip i vrednost.

    Formati:
    - access_token (secrets.token_urlsafe(32) = ~43 karaktera)
    - "SRV-0003" ili "srv-0003": ticket_number = 3
    - "3" ili "0003": ticket_number = 3

    Returns:
        tuple: (type, value) gde je type 'token' ili 'number'
    """
    if not identifier:
        return None, None

    identifier = identifier.strip()

    # access_token - secrets.token_urlsafe(32) generiše ~43 karaktera
    # Prihvatamo tokene između 40-50 karaktera koji su URL-safe base64
    if 40 <= len(identifier) <= 50:
        # Proveri da li je validan URL-safe base64 format
        if re.match(r'^[A-Za-z0-9_-]+$', identifier):
            return 'token', identifier

    # Format SRV-XXXX (case insensitive)
    srv_match = re.match(r'^SRV-?(\d+)$', identifier, re.IGNORECASE)
    if srv_match:
        return 'number', int(srv_match.group(1))

    # Samo broj
    if identifier.isdigit():
        return 'number', int(identifier)

    return None, None


# ============== Routes ==============

@bp.route('/<string:token>', methods=['GET'])
@rate_limit(max_requests=30, window_seconds=60, block_seconds=300, endpoint_name='public_track')
def track_ticket(token):
    """
    Prati status servisnog naloga putem tokena ili broja naloga.

    Token može biti:
    - access_token (~43 karaktera, iz QR koda, SMS-a ili email-a)
    - Broj naloga u formatu "SRV-0003" ili samo "3"

    Ako se koristi broj naloga, potreban je tenant_id parametar
    ili tenant kontekst iz subdomene (g.public_tenant).

    Returns:
        - status: Trenutni status naloga
        - progress: Lista svih statusa sa indikacijom gde je nalog
        - service: Osnovni podaci o servisu
        - device: Podaci o uredjaju (bez lozinke)
        - warranty: Info o garanciji (ako je zatvoren)
    """
    id_type, id_value = _parse_ticket_identifier(token)

    if id_type is None:
        return {'error': 'Invalid ticket identifier. Use ticket number (SRV-0003 or 3) or access token.'}, 400

    ticket = None

    if id_type == 'token':
        # Pretraga po access_token (originalni siguran način)
        ticket = ServiceTicket.query.filter_by(access_token=id_value).first()
    else:
        # Pretraga po ticket_number - zahteva verifikaciju telefonom
        tenant_id = request.args.get('tenant_id', type=int)
        phone_digits = request.args.get('phone', '').strip()

        # Validacija: potrebna su poslednja 4 broja telefona za sigurnost
        if not phone_digits or len(phone_digits) < 4:
            return {
                'error': 'Phone verification required',
                'message': 'Unesite poslednja 4 broja Vašeg telefona za verifikaciju.',
                'requires_phone': True
            }, 400

        # Ako nema tenant_id u parametrima, probaj iz g.public_tenant
        if not tenant_id and hasattr(g, 'public_tenant') and g.public_tenant:
            tenant_id = g.public_tenant.id

        if tenant_id:
            ticket = ServiceTicket.query.filter_by(
                tenant_id=tenant_id,
                ticket_number=id_value
            ).first()
        else:
            # Bez tenant konteksta, probaj naći jedinstven nalog
            tickets = ServiceTicket.query.filter_by(ticket_number=id_value).all()
            if len(tickets) == 1:
                ticket = tickets[0]
            elif len(tickets) > 1:
                return {
                    'error': 'Multiple tickets found with this number. Please use the full access token from your receipt.',
                    'hint': 'Scan the QR code on your receipt or use the link from SMS/email.'
                }, 400

        # Verifikacija telefona - poslednja 4 broja moraju da se poklope
        if ticket:
            customer_phone = (ticket.customer_phone or '').replace(' ', '').replace('-', '').replace('+', '')
            if not customer_phone or not customer_phone.endswith(phone_digits[-4:]):
                return {
                    'error': 'Phone verification failed',
                    'message': 'Broj telefona se ne poklapa sa podacima naloga.'
                }, 403

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
@rate_limit(max_requests=30, window_seconds=60, block_seconds=300, endpoint_name='public_track_qr')
def get_qr_data(token):
    """
    Vraca podatke za generisanje QR koda.

    Frontend koristi ove podatke da generiše QR kod koji kupac
    može skenirati da prati status.
    """
    # access_token je ~43 karaktera (URL-safe base64)
    if not token or not (40 <= len(token) <= 50) or not re.match(r'^[A-Za-z0-9_-]+$', token):
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
@rate_limit(max_requests=30, window_seconds=60, block_seconds=300, endpoint_name='public_track_receipt')
def get_receipt_data(token):
    """
    Vraca podatke za printanje potvrde o prijemu.

    Koristi se za generisanje PDF potvrde sa QR kodom.
    """
    # access_token je ~43 karaktera (URL-safe base64)
    if not token or not (40 <= len(token) <= 50) or not re.match(r'^[A-Za-z0-9_-]+$', token):
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
