"""
Admin Payments API - Upravljanje fakturama i uplatama.

Endpointi za:
- Lista svih faktura (sa filterima)
- Verifikacija uplate
- Odbijanje uplate
- Generisanje fakture
- Block/unblock servisa
- Custom cene za servis
"""

from datetime import datetime, date, timedelta
from decimal import Decimal
from flask import Blueprint, request, jsonify, g
from sqlalchemy import func, or_, and_

from app.extensions import db
from app.models import Tenant, TenantMessage, PlatformSettings
from app.models.representative import SubscriptionPayment
from app.models.tenant import TenantStatus, ServiceLocation
from app.models.tenant_message import MessageCategory, MessagePriority
from app.models.admin_activity import AdminActivityLog, AdminActionType
from app.api.middleware.auth import platform_admin_required

bp = Blueprint('admin_payments', __name__, url_prefix='/payments')


# ============================================================================
# LISTA FAKTURA
# ============================================================================

@bp.route('', methods=['GET'])
@platform_admin_required
def list_payments():
    """
    Lista svih faktura sa filterima i paginacijom.

    Query params:
        - page: broj stranice (default 1)
        - per_page: broj po stranici (default 20, max 100)
        - status: PENDING, PAID, OVERDUE, CANCELLED
        - tenant_id: filter po servisu
        - search: pretraga po broju fakture ili imenu servisa
        - has_proof: true/false - ima dokaz o uplati
        - sort: created_at, due_date, total_amount
        - order: asc, desc
    """
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)
    status = request.args.get('status')
    tenant_id = request.args.get('tenant_id', type=int)
    search = request.args.get('search', '').strip()
    has_proof = request.args.get('has_proof')
    sort = request.args.get('sort', 'created_at')
    order = request.args.get('order', 'desc')

    # Base query with tenant join
    query = SubscriptionPayment.query.join(Tenant)

    # Filter by status
    if status:
        query = query.filter(SubscriptionPayment.status == status)

    # Filter by tenant
    if tenant_id:
        query = query.filter(SubscriptionPayment.tenant_id == tenant_id)

    # Search
    if search:
        search_term = f'%{search}%'
        query = query.filter(
            or_(
                SubscriptionPayment.invoice_number.ilike(search_term),
                Tenant.name.ilike(search_term)
            )
        )

    # Filter by proof
    if has_proof == 'true':
        query = query.filter(SubscriptionPayment.payment_proof_url.isnot(None))
    elif has_proof == 'false':
        query = query.filter(SubscriptionPayment.payment_proof_url.is_(None))

    # Sorting
    sort_column = getattr(SubscriptionPayment, sort, SubscriptionPayment.created_at)
    if order == 'desc':
        sort_column = sort_column.desc()
    query = query.order_by(sort_column)

    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    payments_data = []
    for payment in pagination.items:
        data = payment.to_dict()
        data['tenant_name'] = payment.tenant.name
        data['tenant_email'] = payment.tenant.email
        data['tenant_status'] = payment.tenant.status.value
        payments_data.append(data)

    return jsonify({
        'payments': payments_data,
        'pagination': {
            'page': pagination.page,
            'per_page': pagination.per_page,
            'total': pagination.total,
            'pages': pagination.pages,
            'has_next': pagination.has_next,
            'has_prev': pagination.has_prev
        }
    })


@bp.route('/pending', methods=['GET'])
@platform_admin_required
def list_pending_payments():
    """
    Lista faktura koje čekaju verifikaciju (imaju dokaz o uplati).
    """
    payments = SubscriptionPayment.query.join(Tenant).filter(
        SubscriptionPayment.status == 'PENDING',
        SubscriptionPayment.payment_proof_url.isnot(None)
    ).order_by(SubscriptionPayment.paid_at.asc()).all()

    return jsonify({
        'payments': [{
            **p.to_dict(),
            'tenant_name': p.tenant.name,
            'tenant_email': p.tenant.email
        } for p in payments],
        'count': len(payments)
    })


@bp.route('/overdue', methods=['GET'])
@platform_admin_required
def list_overdue_payments():
    """
    Lista zakasnelih faktura (prošao due_date, status nije PAID).
    """
    today = date.today()

    payments = SubscriptionPayment.query.join(Tenant).filter(
        SubscriptionPayment.status.in_(['PENDING', 'OVERDUE']),
        SubscriptionPayment.due_date < today
    ).order_by(SubscriptionPayment.due_date.asc()).all()

    return jsonify({
        'payments': [{
            **p.to_dict(),
            'tenant_name': p.tenant.name,
            'tenant_email': p.tenant.email,
            'tenant_trust_score': p.tenant.trust_score
        } for p in payments],
        'count': len(payments)
    })


