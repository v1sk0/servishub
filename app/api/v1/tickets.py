"""
Tickets API - CRUD za servisne naloge.

Endpointi za kreiranje, citanje, azuriranje i upravljanje
servisnim nalozima unutar tenanta.
"""

from flask import Blueprint, request, jsonify, g
from datetime import datetime

from ..middleware.auth import jwt_required, tenant_required, location_access_required
from ...extensions import db
from ...models import (
    ServiceTicket, TicketStatus, TicketPriority, TicketNotificationLog,
    get_next_ticket_number, AuditLog, AuditAction
)
from datetime import timezone as tz
import json

bp = Blueprint('tickets', __name__, url_prefix='/tickets')


@bp.route('', methods=['GET'])
@jwt_required
@tenant_required
def list_tickets():
    """
    Lista servisnih naloga za trenutno preduzece.

    Query params:
        - status: filter po statusu (RECEIVED, IN_PROGRESS, itd.)
        - location_id: filter po lokaciji
        - search: pretraga po imenu kupca, broju naloga, IMEI
        - page: broj stranice (default 1)
        - per_page: broj po stranici (default 20, max 100)

    Returns:
        Paginirana lista naloga
    """
    user = g.current_user
    tenant = g.current_tenant

    # Osnovni query - samo nalozi iz dozvoljenih lokacija
    allowed_locations = user.get_accessible_location_ids()
    query = ServiceTicket.query.filter(
        ServiceTicket.tenant_id == tenant.id,
        ServiceTicket.location_id.in_(allowed_locations)
    )

    # Filteri
    status = request.args.get('status')
    if status:
        try:
            status_enum = TicketStatus(status)
            query = query.filter(ServiceTicket.status == status_enum)
        except ValueError:
            pass

    location_id = request.args.get('location_id', type=int)
    if location_id and location_id in allowed_locations:
        query = query.filter(ServiceTicket.location_id == location_id)

    search = request.args.get('search', '').strip()
    if search:
        search_filter = f'%{search}%'
        query = query.filter(
            db.or_(
                ServiceTicket.customer_name.ilike(search_filter),
                ServiceTicket.imei.ilike(search_filter),
                ServiceTicket.customer_phone.ilike(search_filter),
                db.cast(ServiceTicket.ticket_number, db.String).ilike(search_filter)
            )
        )

    # Paginacija
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)

    # Sortiranje - najnoviji prvo
    query = query.order_by(ServiceTicket.created_at.desc())

    # Izvrsi query
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'items': [t.to_dict() for t in pagination.items],
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
        'pages': pagination.pages
    }), 200


@bp.route('/<int:ticket_id>', methods=['GET'])
@jwt_required
@tenant_required
def get_ticket(ticket_id):
    """
    Dohvata jedan servisni nalog.

    Returns:
        Detalji naloga
    """
    user = g.current_user
    tenant = g.current_tenant

    ticket = ServiceTicket.query.filter_by(
        id=ticket_id,
        tenant_id=tenant.id
    ).first()

    if not ticket:
        return jsonify({'error': 'Not Found', 'message': 'Nalog nije pronadjen'}), 404

    # Proveri pristup lokaciji
    if not user.has_location_access(ticket.location_id):
        return jsonify({'error': 'Forbidden', 'message': 'Nemate pristup ovoj lokaciji'}), 403

    return jsonify(ticket.to_dict(include_sensitive=True)), 200


