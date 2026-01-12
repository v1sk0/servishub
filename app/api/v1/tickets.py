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
    ServiceTicket, TicketStatus, TicketPriority,
    get_next_ticket_number, AuditLog, AuditAction
)

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

    # Kreiraj nalog
    ticket = ServiceTicket(
        tenant_id=tenant.id,
        location_id=location_id,
        ticket_number=get_next_ticket_number(tenant.id),
        customer_name=customer_name,
        customer_phone=data.get('customer_phone'),
        customer_email=data.get('customer_email'),
        device_type=data.get('device_type'),
        brand=data.get('brand'),
        model=data.get('model'),
        imei=data.get('imei'),
        device_condition=data.get('device_condition'),
        device_password=data.get('device_password'),
        problem_description=problem_description,
        estimated_price=data.get('estimated_price'),
        warranty_days=data.get('warranty_days', tenant.default_warranty_days),
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
        'customer_name', 'customer_phone', 'customer_email',
        'device_type', 'brand', 'model', 'imei', 'device_condition', 'device_password',
        'problem_description', 'diagnosis', 'resolution',
        'estimated_price', 'final_price', 'warranty_days'
    ]

    for field in updatable_fields:
        if field in data:
            setattr(ticket, field, data[field])

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
        'created_at': ticket.created_at.isoformat(),
        'closed_at': ticket.closed_at.isoformat() if ticket.closed_at else None,
    }), 200