# ============================================================================
# VERIFIKACIJA I ODBIJANJE UPLATE
# ============================================================================

@bp.route('/<int:payment_id>/verify', methods=['PUT'])
@platform_admin_required
def verify_payment(payment_id):
    """
    Verifikuje uplatu i aktivira/produžava pretplatu.

    Body JSON:
        - verification_notes: napomena admina (opciono)
    """
    payment = SubscriptionPayment.query.get_or_404(payment_id)
    tenant = payment.tenant
    data = request.get_json() or {}

    if payment.status == 'PAID':
        return jsonify({'error': 'Uplata je već verifikovana'}), 400

    # Verifikuj uplatu
    payment.status = 'PAID'
    payment.verified_at = datetime.utcnow()
    payment.verified_by_id = g.current_admin.id
    payment.verification_notes = data.get('verification_notes')

    # Ažuriraj tenant billing
    if tenant.current_debt:
        tenant.current_debt = max(Decimal('0'), tenant.current_debt - payment.total_amount)
    tenant.last_payment_at = datetime.utcnow()
    tenant.days_overdue = 0

    # Trust score update
    if payment.due_date and payment.due_date >= date.today():
        # Plaćeno na vreme
        tenant.update_trust_score(+10, 'Uplata na vreme')
        tenant.consecutive_on_time_payments = (tenant.consecutive_on_time_payments or 0) + 1

        # Godišnji bonus
        if tenant.consecutive_on_time_payments >= 12:
            tenant.update_trust_score(+15, '12 meseci uzastopnih uplata')
            tenant.consecutive_on_time_payments = 0
    elif tenant.is_trust_active:
        # Plaćeno tokom "na reč" perioda
        tenant.update_trust_score(-5, 'Plaćeno tokom "na reč" perioda')
        tenant.trust_activated_at = None
        tenant.consecutive_on_time_payments = 0
    else:
        # Plaćeno kasno (u grace periodu)
        tenant.consecutive_on_time_payments = 0

    # Aktiviraj/produži pretplatu
    if tenant.status in [TenantStatus.EXPIRED, TenantStatus.SUSPENDED]:
        tenant.unblock()

    # Postavi subscription_ends_at
    if payment.period_end:
        tenant.subscription_ends_at = datetime.combine(payment.period_end, datetime.min.time())
    else:
        tenant.subscription_ends_at = datetime.utcnow() + timedelta(days=30)

    tenant.status = TenantStatus.ACTIVE

    # Sistemska poruka
    TenantMessage.create_system_message(
        tenant_id=tenant.id,
        subject='Uplata potvrđena - hvala!',
        body=f'''Vaša uplata za fakturu {payment.invoice_number} je potvrđena.

Iznos: {float(payment.total_amount):,.2f} {payment.currency}
Period: {payment.period_start} - {payment.period_end}

Vaš Trust Score: {tenant.trust_score}
Pretplata važi do: {tenant.subscription_ends_at.strftime("%d.%m.%Y.")}

Hvala na poverenju!''',
        category=MessageCategory.BILLING,
        priority=MessagePriority.NORMAL,
        related_payment_id=payment.id
    )

    # Audit log
    AdminActivityLog.log(
        action_type=AdminActionType.VERIFY_PAYMENT,
        target_type='payment',
        target_id=payment.id,
        target_name=payment.invoice_number,
        details={
            'tenant_id': tenant.id,
            'tenant_name': tenant.name,
            'amount': float(payment.total_amount),
            'notes': data.get('verification_notes')
        }
    )

    db.session.commit()

    return jsonify({
        'message': f'Uplata {payment.invoice_number} verifikovana',
        'payment': payment.to_dict(),
        'tenant_status': tenant.status.value,
        'tenant_trust_score': tenant.trust_score
    })