@bp.route('', methods=['POST'])
@jwt_required
@tenant_required
def create_ticket():
    """
    Kreira novi servisni nalog.

    Request body:
        - location_id: ID lokacije (obavezno)
        - customer_name: Ime kupca (obavezno)
        - customer_phone: Telefon kupca
        - customer_email: Email kupca
        - device_type: Tip uredjaja (PHONE, TABLET, LAPTOP, PC, OTHER)
        - brand: Marka
        - model: Model
        - imei: IMEI/serijski broj
        - problem_description: Opis problema (obavezno)
        - estimated_price: Procenjena cena
        - priority: Prioritet (LOW, NORMAL, HIGH, URGENT)
        - warranty_days: Dani garancije (default iz tenant settings)

    Returns:
        201: Kreiran nalog
    """
    user = g.current_user
    tenant = g.current_tenant
    data = request.get_json()

    # Validacija obaveznih polja
    location_id = data.get('location_id')
    if not location_id:
        return jsonify({'error': 'Validation Error', 'message': 'location_id je obavezan'}), 400

    if not user.has_location_access(location_id):
        return jsonify({'error': 'Forbidden', 'message': 'Nemate pristup ovoj lokaciji'}), 403

    customer_name = data.get('customer_name', '').strip()
    if not customer_name:
        return jsonify({'error': 'Validation Error', 'message': 'customer_name je obavezan'}), 400

    problem_description = data.get('problem_description', '').strip()
    if not problem_description:
        return jsonify({'error': 'Validation Error', 'message': 'problem_description je obavezan'}), 400

    # Pripremi problem_areas kao JSON string ako je dict
    problem_areas = data.get('problem_areas')
    if problem_areas and isinstance(problem_areas, dict):
        problem_areas = json.dumps(problem_areas)

    # Kreiraj nalog
    ticket = ServiceTicket(
        tenant_id=tenant.id,
        location_id=location_id,
        ticket_number=get_next_ticket_number(tenant.id),
        # Kupac podaci
        customer_name=customer_name,
        customer_phone=data.get('customer_phone'),
        customer_email=data.get('customer_email'),
        customer_company_name=data.get('customer_company_name'),
        customer_pib=data.get('customer_pib'),
        # Uredjaj podaci
        device_type=data.get('device_type'),
        brand=data.get('brand'),
        model=data.get('model'),
        imei=data.get('imei'),
        device_condition=data.get('device_condition'),
        device_password=data.get('device_password'),
        # Dolce Vita stil - kategorija i stanje
        service_section=data.get('service_section'),
        device_condition_grade=data.get('device_condition_grade'),
        device_condition_notes=data.get('device_condition_notes'),
        device_not_working=data.get('device_not_working', False),
        problem_areas=problem_areas,
        # Problem i cena
        problem_description=problem_description,
        estimated_price=data.get('estimated_price'),
        currency=data.get('currency', 'RSD'),
        warranty_days=data.get('warranty_days', tenant.default_warranty_days),
        # Napomene
        ticket_notes=data.get('ticket_notes'),
        # Tehnicar i kreiranje
        assigned_technician_id=data.get('assigned_technician_id'),
        created_by_id=user.id,
        status=TicketStatus.RECEIVED,
    )

    # Prioritet
    priority = data.get('priority', 'NORMAL')
    try:
        ticket.priority = TicketPriority(priority)
    except ValueError:
        ticket.priority = TicketPriority.NORMAL

    # Generisi access token za QR
    ticket.generate_access_token()

    db.session.add(ticket)
    db.session.flush()  # Get ticket.id before audit log

    # Audit log
    AuditLog.log_create(
        entity_type='ticket',
        entity_id=ticket.id,
        data={'customer': customer_name, 'problem': problem_description[:100]},
        tenant_id=tenant.id,
        user=user
    )

    db.session.commit()

    return jsonify(ticket.to_dict()), 201


