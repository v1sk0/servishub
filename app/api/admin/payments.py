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
from app.services.billing_tasks import get_next_invoice_number
from app.services.ips_service import IPSService
from app.services.pdf_service import PDFService

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


@bp.route('/stats', methods=['GET'])
@platform_admin_required
def get_payments_stats():
    """
    Statistike faktura za dashboard kartice.

    Returns:
        - pending: broj i suma faktura na čekanju
        - paid: broj i suma plaćenih faktura (ovaj mesec)
        - overdue: broj i suma zakasnelih faktura
        - monthly_total: ukupno naplaćeno ovog meseca
    """
    today = date.today()
    start_of_month = today.replace(day=1)

    # Pending
    pending_count = SubscriptionPayment.query.filter(
        SubscriptionPayment.status == 'PENDING'
    ).count()
    pending_amount = db.session.query(
        func.coalesce(func.sum(SubscriptionPayment.total_amount), 0)
    ).filter(
        SubscriptionPayment.status == 'PENDING'
    ).scalar() or 0

    # Overdue
    overdue_count = SubscriptionPayment.query.filter(
        SubscriptionPayment.status.in_(['PENDING', 'OVERDUE']),
        SubscriptionPayment.due_date < today
    ).count()
    overdue_amount = db.session.query(
        func.coalesce(func.sum(SubscriptionPayment.total_amount), 0)
    ).filter(
        SubscriptionPayment.status.in_(['PENDING', 'OVERDUE']),
        SubscriptionPayment.due_date < today
    ).scalar() or 0

    # Paid this month
    paid_count = SubscriptionPayment.query.filter(
        SubscriptionPayment.status == 'PAID',
        SubscriptionPayment.paid_at >= start_of_month
    ).count()
    paid_amount = db.session.query(
        func.coalesce(func.sum(SubscriptionPayment.total_amount), 0)
    ).filter(
        SubscriptionPayment.status == 'PAID',
        SubscriptionPayment.paid_at >= start_of_month
    ).scalar() or 0

    # Monthly total (all PAID in current month)
    monthly_total = db.session.query(
        func.coalesce(func.sum(SubscriptionPayment.total_amount), 0)
    ).filter(
        SubscriptionPayment.status == 'PAID',
        SubscriptionPayment.created_at >= start_of_month
    ).scalar() or 0

    return jsonify({
        'pending': {
            'count': pending_count,
            'amount': float(pending_amount)
        },
        'paid': {
            'count': paid_count,
            'amount': float(paid_amount)
        },
        'overdue': {
            'count': overdue_count,
            'amount': float(overdue_amount)
        },
        'monthly_total': float(monthly_total),
        'currency': 'RSD',
        'as_of': today.isoformat()
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

    # Kreiraj fakturu (race-safe sa SELECT FOR UPDATE)
    invoice_number = get_next_invoice_number(datetime.utcnow().year)

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


# ============================================================================
# PDF / UPLATNICA ENDPOINTS
# ============================================================================

@bp.route('/<int:payment_id>/pdf', methods=['GET'])
@platform_admin_required
def download_invoice_pdf(payment_id):
    """
    Download invoice PDF.

    Response: application/pdf file
    """
    from flask import send_file
    from io import BytesIO

    payment = SubscriptionPayment.query.get_or_404(payment_id)
    tenant = Tenant.query.get(payment.tenant_id)
    settings = PlatformSettings.get_settings()

    # Generate IPS QR if not exists
    if not payment.ips_qr_string:
        ips_service = IPSService(settings)
        payment.ips_qr_string = ips_service.generate_qr_string(payment, tenant, settings)
        payment.ips_qr_generated_at = datetime.utcnow()
        db.session.commit()

    pdf_service = PDFService(settings)
    pdf_bytes = pdf_service.generate_invoice_pdf(payment, tenant, settings)

    return send_file(
        BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'faktura-{payment.invoice_number}.pdf'
    )


@bp.route('/<int:payment_id>/uplatnica', methods=['GET'])
@platform_admin_required
def download_uplatnica(payment_id):
    """
    Download payment slip (uplatnica) PDF.

    Response: application/pdf file
    """
    from flask import send_file
    from io import BytesIO

    payment = SubscriptionPayment.query.get_or_404(payment_id)
    tenant = Tenant.query.get(payment.tenant_id)
    settings = PlatformSettings.get_settings()

    # Generate IPS QR if not exists
    if not payment.ips_qr_string:
        ips_service = IPSService(settings)
        payment.ips_qr_string = ips_service.generate_qr_string(payment, tenant, settings)
        payment.ips_qr_generated_at = datetime.utcnow()
        db.session.commit()

    pdf_service = PDFService(settings)
    pdf_bytes = pdf_service.generate_uplatnica(payment, tenant, settings)

    return send_file(
        BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'uplatnica-{payment.invoice_number}.pdf'
    )


@bp.route('/<int:payment_id>/qr', methods=['GET'])
@platform_admin_required
def get_qr_code(payment_id):
    """
    Get IPS QR code as PNG image.

    Query params:
        - size: int (default 300)

    Response: image/png
    """
    from flask import send_file
    from io import BytesIO

    payment = SubscriptionPayment.query.get_or_404(payment_id)
    tenant = Tenant.query.get(payment.tenant_id)
    settings = PlatformSettings.get_settings()

    size = request.args.get('size', 300, type=int)

    ips_service = IPSService(settings)

    if not payment.ips_qr_string:
        payment.ips_qr_string = ips_service.generate_qr_string(payment, tenant, settings)
        payment.ips_qr_generated_at = datetime.utcnow()
        db.session.commit()

    qr_bytes = ips_service.generate_qr_image(payment.ips_qr_string, size=size)

    return send_file(
        BytesIO(qr_bytes),
        mimetype='image/png'
    )


@bp.route('/<int:payment_id>/qr-string', methods=['GET'])
@platform_admin_required
def get_qr_string(payment_id):
    """
    Get raw IPS QR string (for debugging or custom rendering).

    Response:
    {
        "qr_string": "K:PR|V:01|...",
        "generated_at": "2026-01-24T10:30:00"
    }
    """
    payment = SubscriptionPayment.query.get_or_404(payment_id)
    tenant = Tenant.query.get(payment.tenant_id)
    settings = PlatformSettings.get_settings()

    ips_service = IPSService(settings)

    if not payment.ips_qr_string:
        payment.ips_qr_string = ips_service.generate_qr_string(payment, tenant, settings)
        payment.ips_qr_generated_at = datetime.utcnow()
        db.session.commit()

    return jsonify({
        'qr_string': payment.ips_qr_string,
        'generated_at': payment.ips_qr_generated_at.isoformat() if payment.ips_qr_generated_at else None,
        'payment_reference': payment.payment_reference
    })


@bp.route('/<int:payment_id>/regenerate-qr', methods=['POST'])
@platform_admin_required
def regenerate_qr(payment_id):
    """
    Regenerate IPS QR code (if settings changed).

    Response:
    {
        "qr_string": "K:PR|V:01|...",
        "generated_at": "2026-01-24T10:30:00"
    }
    """
    payment = SubscriptionPayment.query.get_or_404(payment_id)
    tenant = Tenant.query.get(payment.tenant_id)
    settings = PlatformSettings.get_settings()

    ips_service = IPSService(settings)

    payment.ips_qr_string = ips_service.generate_qr_string(payment, tenant, settings)
    payment.ips_qr_generated_at = datetime.utcnow()

    db.session.commit()

    return jsonify({
        'message': 'QR kod regenerisan',
        'qr_string': payment.ips_qr_string,
        'generated_at': payment.ips_qr_generated_at.isoformat()
    })


# ============================================================================
# RECONCILIATION SUMMARY
# ============================================================================

@bp.route('/reconciliation/summary', methods=['GET'])
@platform_admin_required
def get_reconciliation_summary():
    """
    Sažetak reconciliation aktivnosti.

    Query params:
        - days: int (default 30)

    Response:
    {
        "period_days": 30,
        "reconciled": {"count": 42, "amount": 226800.00},
        "pending_payments": {"count": 5, "amount": 27000.00},
        "unmatched_transactions": {"count": 3, "amount": 16200.00}
    }
    """
    from app.services.reconciliation import get_reconciliation_summary as get_summary

    days = request.args.get('days', 30, type=int)
    summary = get_summary(days=days)

    return jsonify(summary)


# ============================================================================
# SEND INVOICE EMAIL
# ============================================================================

@bp.route('/<int:payment_id>/send', methods=['POST'])
@platform_admin_required
def send_invoice_email(payment_id):
    """
    Šalje fakturu na email tenanta sa PDF attachment-om.

    Body JSON:
        - include_pdf: bool (default true) - priloži PDF fakturu
        - include_uplatnica: bool (default true) - priloži uplatnicu
        - custom_message: str (opciono) - dodatna poruka

    Response:
    {
        "message": "Faktura poslata na email",
        "sent_to": "office@example.com",
        "sent_at": "2026-01-25T12:00:00"
    }
    """
    from io import BytesIO
    import base64

    payment = SubscriptionPayment.query.get_or_404(payment_id)
    tenant = Tenant.query.get(payment.tenant_id)
    settings = PlatformSettings.get_settings()
    data = request.get_json() or {}

    if not tenant.email:
        return jsonify({'error': 'Tenant nema email adresu'}), 400

    include_pdf = data.get('include_pdf', True)
    include_uplatnica = data.get('include_uplatnica', True)
    custom_message = data.get('custom_message', '')

    # Generate IPS QR if not exists
    if not payment.ips_qr_string:
        ips_service = IPSService(settings)
        payment.ips_qr_string = ips_service.generate_qr_string(payment, tenant, settings)
        payment.ips_qr_generated_at = datetime.utcnow()

    # Prepare attachments
    attachments = []
    pdf_service = PDFService(settings)

    if include_pdf:
        pdf_bytes = pdf_service.generate_invoice_pdf(payment, tenant, settings)
        attachments.append({
            'filename': f'faktura-{payment.invoice_number}.pdf',
            'content': base64.b64encode(pdf_bytes).decode('utf-8'),
            'type': 'application/pdf'
        })

    if include_uplatnica:
        uplatnica_bytes = pdf_service.generate_uplatnica(payment, tenant, settings)
        attachments.append({
            'filename': f'uplatnica-{payment.invoice_number}.pdf',
            'content': base64.b64encode(uplatnica_bytes).decode('utf-8'),
            'type': 'application/pdf'
        })

    # Send email with attachments
    from app.services.email_service import email_service

    period = f"{payment.period_start.strftime('%d.%m.%Y')} - {payment.period_end.strftime('%d.%m.%Y')}" if payment.period_start and payment.period_end else "N/A"
    due_date = payment.due_date.strftime('%d.%m.%Y') if payment.due_date else "N/A"

    success = _send_invoice_with_attachments(
        email_service=email_service,
        to_email=tenant.email,
        tenant_name=tenant.name,
        invoice_number=payment.invoice_number,
        amount=float(payment.total_amount),
        due_date=due_date,
        period=period,
        payment_reference=payment.payment_reference or payment.invoice_number,
        bank_account=settings.company_bank_account,
        custom_message=custom_message,
        attachments=attachments
    )

    if success:
        # Update payment
        payment.invoice_sent_at = datetime.utcnow()
        payment.invoice_sent_to = tenant.email

        # Audit log
        AdminActivityLog.log(
            action_type=AdminActionType.SEND_INVOICE,
            target_type='payment',
            target_id=payment.id,
            target_name=payment.invoice_number,
            details={
                'tenant_id': tenant.id,
                'tenant_name': tenant.name,
                'sent_to': tenant.email,
                'include_pdf': include_pdf,
                'include_uplatnica': include_uplatnica
            }
        )

        db.session.commit()

        return jsonify({
            'message': f'Faktura {payment.invoice_number} poslata na email',
            'sent_to': tenant.email,
            'sent_at': payment.invoice_sent_at.isoformat()
        })
    else:
        return jsonify({'error': 'Slanje emaila nije uspelo'}), 500


def _send_invoice_with_attachments(
    email_service,
    to_email: str,
    tenant_name: str,
    invoice_number: str,
    amount: float,
    due_date: str,
    period: str,
    payment_reference: str,
    bank_account: str,
    custom_message: str = '',
    attachments: list = None
) -> bool:
    """
    Helper za slanje fakture sa attachmentima preko SendGrid.
    """
    import os
    import requests

    api_key = email_service.api_key
    from_email = email_service.from_email
    from_name = email_service.from_name
    frontend_url = email_service.frontend_url

    # Build HTML
    custom_html = f'<p style="background: #fef3c7; padding: 15px; border-radius: 8px; border-left: 4px solid #f59e0b;"><strong>Napomena:</strong> {custom_message}</p>' if custom_message else ''

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
            <h1 style="color: white; margin: 0;">ServisHub</h1>
            <p style="color: rgba(255,255,255,0.9); margin: 10px 0 0 0;">Faktura za pretplatu</p>
        </div>
        <div style="background: #f9fafb; padding: 30px; border: 1px solid #e5e7eb;">
            <h2 style="margin-top: 0;">Postovani {tenant_name},</h2>
            <p>U prilogu vam saljemo fakturu za koriscenje ServisHub platforme.</p>

            {custom_html}

            <div style="background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 20px; margin: 20px 0;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr><td style="padding: 8px 0; color: #6b7280;">Broj fakture:</td><td style="padding: 8px 0; text-align: right; font-weight: 600;">{invoice_number}</td></tr>
                    <tr><td style="padding: 8px 0; color: #6b7280;">Period:</td><td style="padding: 8px 0; text-align: right;">{period}</td></tr>
                    <tr><td style="padding: 8px 0; color: #6b7280;">Rok placanja:</td><td style="padding: 8px 0; text-align: right;">{due_date}</td></tr>
                    <tr style="border-top: 2px solid #e5e7eb;"><td style="padding: 12px 0; font-weight: 600;">UKUPNO:</td><td style="padding: 12px 0; text-align: right; font-size: 20px; font-weight: 700; color: #667eea;">{amount:,.0f} RSD</td></tr>
                </table>
            </div>

            <div style="background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 15px; margin: 20px 0;">
                <p style="margin: 0 0 8px 0; font-weight: 600; color: #1e40af;">Podaci za uplatu:</p>
                <p style="margin: 0; color: #1e40af;"><strong>Racun:</strong> {bank_account}</p>
                <p style="margin: 5px 0 0 0; color: #1e40af;"><strong>Poziv na broj:</strong> {payment_reference}</p>
            </div>

            <p style="color: #6b7280; font-size: 14px;">PDF faktura i uplatnica su u prilogu ovog emaila.</p>

            <div style="text-align: center; margin: 30px 0;">
                <a href="{frontend_url}/subscription" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 14px 30px; text-decoration: none; border-radius: 8px; font-weight: 600;">Pogledaj u aplikaciji</a>
            </div>
        </div>
        <div style="text-align: center; padding: 20px; color: #9ca3af; font-size: 12px;">
            <p>&copy; {datetime.now().year} ServisHub</p>
        </div>
    </body>
    </html>
    """

    text_content = f"""
ServisHub - Faktura za pretplatu

Postovani {tenant_name},

U prilogu vam saljemo fakturu za koriscenje ServisHub platforme.

{('Napomena: ' + custom_message) if custom_message else ''}

Broj fakture: {invoice_number}
Period: {period}
Rok placanja: {due_date}
UKUPNO: {amount:,.0f} RSD

Podaci za uplatu:
Racun: {bank_account}
Poziv na broj: {payment_reference}

---
(c) {datetime.now().year} ServisHub
    """

    # DEV mode - just log
    if not api_key or os.environ.get('FLASK_ENV') == 'development':
        print(f"[DEV EMAIL] To: {to_email}")
        print(f"[DEV EMAIL] Subject: ServisHub - Faktura {invoice_number}")
        print(f"[DEV EMAIL] Attachments: {len(attachments or [])} files")
        return True

    # Build SendGrid payload
    payload = {
        "personalizations": [
            {
                "to": [{"email": to_email}],
                "subject": f"ServisHub - Faktura {invoice_number}"
            }
        ],
        "from": {
            "email": from_email,
            "name": from_name
        },
        "content": [
            {"type": "text/plain", "value": text_content},
            {"type": "text/html", "value": html_content}
        ]
    }

    # Add attachments
    if attachments:
        payload["attachments"] = [
            {
                "content": att['content'],
                "filename": att['filename'],
                "type": att['type'],
                "disposition": "attachment"
            }
            for att in attachments
        ]

    try:
        response = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            timeout=30
        )

        return response.status_code in [200, 201, 202]

    except Exception as e:
        print(f"[EMAIL ERROR] {str(e)}")
        return False