@bp.route('/<int:payment_id>/reject', methods=['PUT'])
@platform_admin_required
def reject_payment(payment_id):
    """
    Odbija prijavljenu uplatu.

    Body JSON:
        - reason: razlog odbijanja (obavezno)
    """
    payment = SubscriptionPayment.query.get_or_404(payment_id)
    tenant = payment.tenant
    data = request.get_json() or {}

    reason = data.get('reason')
    if not reason:
        return jsonify({'error': 'Razlog odbijanja je obavezan'}), 400

    if payment.status == 'PAID':
        return jsonify({'error': 'Ne možete odbiti već verifikovanu uplatu'}), 400

    # Reset payment proof fields
    old_proof = payment.payment_proof_url
    payment.payment_proof_url = None
    payment.payment_notes = None
    payment.paid_at = None
    payment.verification_notes = f'ODBIJENO: {reason}'

    # Sistemska poruka
    TenantMessage.create_system_message(
        tenant_id=tenant.id,
        subject='Uplata odbijena',
        body=f'''Vaša prijava uplate za fakturu {payment.invoice_number} je odbijena.

Razlog: {reason}

Molimo vas da proverite uplatnicu i ponovo prijavite uplatu sa ispravnim dokazom.

Ako smatrate da je ovo greška, kontaktirajte podršku.''',
        category=MessageCategory.BILLING,
        priority=MessagePriority.HIGH,
        action_url='/settings/subscription',
        action_label='Ponovo prijavi',
        related_payment_id=payment.id
    )

    # Audit log
    AdminActivityLog.log(
        action_type=AdminActionType.REJECT_PAYMENT,
        target_type='payment',
        target_id=payment.id,
        target_name=payment.invoice_number,
        details={
            'tenant_id': tenant.id,
            'tenant_name': tenant.name,
            'reason': reason,
            'old_proof_url': old_proof
        }
    )

    db.session.commit()

    return jsonify({
        'message': f'Uplata {payment.invoice_number} odbijena',
        'reason': reason
    })


# ============================================================================
# GENERISANJE FAKTURE
# ============================================================================

@bp.route('/generate/<int:tenant_id>', methods=['POST'])
@platform_admin_required
def generate_invoice(tenant_id):
    """
    Ručno generiše fakturu za servis.

    Body JSON:
        - period_start: početak perioda (YYYY-MM-DD)
        - period_end: kraj perioda (YYYY-MM-DD)
        - discount_amount: popust (opciono)
        - discount_reason: razlog popusta (opciono)
        - notes: napomena (opciono)
    """
    tenant = Tenant.query.get_or_404(tenant_id)
    data = request.get_json() or {}
    settings = PlatformSettings.get_settings()

    # Parse dates
    try:
        if data.get('period_start'):
            period_start = datetime.strptime(data['period_start'], '%Y-%m-%d').date()
        else:
            period_start = date.today().replace(day=1)

        if data.get('period_end'):
            period_end = datetime.strptime(data['period_end'], '%Y-%m-%d').date()
        else:
            # Last day of month
            next_month = period_start.replace(day=28) + timedelta(days=4)
            period_end = next_month - timedelta(days=next_month.day)
    except ValueError as e:
        return jsonify({'error': f'Invalid date format: {str(e)}'}), 400

    # Broj lokacija
    locations = ServiceLocation.query.filter_by(
        tenant_id=tenant.id, is_active=True
    ).all()
    locations_count = len(locations)

    # Cene
    base_price = float(tenant.custom_base_price or settings.base_price)
    location_price = float(tenant.custom_location_price or settings.location_price)

    # Kalkulacija
    additional = max(0, locations_count - 1)
    subtotal = base_price + (additional * location_price)

    # Stavke fakture
    items = [
        {'type': 'BASE', 'description': 'Bazni paket', 'amount': base_price}
    ]

    for loc in locations[1:]:  # Skip first (included in base)
        items.append({
            'type': 'LOCATION',
            'location_id': loc.id,
            'name': loc.name,
            'amount': location_price
        })

    # Popust
    discount = Decimal(str(data.get('discount_amount', 0)))
    total = Decimal(str(subtotal)) - discount

    # Kreiraj fakturu
    invoice_number = SubscriptionPayment.generate_invoice_number()

    payment = SubscriptionPayment(
        tenant_id=tenant.id,
        invoice_number=invoice_number,
        period_start=period_start,
        period_end=period_end,
        items_json=items,
        subtotal=Decimal(str(subtotal)),
        discount_amount=discount,
        discount_reason=data.get('discount_reason'),
        total_amount=total,
        currency=settings.currency or 'RSD',
        status='PENDING',
        due_date=date.today() + timedelta(days=7),
        is_auto_generated=False
    )

    db.session.add(payment)

    # Ažuriraj tenant dugovanje
    tenant.current_debt = (tenant.current_debt or Decimal('0')) + total

    # Sistemska poruka
    TenantMessage.create_system_message(
        tenant_id=tenant.id,
        subject=f'Nova faktura za {period_start.strftime("%B %Y")}',
        body=f'''Generisana je nova faktura za vaš servis.

Broj fakture: {invoice_number}
Period: {period_start.strftime("%d.%m.%Y.")} - {period_end.strftime("%d.%m.%Y.")}
Iznos: {float(total):,.2f} RSD
Rok za plaćanje: {(date.today() + timedelta(days=7)).strftime("%d.%m.%Y.")}

Molimo vas da izvršite uplatu na vreme.''',
        category=MessageCategory.BILLING,
        priority=MessagePriority.NORMAL,
        action_url='/settings/subscription',
        action_label='Pogledaj fakturu',
        related_payment_id=payment.id
    )

    # Audit log
    AdminActivityLog.log(
        action_type=AdminActionType.GENERATE_INVOICE,
        target_type='payment',
        target_id=payment.id,
        target_name=invoice_number,
        details={
            'tenant_id': tenant.id,
            'tenant_name': tenant.name,
            'amount': float(total),
            'period': f'{period_start} - {period_end}'
        }
    )

    db.session.commit()

    return jsonify({
        'message': f'Faktura {invoice_number} generisana',
        'payment': payment.to_dict()
    }), 201