@bp.route('/<int:ticket_id>', methods=['PUT'])
@jwt_required
@tenant_required
def update_ticket(ticket_id):
    """
    Azurira servisni nalog.

    Request body: Polja koja se azuriraju

    Returns:
        200: Azuriran nalog
    """
    user = g.current_user
    tenant = g.current_tenant
    data = request.get_json()

    ticket = ServiceTicket.query.filter_by(
        id=ticket_id,
        tenant_id=tenant.id
    ).first()

    if not ticket:
        return jsonify({'error': 'Not Found', 'message': 'Nalog nije pronadjen'}), 404

    if not user.has_location_access(ticket.location_id):
        return jsonify({'error': 'Forbidden', 'message': 'Nemate pristup ovoj lokaciji'}), 403

    # Sacuvaj stare vrednosti za audit
    old_data = ticket.to_dict()

    # Azuriraj polja
    updatable_fields = [
        # Kupac
        'customer_name', 'customer_phone', 'customer_email',
        'customer_company_name', 'customer_pib',
        # Uredjaj
        'device_type', 'brand', 'model', 'imei', 'device_condition', 'device_password',
        # Dolce Vita stil
        'service_section', 'device_condition_grade', 'device_condition_notes',
        'device_not_working',
        # Problem i resenje
        'problem_description', 'diagnosis', 'resolution',
        # Cene i garancija
        'estimated_price', 'final_price', 'currency', 'warranty_days',
        # Napomene
        'ticket_notes'
    ]

    for field in updatable_fields:
        if field in data:
            setattr(ticket, field, data[field])

    # Posebno obradi problem_areas (JSON)
    if 'problem_areas' in data:
        problem_areas = data['problem_areas']
        if problem_areas and isinstance(problem_areas, dict):
            ticket.problem_areas = json.dumps(problem_areas)
        else:
            ticket.problem_areas = problem_areas

    # Prioritet
    if 'priority' in data:
        try:
            ticket.priority = TicketPriority(data['priority'])
        except ValueError:
            pass

    # Tehnicar
    if 'assigned_technician_id' in data:
        ticket.assigned_technician_id = data['assigned_technician_id']

    # Audit log
    new_data = ticket.to_dict()
    from ...models import calculate_changes
    changes = calculate_changes(old_data, new_data)
    if changes:
        AuditLog.log_update(
            entity_type='ticket',
            entity_id=ticket.id,
            changes=changes,
            tenant_id=tenant.id,
            user=user
        )

    db.session.commit()

    return jsonify(ticket.to_dict()), 200


@bp.route('/<int:ticket_id>/status', methods=['PUT'])
@jwt_required
@tenant_required
def update_ticket_status(ticket_id):
    """
    Menja status servisnog naloga.

    Request body:
        - status: Novi status (RECEIVED, DIAGNOSED, IN_PROGRESS, WAITING_PARTS, READY, DELIVERED, CANCELLED)

    Returns:
        200: Azuriran status
    """
    user = g.current_user
    tenant = g.current_tenant
    data = request.get_json()

    ticket = ServiceTicket.query.filter_by(
        id=ticket_id,
        tenant_id=tenant.id
    ).first()

    if not ticket:
        return jsonify({'error': 'Not Found', 'message': 'Nalog nije pronadjen'}), 404

    if not user.has_location_access(ticket.location_id):
        return jsonify({'error': 'Forbidden', 'message': 'Nemate pristup ovoj lokaciji'}), 403

    new_status = data.get('status')
    if not new_status:
        return jsonify({'error': 'Validation Error', 'message': 'status je obavezan'}), 400

    try:
        new_status_enum = TicketStatus(new_status)
    except ValueError:
        return jsonify({'error': 'Validation Error', 'message': 'Neispravan status'}), 400

    old_status = ticket.status.value

    # Ako se zatvara nalog (DELIVERED), postavi closed_at
    if new_status_enum == TicketStatus.DELIVERED and ticket.status != TicketStatus.DELIVERED:
        ticket.close_ticket()
    else:
        ticket.status = new_status_enum

    # Audit log
    AuditLog.log_status_change(
        entity_type='ticket',
        entity_id=ticket.id,
        old_status=old_status,
        new_status=new_status,
        tenant_id=tenant.id,
        user=user
    )

    db.session.commit()

    return jsonify(ticket.to_dict()), 200


@bp.route('/<int:ticket_id>/pay', methods=['POST'])
@jwt_required
@tenant_required
def mark_ticket_paid(ticket_id):
    """
    Oznacava nalog kao naplacen.

    Request body:
        - payment_method: Nacin placanja (CASH, CARD, TRANSFER)
        - final_price: Konacna cena (opciono, ako nije vec postavljena)

    Returns:
        200: Nalog oznacen kao naplacen
    """
    user = g.current_user
    tenant = g.current_tenant
    data = request.get_json() or {}

    ticket = ServiceTicket.query.filter_by(
        id=ticket_id,
        tenant_id=tenant.id
    ).first()

    if not ticket:
        return jsonify({'error': 'Not Found', 'message': 'Nalog nije pronadjen'}), 404

    if ticket.is_paid:
        return jsonify({'error': 'Bad Request', 'message': 'Nalog je vec naplacen'}), 400

    payment_method = data.get('payment_method', 'CASH')
    if 'final_price' in data:
        ticket.final_price = data['final_price']

    ticket.mark_as_paid(payment_method)

    AuditLog.log(
        entity_type='ticket',
        entity_id=ticket.id,
        action=AuditAction.UPDATE,
        changes={'is_paid': {'old': False, 'new': True}, 'payment_method': payment_method},
        tenant_id=tenant.id,
        user=user
    )

    db.session.commit()

    return jsonify(ticket.to_dict()), 200


@bp.route('/<int:ticket_id>/history', methods=['GET'])
@jwt_required
@tenant_required
def get_ticket_history(ticket_id):
    """
    Istorija promena naloga iz audit loga.

    Returns:
        Lista promena
    """
    user = g.current_user
    tenant = g.current_tenant

    ticket = ServiceTicket.query.filter_by(
        id=ticket_id,
        tenant_id=tenant.id
    ).first()

    if not ticket:
        return jsonify({'error': 'Not Found', 'message': 'Nalog nije pronadjen'}), 404

    # Dohvati audit log
    logs = AuditLog.query.filter_by(
        tenant_id=tenant.id,
        entity_type='ticket',
        entity_id=ticket_id
    ).order_by(AuditLog.created_at.desc()).limit(50).all()

    return jsonify({
        'items': [
            {
                'id': log.id,
                'action': log.action.value,
                'changes': log.changes_json,
                'user_email': log.user_email,
                'created_at': log.created_at.isoformat()
            }
            for log in logs
        ]
    }), 200


@bp.route('/public/<string:access_token>', methods=['GET'])
def get_ticket_public(access_token):
    """
    Javni pristup nalogu preko QR koda.
    NE zahteva autentifikaciju.

    Returns:
        Osnovni podaci o nalogu (bez osetljivih informacija)
    """
    ticket = ServiceTicket.query.filter_by(access_token=access_token).first()

    if not ticket:
        return jsonify({'error': 'Not Found', 'message': 'Nalog nije pronadjen'}), 404

    return jsonify({
        'ticket_number': ticket.ticket_number_formatted,
        'status': ticket.status.value,
        'device_type': ticket.device_type,
        'brand': ticket.brand,
        'model': ticket.model,
        'problem_description': ticket.problem_description,
        'diagnosis': ticket.diagnosis,
        'estimated_price': float(ticket.estimated_price) if ticket.estimated_price else None,
        'final_price': float(ticket.final_price) if ticket.final_price else None,
        'warranty_days': ticket.warranty_days,
        'warranty_remaining_days': ticket.warranty_remaining_days,
        'is_under_warranty': ticket.is_under_warranty,
        'is_collected': ticket.is_collected,
        'notification_count': ticket.notification_count,
        'created_at': ticket.created_at.isoformat(),
        'closed_at': ticket.closed_at.isoformat() if ticket.closed_at else None,
    }), 200


# =============================================================================
# DOLCE VITA STIL - DODATNI ENDPOINTI
# =============================================================================