# ============================================================================
# BLOCK / UNBLOCK
# ============================================================================

@bp.route('/block/<int:tenant_id>', methods=['POST'])
@platform_admin_required
def block_tenant_for_payment(tenant_id):
    """
    Blokira servis zbog neplaćanja.

    Body JSON:
        - reason: razlog blokade (opciono, default: "Neplaćanje")
    """
    tenant = Tenant.query.get_or_404(tenant_id)
    data = request.get_json() or {}

    if tenant.status == TenantStatus.SUSPENDED:
        return jsonify({'error': 'Servis je već blokiran'}), 400

    reason = data.get('reason', 'Neplaćanje')
    old_status = tenant.status.value

    tenant.block(reason)

    # Sistemska poruka
    TenantMessage.create_system_message(
        tenant_id=tenant.id,
        subject='Nalog blokiran zbog neplaćanja',
        body=f'''Vaš nalog je blokiran.

Razlog: {reason}

Dok je nalog blokiran, ne možete kreirati nove servisne naloge,
dodavati inventar ili koristiti marketplace.

Da biste ponovo aktivirali nalog:
1. Izvršite uplatu za dospele fakture
2. Ili koristite opciju "Uključenje na reč" (48h)

Ako smatrate da je ovo greška, kontaktirajte podršku.''',
        category=MessageCategory.BILLING,
        priority=MessagePriority.URGENT,
        action_url='/settings/subscription',
        action_label='Reši dugovanje'
    )

    # Audit log
    AdminActivityLog.log(
        action_type=AdminActionType.BLOCK_TENANT,
        target_type='tenant',
        target_id=tenant.id,
        target_name=tenant.name,
        old_status=old_status,
        new_status='SUSPENDED',
        details={'reason': reason}
    )

    db.session.commit()

    return jsonify({
        'message': f'Servis "{tenant.name}" blokiran',
        'reason': reason
    })


@bp.route('/unblock/<int:tenant_id>', methods=['POST'])
@platform_admin_required
def unblock_tenant_for_payment(tenant_id):
    """
    Deblokira servis (ručno od admina).

    Body JSON:
        - reason: razlog deblokade (opciono)
    """
    tenant = Tenant.query.get_or_404(tenant_id)
    data = request.get_json() or {}

    if tenant.status != TenantStatus.SUSPENDED:
        return jsonify({'error': 'Servis nije blokiran'}), 400

    reason = data.get('reason', 'Admin deblokada')

    tenant.unblock()

    # Sistemska poruka
    TenantMessage.create_system_message(
        tenant_id=tenant.id,
        subject='Nalog ponovo aktivan',
        body=f'''Vaš nalog je ponovo aktivan.

Razlog deblokade: {reason}

Sada možete koristiti sve funkcije platforme.

Hvala na razumevanju!''',
        category=MessageCategory.BILLING,
        priority=MessagePriority.NORMAL
    )

    # Audit log
    AdminActivityLog.log(
        action_type=AdminActionType.UNBLOCK_TENANT,
        target_type='tenant',
        target_id=tenant.id,
        target_name=tenant.name,
        old_status='SUSPENDED',
        new_status='ACTIVE',
        details={'reason': reason}
    )

    db.session.commit()

    return jsonify({
        'message': f'Servis "{tenant.name}" deblokiran',
        'status': tenant.status.value
    })


# ============================================================================
# CUSTOM CENE
# ============================================================================