@bp.route('/<int:ticket_id>/notify', methods=['POST'])
@jwt_required
@tenant_required
def notify_customer(ticket_id):
    """
    Loguje pokusaj obavestavanja kupca za preuzimanje uredjaja.

    Dolce Vita pravila:
    - Minimum 15 dana izmedju notifikacija (osim prve)
    - Nakon 5+ neuspesnih pokusaja moze write-off

    Request body:
        - comment: Napomena o pozivu (opciono)
        - notification_type: Tip notifikacije (CALL, SMS, EMAIL), default CALL
        - contact_successful: Da li je kontakt uspesan (default false)

    Returns:
        200: Notifikacija ubelezena
        400: Nije proslo 15 dana od poslednje notifikacije
    """
    user = g.current_user
    tenant = g.current_tenant
    data = request.get_json() or {}

    ticket = ServiceTicket.query.filter_by(
        id=ticket_id,
        tenant_id=tenant.id
    ).first()

    if not ticket:
        return jsonify({'error': 'Not Found', 'message': 'Nalog nije pronadjen'}), 404

    if not user.has_location_access(ticket.location_id):
        return jsonify({'error': 'Forbidden', 'message': 'Nemate pristup ovoj lokaciji'}), 403

    # Proveri da li je vec preuzeto ili otpisano
    if ticket.is_collected:
        return jsonify({'error': 'Bad Request', 'message': 'Uredjaj je vec preuzet'}), 400

    if ticket.is_written_off:
        return jsonify({'error': 'Bad Request', 'message': 'Nalog je otpisan'}), 400

    # Proveri 15-dnevno pravilo
    if not ticket.can_notify:
        days_left = ticket.days_until_can_notify
        return jsonify({
            'error': 'Too Early',
            'message': f'Morate sacekati jos {days_left} dana pre sledece notifikacije',
            'days_until_can_notify': days_left
        }), 400

    # Kreiraj log notifikacije
    notification_log = TicketNotificationLog(
        ticket_id=ticket.id,
        user_id=user.id,
        comment=data.get('comment'),
        notification_type=data.get('notification_type', 'CALL'),
        contact_successful=data.get('contact_successful', False)
    )

    db.session.add(notification_log)

    # Audit log
    AuditLog.log(
        entity_type='ticket',
        entity_id=ticket.id,
        action=AuditAction.UPDATE,
        changes={
            'notification': {
                'type': notification_log.notification_type,
                'count': ticket.notification_count + 1,
                'contact_successful': notification_log.contact_successful
            }
        },
        tenant_id=tenant.id,
        user=user
    )

    db.session.commit()

    return jsonify({
        'message': 'Notifikacija ubelezena',
        'notification_count': ticket.notification_count,
        'can_write_off': ticket.can_write_off,
        'days_until_can_notify': 15
    }), 200


@bp.route('/<int:ticket_id>/notifications', methods=['GET'])
@jwt_required
@tenant_required
def get_ticket_notifications(ticket_id):
    """
    Lista svih notifikacija/poziva za nalog.

    Returns:
        Lista notifikacija sa detaljima
    """
    user = g.current_user
    tenant = g.current_tenant

    ticket = ServiceTicket.query.filter_by(
        id=ticket_id,
        tenant_id=tenant.id
    ).first()

    if not ticket:
        return jsonify({'error': 'Not Found', 'message': 'Nalog nije pronadjen'}), 404

    if not user.has_location_access(ticket.location_id):
        return jsonify({'error': 'Forbidden', 'message': 'Nemate pristup ovoj lokaciji'}), 403

    notifications = ticket.notification_logs.order_by(
        TicketNotificationLog.timestamp.desc()
    ).all()

    return jsonify({
        'items': [n.to_dict() for n in notifications],
        'total': len(notifications),
        'can_notify': ticket.can_notify,
        'can_write_off': ticket.can_write_off,
        'days_until_can_notify': ticket.days_until_can_notify
    }), 200


@bp.route('/<int:ticket_id>/write-off', methods=['POST'])
@jwt_required
@tenant_required
def write_off_ticket(ticket_id):
    """
    Write-off naloga nakon 5+ neuspesnih pokusaja kontakta.

    Dolce Vita pravila:
    - Minimum 5 notifikacija pre write-off-a
    - Nalog mora biti nezatvoren i nepreuzet

    Returns:
        200: Nalog otpisan
        400: Ne ispunjava uslove za write-off
    """
    user = g.current_user
    tenant = g.current_tenant

    ticket = ServiceTicket.query.filter_by(
        id=ticket_id,
        tenant_id=tenant.id
    ).first()

    if not ticket:
        return jsonify({'error': 'Not Found', 'message': 'Nalog nije pronadjen'}), 404

    if not user.has_location_access(ticket.location_id):
        return jsonify({'error': 'Forbidden', 'message': 'Nemate pristup ovoj lokaciji'}), 403

    # Proveri uslove za write-off
    if ticket.is_collected:
        return jsonify({'error': 'Bad Request', 'message': 'Uredjaj je vec preuzet'}), 400

    if ticket.is_written_off:
        return jsonify({'error': 'Bad Request', 'message': 'Nalog je vec otpisan'}), 400

    if not ticket.can_write_off:
        return jsonify({
            'error': 'Bad Request',
            'message': f'Potrebno je minimum 5 notifikacija za write-off. Trenutno: {ticket.notification_count}'
        }), 400

    # Izvrsi write-off
    ticket.is_written_off = True
    ticket.written_off_timestamp = datetime.now(tz.utc)
    ticket.written_off_by_id = user.id

    # Audit log
    AuditLog.log(
        entity_type='ticket',
        entity_id=ticket.id,
        action=AuditAction.UPDATE,
        changes={
            'is_written_off': {'old': False, 'new': True},
            'notification_count': ticket.notification_count
        },
        tenant_id=tenant.id,
        user=user
    )

    db.session.commit()

    return jsonify({
        'message': 'Nalog uspesno otpisan',
        'ticket': ticket.to_dict()
    }), 200


@bp.route('/<int:ticket_id>/collect', methods=['POST'])
@jwt_required
@tenant_required
def collect_ticket(ticket_id):
    """
    Oznacava nalog kao preuzet (naplata).

    Dolce Vita stil - omogucava izmenu cene pri preuzimanju.

    Request body:
        - final_price: Konacna cena (opciono)
        - currency: Valuta (opciono, default RSD)
        - payment_method: Nacin placanja (CASH, CARD, TRANSFER)
        - owner_collect: Ime osobe koja preuzima (opciono)

    Returns:
        200: Nalog preuzet i naplacen
    """
    user = g.current_user
    tenant = g.current_tenant
    data = request.get_json() or {}

    ticket = ServiceTicket.query.filter_by(
        id=ticket_id,
        tenant_id=tenant.id
    ).first()

    if not ticket:
        return jsonify({'error': 'Not Found', 'message': 'Nalog nije pronadjen'}), 404

    if not user.has_location_access(ticket.location_id):
        return jsonify({'error': 'Forbidden', 'message': 'Nemate pristup ovoj lokaciji'}), 403

    if ticket.is_collected:
        return jsonify({'error': 'Bad Request', 'message': 'Uredjaj je vec preuzet'}), 400

    if ticket.is_written_off:
        return jsonify({'error': 'Bad Request', 'message': 'Nalog je otpisan, nije moguce preuzimanje'}), 400

    # Azuriraj cenu ako je prosledjena
    if 'final_price' in data:
        ticket.final_price = data['final_price']

    if 'currency' in data:
        ticket.currency = data['currency']

    # Ko je preuzeo
    ticket.owner_collect = data.get('owner_collect', ticket.customer_name)
    ticket.owner_collect_timestamp = datetime.now(tz.utc)

    # Racunaj trajanje popravke
    if ticket.created_at:
        delta = datetime.utcnow() - ticket.created_at
        ticket.complete_duration = int(delta.total_seconds())

    # Oznaci kao naplaceno i zatvori
    payment_method = data.get('payment_method', 'CASH')
    ticket.mark_as_paid(payment_method)
    ticket.close_ticket()

    # Audit log
    AuditLog.log(
        entity_type='ticket',
        entity_id=ticket.id,
        action=AuditAction.UPDATE,
        changes={
            'is_paid': {'old': False, 'new': True},
            'status': {'old': ticket.status.value, 'new': 'DELIVERED'},
            'owner_collect': ticket.owner_collect,
            'payment_method': payment_method
        },
        tenant_id=tenant.id,
        user=user
    )

    db.session.commit()

    return jsonify({
        'message': 'Nalog uspesno naplacen i zatvoren',
        'ticket': ticket.to_dict()
    }), 200