@bp.route('/pricing/<int:tenant_id>', methods=['PUT'])
@platform_admin_required
def update_tenant_pricing(tenant_id):
    """
    Postavlja custom cene za servis.

    Body JSON:
        - custom_base_price: cena baznog paketa (null za platformsku)
        - custom_location_price: cena dodatne lokacije (null za platformsku)
        - reason: razlog za custom cenu
        - valid_from: od kada važi (YYYY-MM-DD, default: danas)
    """
    tenant = Tenant.query.get_or_404(tenant_id)
    data = request.get_json() or {}
    settings = PlatformSettings.get_settings()

    old_base = tenant.custom_base_price
    old_location = tenant.custom_location_price

    # Update cene
    if 'custom_base_price' in data:
        tenant.custom_base_price = Decimal(str(data['custom_base_price'])) if data['custom_base_price'] else None

    if 'custom_location_price' in data:
        tenant.custom_location_price = Decimal(str(data['custom_location_price'])) if data['custom_location_price'] else None

    tenant.custom_price_reason = data.get('reason')

    if data.get('valid_from'):
        tenant.custom_price_valid_from = datetime.strptime(data['valid_from'], '%Y-%m-%d').date()
    else:
        tenant.custom_price_valid_from = date.today()

    # Sistemska poruka
    new_base = tenant.custom_base_price or settings.base_price
    new_location = tenant.custom_location_price or settings.location_price

    TenantMessage.create_system_message(
        tenant_id=tenant.id,
        subject='Promena cene paketa',
        body=f'''Cena vašeg paketa je promenjena.

Nova cena baznog paketa: {float(new_base):,.2f} RSD/mesec
Nova cena dodatne lokacije: {float(new_location):,.2f} RSD/mesec

Razlog: {data.get('reason', 'Nije navedeno')}
Važi od: {tenant.custom_price_valid_from.strftime("%d.%m.%Y.")}

Nova cena će se primenjivati na sledeću fakturu.''',
        category=MessageCategory.PACKAGE_CHANGE,
        priority=MessagePriority.HIGH
    )

    # Audit log
    AdminActivityLog.log(
        action_type=AdminActionType.UPDATE_PRICING,
        target_type='tenant',
        target_id=tenant.id,
        target_name=tenant.name,
        details={
            'old_base_price': float(old_base) if old_base else None,
            'new_base_price': float(tenant.custom_base_price) if tenant.custom_base_price else None,
            'old_location_price': float(old_location) if old_location else None,
            'new_location_price': float(tenant.custom_location_price) if tenant.custom_location_price else None,
            'reason': data.get('reason')
        }
    )

    db.session.commit()

    return jsonify({
        'message': f'Cene za "{tenant.name}" ažurirane',
        'custom_base_price': float(tenant.custom_base_price) if tenant.custom_base_price else None,
        'custom_location_price': float(tenant.custom_location_price) if tenant.custom_location_price else None,
        'reason': tenant.custom_price_reason,
        'valid_from': tenant.custom_price_valid_from.isoformat() if tenant.custom_price_valid_from else None
    })


# ============================================================================
# SLANJE PORUKE SERVISU
# ============================================================================

@bp.route('/message/<int:tenant_id>', methods=['POST'])
@platform_admin_required
def send_message_to_tenant(tenant_id):
    """
    Šalje poruku servisu od admina.

    Body JSON:
        - subject: naslov (obavezno)
        - body: tekst poruke (obavezno)
        - category: BILLING/SUPPORT/ANNOUNCEMENT/OTHER (default: SUPPORT)
        - priority: LOW/NORMAL/HIGH/URGENT (default: NORMAL)
    """
    tenant = Tenant.query.get_or_404(tenant_id)
    data = request.get_json() or {}

    subject = data.get('subject')
    body = data.get('body')

    if not subject or not body:
        return jsonify({'error': 'Subject i body su obavezni'}), 400

    # Parse category
    try:
        category = MessageCategory(data.get('category', 'SUPPORT'))
    except ValueError:
        category = MessageCategory.SUPPORT

    # Parse priority
    try:
        priority = MessagePriority(data.get('priority', 'NORMAL'))
    except ValueError:
        priority = MessagePriority.NORMAL

    # Kreiraj poruku
    message = TenantMessage.create_admin_message(
        tenant_id=tenant.id,
        admin_id=g.current_admin.id,
        subject=subject,
        body=body,
        category=category,
        priority=priority
    )

    # Audit log
    AdminActivityLog.log(
        action_type=AdminActionType.SEND_MESSAGE,
        target_type='tenant',
        target_id=tenant.id,
        target_name=tenant.name,
        details={
            'message_id': message.id,
            'subject': subject,
            'category': category.value,
            'priority': priority.value
        }
    )

    db.session.commit()

    return jsonify({
        'message': f'Poruka poslata servisu "{tenant.name}"',
        'message_id': message.id
    }), 201