@bp.route('/<int:ticket_id>/print', methods=['GET'])
@jwt_required
@tenant_required
def get_ticket_print_data(ticket_id):
    """
    Vraca podatke potrebne za stampanje naloga.

    Podaci ukljucuju:
    - Kompletan ticket sa svim poljima
    - Tenant podaci (naziv firme, adresa, PIB, itd.)
    - QR kod URL
    - Klauzola iz tenant settings

    Returns:
        200: Podaci za stampanje
    """
    user = g.current_user
    tenant = g.current_tenant

    ticket = ServiceTicket.query.filter_by(
        id=ticket_id,
        tenant_id=tenant.id
    ).first()

    if not ticket:
        return jsonify({'error': 'Not Found', 'message': 'Nalog nije pronadjen'}), 404

    if not user.has_location_access(ticket.location_id):
        return jsonify({'error': 'Forbidden', 'message': 'Nemate pristup ovoj lokaciji'}), 403

    # Dohvati tenant settings za klauzolu
    settings = tenant.settings_json or {}
    clause = settings.get('ticket_clause', '')

    # URL za QR kod
    qr_url = f"/tickets/public/{ticket.access_token}" if ticket.access_token else None

    return jsonify({
        'ticket': ticket.to_dict(include_sensitive=True),
        'tenant': {
            'name': tenant.name,
            'pib': tenant.pib,
            'address': tenant.adresa_sedista,
            'email': tenant.email,
            'phone': tenant.telefon
        },
        'location': {
            'name': ticket.location.name if ticket.location else None,
            'address': ticket.location.address if ticket.location else None,
            'phone': ticket.location.phone if ticket.location else None
        },
        'qr_url': qr_url,
        'clause': clause,
        'print_date': datetime.utcnow().isoformat()
    }), 200


@bp.route('/stats', methods=['GET'])
@jwt_required
@tenant_required
def get_ticket_stats():
    """
    KPI statistike za dashboard (Dolce Vita stil).

    Vraca:
    - open_tickets: Broj otvorenih naloga
    - closed_tickets: Broj zatvorenih naloga (ovaj mesec)
    - uncollected_tickets: Broj gotovih ali nenaplacenih naloga
    - active_warranties: Broj aktivnih garancija
    - today_tickets: Broj naloga kreiranih danas
    - written_off_tickets: Broj otpisanih naloga

    Query params:
        - location_id: Filter po lokaciji (opciono)

    Returns:
        200: Statistike
    """
    user = g.current_user
    tenant = g.current_tenant

    # Dozvoljene lokacije
    allowed_locations = user.get_accessible_location_ids()
    location_id = request.args.get('location_id', type=int)

    if location_id:
        if location_id not in allowed_locations:
            return jsonify({'error': 'Forbidden', 'message': 'Nemate pristup ovoj lokaciji'}), 403
        location_filter = [location_id]
    else:
        location_filter = allowed_locations

    # Bazni query
    base_query = ServiceTicket.query.filter(
        ServiceTicket.tenant_id == tenant.id,
        ServiceTicket.location_id.in_(location_filter)
    )

    # Otvoreni nalozi (nije DELIVERED, CANCELLED, niti written off)
    open_tickets = base_query.filter(
        ServiceTicket.status.notin_([TicketStatus.DELIVERED, TicketStatus.CANCELLED]),
        ServiceTicket.is_written_off == False
    ).count()

    # Zatvoreni ovaj mesec
    from datetime import date
    first_day_of_month = date.today().replace(day=1)
    closed_tickets = base_query.filter(
        ServiceTicket.status == TicketStatus.DELIVERED,
        ServiceTicket.closed_at >= first_day_of_month
    ).count()

    # Nenaplaceni (READY ali nisu is_paid)
    uncollected_tickets = base_query.filter(
        ServiceTicket.status == TicketStatus.READY,
        ServiceTicket.is_paid == False,
        ServiceTicket.is_written_off == False
    ).count()

    # Aktivne garancije
    active_warranties = base_query.filter(
        ServiceTicket.status == TicketStatus.DELIVERED,
        ServiceTicket.closed_at.isnot(None),
        ServiceTicket.warranty_days > 0
    ).all()
    warranties_count = sum(1 for t in active_warranties if t.is_under_warranty)

    # Danas kreirani
    today = date.today()
    today_tickets = base_query.filter(
        db.func.date(ServiceTicket.created_at) == today
    ).count()

    # Otpisani
    written_off_tickets = base_query.filter(
        ServiceTicket.is_written_off == True
    ).count()

    # Cekaju preuzimanje (READY)
    ready_tickets = base_query.filter(
        ServiceTicket.status == TicketStatus.READY,
        ServiceTicket.is_written_off == False
    ).count()

    return jsonify({
        'open_tickets': open_tickets,
        'closed_tickets': closed_tickets,
        'uncollected_tickets': uncollected_tickets,
        'ready_tickets': ready_tickets,
        'active_warranties': warranties_count,
        'today_tickets': today_tickets,
        'written_off_tickets': written_off_tickets
    }), 200


@bp.route('/warranties', methods=['GET'])
@jwt_required
@tenant_required
def get_warranty_tickets():
    """
    Lista naloga sa garancijama.

    Query params:
        - filter: Filter po statusu garancije (active, expiring, expired)
        - location_id: Filter po lokaciji
        - page, per_page: Paginacija

    Returns:
        Paginirana lista naloga sa garancijama
    """
    user = g.current_user
    tenant = g.current_tenant

    # Dozvoljene lokacije
    allowed_locations = user.get_accessible_location_ids()
    location_id = request.args.get('location_id', type=int)

    if location_id:
        if location_id not in allowed_locations:
            return jsonify({'error': 'Forbidden', 'message': 'Nemate pristup ovoj lokaciji'}), 403
        location_filter = [location_id]
    else:
        location_filter = allowed_locations

    # Samo zatvoreni sa garancijom
    query = ServiceTicket.query.filter(
        ServiceTicket.tenant_id == tenant.id,
        ServiceTicket.location_id.in_(location_filter),
        ServiceTicket.status == TicketStatus.DELIVERED,
        ServiceTicket.closed_at.isnot(None),
        ServiceTicket.warranty_days > 0
    )

    # Dohvati sve i filtriraj u Pythonu (posto warranty_expires_at je property)
    tickets = query.order_by(ServiceTicket.closed_at.desc()).all()

    # Filter po statusu garancije
    filter_type = request.args.get('filter', 'all')
    filtered_tickets = []

    for t in tickets:
        remaining = t.warranty_remaining_days
        if remaining is None:
            continue

        if filter_type == 'active' and remaining > 10:
            filtered_tickets.append(t)
        elif filter_type == 'expiring' and 0 < remaining <= 10:
            filtered_tickets.append(t)
        elif filter_type == 'expired' and remaining <= 0:
            filtered_tickets.append(t)
        elif filter_type == 'all':
            filtered_tickets.append(t)

    # Paginacija
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)

    start = (page - 1) * per_page
    end = start + per_page
    paginated = filtered_tickets[start:end]

    return jsonify({
        'items': [
            {
                **t.to_dict(),
                'warranty_status': 'active' if t.warranty_remaining_days and t.warranty_remaining_days > 10
                    else 'expiring' if t.warranty_remaining_days and t.warranty_remaining_days > 0
                    else 'expired'
            }
            for t in paginated
        ],
        'total': len(filtered_tickets),
        'page': page,
        'per_page': per_page,
        'pages': (len(filtered_tickets) + per_page - 1) // per_page
    }), 200
