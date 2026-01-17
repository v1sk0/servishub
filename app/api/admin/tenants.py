"""
Admin API - Upravljanje tenantima (servisima).

Endpointi za platformske administratore za pregled i upravljanje
svim registrovanim servisima na platformi.
"""

from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, g
from sqlalchemy import func, and_

from app.extensions import db
from app.models import Tenant, User, ServiceTicket, SubscriptionPayment
from app.models.representative import ServiceRepresentative, RepresentativeStatus
from app.models.admin_activity import AdminActivityLog, AdminActionType
from app.api.middleware.auth import platform_admin_required

bp = Blueprint('admin_tenants', __name__, url_prefix='/tenants')


# ============================================================================
# LISTA I PRETRAGA TENANATA
# ============================================================================

@bp.route('', methods=['GET'])
@platform_admin_required
def list_tenants():
    """
    Lista svih tenanata sa filterima i paginacijom.

    Query params:
        - page: broj stranice (default 1)
        - per_page: broj po stranici (default 20, max 100)
        - status: filter po statusu (TRIAL, ACTIVE, SUSPENDED, CANCELLED)
        - search: pretraga po imenu ili email-u
        - sort: polje za sortiranje (created_at, name, status)
        - order: asc ili desc
    """
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)
    status = request.args.get('status')
    search = request.args.get('search', '').strip()
    sort = request.args.get('sort', 'created_at')
    order = request.args.get('order', 'desc')

    # Bazni query
    query = Tenant.query

    # Filter po statusu
    if status:
        query = query.filter(Tenant.status == status)

    # Pretraga
    if search:
        search_term = f'%{search}%'
        query = query.filter(
            db.or_(
                Tenant.name.ilike(search_term),
                Tenant.email.ilike(search_term),
                Tenant.slug.ilike(search_term)
            )
        )

    # Sortiranje
    sort_column = getattr(Tenant, sort, Tenant.created_at)
    if order == 'desc':
        sort_column = sort_column.desc()
    query = query.order_by(sort_column)

    # Paginacija
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    tenants_data = []
    for tenant in pagination.items:
        # Broj korisnika
        user_count = User.query.filter_by(tenant_id=tenant.id).count()

        # Broj lokacija
        from app.models.tenant import ServiceLocation
        locations_count = ServiceLocation.query.filter_by(tenant_id=tenant.id, is_active=True).count()

        # Broj tiketa ovog meseca
        start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0)
        tickets_this_month = ServiceTicket.query.filter(
            ServiceTicket.tenant_id == tenant.id,
            ServiceTicket.created_at >= start_of_month
        ).count()

        tenants_data.append({
            'id': tenant.id,
            'name': tenant.name,
            'slug': tenant.slug,
            'email': tenant.email,
            'phone': tenant.telefon,  # Ispravka: telefon -> telefon
            'status': tenant.status.value if tenant.status else None,
            'subscription_plan': 'Bazni',  # TODO: Dodati subscription_plan u model
            'demo_ends_at': tenant.demo_ends_at.isoformat() if tenant.demo_ends_at else None,
            'trial_ends_at': tenant.trial_ends_at.isoformat() if tenant.trial_ends_at else None,
            'subscription_ends_at': tenant.subscription_ends_at.isoformat() if tenant.subscription_ends_at else None,
            'locations_count': locations_count,
            'user_count': user_count,
            'tickets_this_month': tickets_this_month,
            'created_at': tenant.created_at.isoformat(),
            'is_trial_expired': False  # TODO: Dodati logiku za proveru isteka
        })

    return jsonify({
        'tenants': tenants_data,
        'pagination': {
            'page': pagination.page,
            'per_page': pagination.per_page,
            'total': pagination.total,
            'pages': pagination.pages,
            'has_next': pagination.has_next,
            'has_prev': pagination.has_prev
        }
    }), 200


@bp.route('/<int:tenant_id>', methods=['GET'])
@platform_admin_required
def get_tenant(tenant_id):
    """
    Detalji jednog tenanta sa svim povezanim podacima.
    """
    tenant = Tenant.query.get_or_404(tenant_id)

    # Broj korisnika
    users = User.query.filter_by(tenant_id=tenant.id).all()

    # Statistika tiketa
    total_tickets = ServiceTicket.query.filter_by(tenant_id=tenant.id).count()

    # Poslednje uplate
    payments = SubscriptionPayment.query.filter_by(tenant_id=tenant.id)\
        .order_by(SubscriptionPayment.created_at.desc())\
        .limit(10).all()

    # KYC reprezentativi
    representatives = ServiceRepresentative.query.filter_by(tenant_id=tenant.id).all()

    # Broj lokacija
    from app.models.tenant import ServiceLocation
    locations_count = ServiceLocation.query.filter_by(tenant_id=tenant.id, is_active=True).count()

    # Flat response - svi podaci na istom nivou za frontend
    return jsonify({
        # Osnovni podaci tenanta
        'id': tenant.id,
        'name': tenant.name,
        'slug': tenant.slug,
        'email': tenant.email,
        'phone': tenant.telefon,
        'telefon': tenant.telefon,
        'address': tenant.adresa_sedista,
        'adresa_sedista': tenant.adresa_sedista,
        'city': None,  # TODO: Dodati city u model ako je potrebno
        'pib': tenant.pib,
        'maticni_broj': tenant.maticni_broj,
        'bank_account': tenant.bank_account,
        'status': tenant.status.value if tenant.status else None,
        'subscription_plan': 'Bazni',  # TODO: Dodati subscription_plan u model
        'demo_ends_at': tenant.demo_ends_at.isoformat() if tenant.demo_ends_at else None,
        'trial_ends_at': tenant.trial_ends_at.isoformat() if tenant.trial_ends_at else None,
        'subscription_ends_at': tenant.subscription_ends_at.isoformat() if tenant.subscription_ends_at else None,
        'locations_count': locations_count,
        'users_count': len(users),
        'settings': tenant.settings_json,
        'created_at': tenant.created_at.isoformat(),
        'updated_at': tenant.updated_at.isoformat() if tenant.updated_at else None,
        # Povezani podaci
        'users': [{
            'id': u.id,
            'email': u.email,
            'full_name': u.full_name,
            'role': u.role.value if u.role else None,
            'is_active': u.is_active,
            'last_login_at': u.last_login_at.isoformat() if u.last_login_at else None
        } for u in users],
        'stats': {
            'tickets_total': total_tickets,
            'tickets_this_month': ServiceTicket.query.filter(
                ServiceTicket.tenant_id == tenant.id,
                ServiceTicket.created_at >= datetime.utcnow().replace(day=1, hour=0, minute=0, second=0)
            ).count(),
            'phones_total': 0,
            'parts_total': 0
        },
        'payments': [{
            'id': p.id,
            'amount': float(p.amount),
            'status': p.status,
            'period_start': p.period_start.isoformat() if p.period_start else None,
            'period_end': p.period_end.isoformat() if p.period_end else None,
            'created_at': p.created_at.isoformat()
        } for p in payments],
        'representatives': [{
            'id': r.id,
            'full_name': r.full_name,
            'email': r.email,
            'telefon': r.telefon,
            'jmbg_masked': f'*********{r.jmbg[-4:]}' if r.jmbg and len(r.jmbg) >= 4 else None,
            'broj_licne_karte': r.broj_licne_karte,
            'lk_front_url': r.lk_front_url,
            'lk_back_url': r.lk_back_url,
            'is_primary': r.is_primary,
            'status': r.status.value if r.status else None,
            'verified_at': r.verified_at.isoformat() if r.verified_at else None
        } for r in representatives]
    }), 200


# ============================================================================
# UPRAVLJANJE STATUSOM TENANTA
# ============================================================================

@bp.route('/<int:tenant_id>/activate-trial', methods=['POST'])
@platform_admin_required
def activate_trial(tenant_id):
    """
    Produzuje ili resetuje TRIAL period za tenant.

    Ovo radi admin kada zeli da produzi besplatni period.
    - Menja status na TRIAL (ako je EXPIRED)
    - Postavlja trial_ends_at na 60 dana od sada
    - Verifikuje primarnog KYC predstavnika ako nije vec verifikovan
    """
    tenant = Tenant.query.get_or_404(tenant_id)

    from app.models.tenant import TenantStatus

    old_status = tenant.status.value

    # Dozvoli za TRIAL (produljenje) ili EXPIRED (reaktivacija)
    if tenant.status not in (TenantStatus.TRIAL, TenantStatus.EXPIRED):
        return jsonify({
            'error': f'Tenant mora biti u TRIAL ili EXPIRED statusu. Trenutni status: {tenant.status.value}'
        }), 400

    # Postavi/produzi TRIAL
    tenant.status = TenantStatus.TRIAL
    tenant.trial_ends_at = datetime.utcnow() + timedelta(days=60)

    # Verifikuj primarnog predstavnika
    primary_rep = ServiceRepresentative.query.filter_by(
        tenant_id=tenant.id,
        is_primary=True
    ).first()

    if primary_rep:
        primary_rep.status = RepresentativeStatus.VERIFIED
        primary_rep.verified_at = datetime.utcnow()
        primary_rep.verified_by_id = g.current_admin.id

    # Audit log
    AdminActivityLog.log(
        action_type=AdminActionType.ACTIVATE_TRIAL,
        target_type='tenant',
        target_id=tenant.id,
        target_name=tenant.name,
        old_status=old_status,
        new_status='TRIAL',
        details={
            'trial_ends_at': tenant.trial_ends_at.isoformat(),
            'representative_verified': primary_rep.id if primary_rep else None
        }
    )

    db.session.commit()

    return jsonify({
        'message': f'TRIAL aktiviran za "{tenant.name}" (60 dana).',
        'tenant_id': tenant.id,
        'status': tenant.status.value,
        'trial_ends_at': tenant.trial_ends_at.isoformat(),
        'representative_verified': primary_rep.id if primary_rep else None
    }), 200


@bp.route('/<int:tenant_id>/activate', methods=['POST'])
@platform_admin_required
def activate_tenant(tenant_id):
    """
    Aktivira tenant - postavlja status na ACTIVE i kreira SubscriptionPayment.

    Request body (JSON):
        - months: Broj meseci pretplate (1, 3, 6, 12) - default 1
        - payment_method: BANK_TRANSFER, CASH, CARD - default BANK_TRANSFER
        - payment_reference: Referenca uplate (opciono)
        - notes: Napomena (opciono)
    """
    tenant = Tenant.query.get_or_404(tenant_id)
    data = request.get_json() or {}

    # Parametri iz request body
    months = data.get('months', 1)
    payment_method = data.get('payment_method', 'BANK_TRANSFER')
    payment_reference = data.get('payment_reference', '')
    notes = data.get('notes', '')

    # Validacija meseci
    if months not in [1, 3, 6, 12]:
        return jsonify({'error': 'Broj meseci mora biti 1, 3, 6 ili 12'}), 400

    # Sacuvaj stari status za audit
    old_status = tenant.status.value if tenant.status else None

    # Ucitaj cene iz PlatformSettings
    from app.models import PlatformSettings
    settings = PlatformSettings.get_settings()
    base_price = float(settings.base_price) if settings.base_price else 3600
    location_price = float(settings.location_price) if settings.location_price else 1800

    # Izracunaj broj lokacija
    from app.models.tenant import ServiceLocation, TenantStatus
    locations_count = ServiceLocation.query.filter_by(tenant_id=tenant.id, is_active=True).count()
    locations_count = max(1, locations_count)  # Minimum 1 lokacija

    # Izracunaj mesecnu cenu
    additional_locations = max(0, locations_count - 1)
    monthly_price = base_price + (additional_locations * location_price)
    total_amount = monthly_price * months

    # Period pretplate
    period_start = datetime.utcnow().date()
    period_end = period_start + timedelta(days=30 * months)

    # Generiši broj fakture (SH-YYYY-NNNNNN)
    year = datetime.utcnow().year
    last_payment = SubscriptionPayment.query.filter(
        SubscriptionPayment.invoice_number.like(f'SH-{year}-%')
    ).order_by(SubscriptionPayment.id.desc()).first()

    if last_payment and last_payment.invoice_number:
        last_num = int(last_payment.invoice_number.split('-')[-1])
        next_num = last_num + 1
    else:
        next_num = 1
    invoice_number = f'SH-{year}-{next_num:06d}'

    # Kreiraj stavke fakture
    items = [
        {
            'description': 'Bazni paket ServisHub',
            'quantity': months,
            'unit_price': base_price,
            'total': base_price * months
        }
    ]
    if additional_locations > 0:
        items.append({
            'description': f'Dodatne lokacije ({additional_locations})',
            'quantity': months,
            'unit_price': location_price * additional_locations,
            'total': location_price * additional_locations * months
        })

    # Kreiraj SubscriptionPayment
    payment = SubscriptionPayment(
        tenant_id=tenant.id,
        invoice_number=invoice_number,
        period_start=period_start,
        period_end=period_end,
        items_json=items,
        subtotal=total_amount,
        total_amount=total_amount,
        currency='RSD',
        status='PAID',  # Direktno PAID jer admin aktivira
        paid_at=datetime.utcnow(),
        payment_method=payment_method,
        payment_reference=payment_reference,
        payment_notes=notes,
        verified_by_id=g.current_admin.id,
        verified_at=datetime.utcnow(),
        is_auto_generated=False
    )
    db.session.add(payment)

    # Postavi status i period pretplate
    tenant.status = TenantStatus.ACTIVE
    tenant.subscription_ends_at = datetime.combine(period_end, datetime.min.time())

    # Audit log
    AdminActivityLog.log(
        action_type=AdminActionType.ACTIVATE_SUBSCRIPTION,
        target_type='tenant',
        target_id=tenant.id,
        target_name=tenant.name,
        old_status=old_status,
        new_status='ACTIVE',
        details={
            'subscription_ends_at': tenant.subscription_ends_at.isoformat(),
            'months': months,
            'total_amount': total_amount,
            'invoice_number': invoice_number,
            'payment_method': payment_method,
            'locations_count': locations_count
        }
    )

    db.session.commit()

    return jsonify({
        'message': f'Pretplata za "{tenant.name}" aktivirana na {months} mesec(i).',
        'tenant_id': tenant.id,
        'status': tenant.status.value,
        'subscription_ends_at': tenant.subscription_ends_at.isoformat(),
        'invoice_number': invoice_number,
        'total_amount': total_amount
    }), 200


@bp.route('/<int:tenant_id>/suspend', methods=['POST'])
@platform_admin_required
def suspend_tenant(tenant_id):
    """
    Suspenduje tenant - korisnici ne mogu da se uloguju.
    """
    tenant = Tenant.query.get_or_404(tenant_id)
    data = request.get_json() or {}
    reason = data.get('reason', 'Suspendovano od strane administratora')

    # Sacuvaj stari status za audit
    old_status = tenant.status.value if tenant.status else None

    from app.models.tenant import TenantStatus
    tenant.status = TenantStatus.SUSPENDED

    # Sacuvaj razlog u settings
    if not tenant.settings:
        tenant.settings = {}
    tenant.settings['suspension_reason'] = reason
    tenant.settings['suspended_at'] = datetime.utcnow().isoformat()
    tenant.settings['suspended_by'] = g.current_admin.id

    # Audit log
    AdminActivityLog.log(
        action_type=AdminActionType.SUSPEND_TENANT,
        target_type='tenant',
        target_id=tenant.id,
        target_name=tenant.name,
        old_status=old_status,
        new_status='SUSPENDED',
        details={
            'reason': reason
        }
    )

    db.session.commit()

    return jsonify({
        'message': f'Tenant "{tenant.name}" je suspendovan.',
        'tenant_id': tenant.id,
        'reason': reason
    }), 200


@bp.route('/<int:tenant_id>/unsuspend', methods=['POST'])
@platform_admin_required
def unsuspend_tenant(tenant_id):
    """
    Ukida suspenziju tenanta.
    """
    tenant = Tenant.query.get_or_404(tenant_id)

    from app.models.tenant import TenantStatus

    # Vrati na ACTIVE ili TRIAL zavisno od stanja
    if tenant.trial_ends_at and tenant.trial_ends_at > datetime.utcnow():
        new_status = TenantStatus.TRIAL
    else:
        new_status = TenantStatus.ACTIVE

    tenant.status = new_status

    # Ukloni suspension info
    if tenant.settings:
        tenant.settings.pop('suspension_reason', None)
        tenant.settings.pop('suspended_at', None)
        tenant.settings.pop('suspended_by', None)

    # Audit log
    AdminActivityLog.log(
        action_type=AdminActionType.UNSUSPEND_TENANT,
        target_type='tenant',
        target_id=tenant.id,
        target_name=tenant.name,
        old_status='SUSPENDED',
        new_status=new_status.value,
        details={}
    )

    db.session.commit()

    return jsonify({
        'message': f'Suspenzija za "{tenant.name}" je ukinuta.',
        'tenant_id': tenant.id,
        'status': tenant.status.value
    }), 200


@bp.route('/<int:tenant_id>/extend-trial', methods=['POST'])
@platform_admin_required
def extend_trial(tenant_id):
    """
    Produzuje trial period za tenant.
    """
    tenant = Tenant.query.get_or_404(tenant_id)
    data = request.get_json() or {}
    days = data.get('days', 30)

    # Sacuvaj stari status za audit
    old_status = tenant.status.value if tenant.status else None
    old_trial_ends = tenant.trial_ends_at.isoformat() if tenant.trial_ends_at else None

    if tenant.trial_ends_at:
        # Produzenje od trenutnog datuma isteka
        tenant.trial_ends_at = tenant.trial_ends_at + timedelta(days=days)
    else:
        # Novo postavljanje
        tenant.trial_ends_at = datetime.utcnow() + timedelta(days=days)

    from app.models.tenant import TenantStatus
    tenant.status = TenantStatus.TRIAL

    # Audit log
    AdminActivityLog.log(
        action_type=AdminActionType.EXTEND_TRIAL,
        target_type='tenant',
        target_id=tenant.id,
        target_name=tenant.name,
        old_status=old_status,
        new_status='TRIAL',
        details={
            'days_extended': days,
            'old_trial_ends_at': old_trial_ends,
            'new_trial_ends_at': tenant.trial_ends_at.isoformat()
        }
    )

    db.session.commit()

    return jsonify({
        'message': f'Trial za "{tenant.name}" produžen za {days} dana.',
        'tenant_id': tenant.id,
        'trial_ends_at': tenant.trial_ends_at.isoformat()
    }), 200


# ============================================================================
# UPRAVLJANJE LOKACIJAMA
# ============================================================================

@bp.route('/<int:tenant_id>/locations', methods=['PUT'])
@platform_admin_required
def update_locations_count(tenant_id):
    """
    Azurira broj dozvoljenih lokacija za tenanta.
    """
    tenant = Tenant.query.get_or_404(tenant_id)
    data = request.get_json() or {}

    new_count = data.get('locations_count')
    if new_count is None or new_count < 1:
        return jsonify({'error': 'locations_count mora biti >= 1'}), 400

    tenant.locations_count = new_count
    db.session.commit()

    return jsonify({
        'message': f'Broj lokacija za "{tenant.name}" ažuriran na {new_count}.',
        'tenant_id': tenant.id,
        'locations_count': tenant.locations_count
    }), 200


# ============================================================================
# AZURIRANJE PODATAKA TENANTA (EDIT)
# ============================================================================

@bp.route('/<int:tenant_id>', methods=['PUT'])
@platform_admin_required
def update_tenant(tenant_id):
    """
    Azurira osnovne podatke tenanta.

    Body JSON:
        - name: Novi naziv preduzeca
        - email: Nova email adresa
        - telefon: Novi telefon
        - adresa_sedista: Nova adresa
        - pib: Novi PIB (ako se menja)
        - maticni_broj: Novi maticni broj
        - bank_account: Novi bankovni racun
    """
    tenant = Tenant.query.get_or_404(tenant_id)
    data = request.get_json() or {}

    # Sacuvaj stare vrednosti za audit
    old_values = {
        'name': tenant.name,
        'email': tenant.email,
        'telefon': tenant.telefon,
        'adresa_sedista': tenant.adresa_sedista,
        'pib': tenant.pib,
        'maticni_broj': tenant.maticni_broj,
        'bank_account': tenant.bank_account,
    }

    # Azuriraj polja koja su prosledjena
    changes = {}

    if 'name' in data and data['name'] != tenant.name:
        tenant.name = data['name']
        changes['name'] = {'old': old_values['name'], 'new': data['name']}

    if 'email' in data and data['email'] != tenant.email:
        tenant.email = data['email']
        changes['email'] = {'old': old_values['email'], 'new': data['email']}

    if 'telefon' in data and data['telefon'] != tenant.telefon:
        tenant.telefon = data['telefon']
        changes['telefon'] = {'old': old_values['telefon'], 'new': data['telefon']}

    if 'adresa_sedista' in data and data['adresa_sedista'] != tenant.adresa_sedista:
        tenant.adresa_sedista = data['adresa_sedista']
        changes['adresa_sedista'] = {'old': old_values['adresa_sedista'], 'new': data['adresa_sedista']}

    if 'pib' in data and data['pib'] != tenant.pib:
        # Proveri da PIB nije vec zauzet
        existing = Tenant.query.filter(Tenant.pib == data['pib'], Tenant.id != tenant_id).first()
        if existing:
            return jsonify({'error': f'PIB {data["pib"]} je vec zauzet od strane drugog servisa.'}), 400
        tenant.pib = data['pib']
        changes['pib'] = {'old': old_values['pib'], 'new': data['pib']}

    if 'maticni_broj' in data and data['maticni_broj'] != tenant.maticni_broj:
        tenant.maticni_broj = data['maticni_broj']
        changes['maticni_broj'] = {'old': old_values['maticni_broj'], 'new': data['maticni_broj']}

    if 'bank_account' in data and data['bank_account'] != tenant.bank_account:
        tenant.bank_account = data['bank_account']
        changes['bank_account'] = {'old': old_values['bank_account'], 'new': data['bank_account']}

    # Ako nema promena
    if not changes:
        return jsonify({'message': 'Nema promena za sacuvati.'}), 200

    # Audit log
    AdminActivityLog.log(
        action_type=AdminActionType.UPDATE_TENANT,
        target_type='tenant',
        target_id=tenant.id,
        target_name=tenant.name,
        details={'changes': changes}
    )

    tenant.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'message': f'Podaci za "{tenant.name}" uspesno azurirani.',
        'tenant_id': tenant.id,
        'changes': changes
    }), 200


# ============================================================================
# BRISANJE TENANTA SA OPCIONALNIM BACKUP-OM
# ============================================================================

@bp.route('/<int:tenant_id>', methods=['DELETE'])
@platform_admin_required
def delete_tenant(tenant_id):
    """
    Brise tenanta i sve njegove podatke.

    Zahteva potvrdu unosom reci "obrisi" u request body.
    Opciono kreira enkriptovani backup pre brisanja.

    Body JSON:
        - confirmation: Mora biti "obrisi" za potvrdu
        - create_backup: Boolean - da li kreirati backup (default: True)
    """
    tenant = Tenant.query.get_or_404(tenant_id)
    data = request.get_json() or {}

    # Proveri potvrdu
    confirmation = data.get('confirmation', '').lower().strip()
    if confirmation != 'obrisi':
        return jsonify({
            'error': 'Morate uneti "obrisi" za potvrdu brisanja.',
            'message': 'Brisanje otkazano - netacna potvrda.'
        }), 400

    # Da li radimo backup?
    create_backup = data.get('create_backup', True)

    # Sacuvaj podatke za audit pre brisanja
    tenant_name = tenant.name
    tenant_email = tenant.email
    tenant_pib = tenant.pib

    # Izvrsi brisanje (sa ili bez backup-a)
    from app.services.tenant_backup_service import tenant_backup_service
    success, message = tenant_backup_service.backup_and_delete_tenant(
        tenant_id=tenant_id,
        admin_email=g.current_admin.email,
        create_backup=create_backup
    )

    if not success:
        return jsonify({
            'error': 'Greska pri brisanju',
            'message': message
        }), 500

    # Audit log - nakon uspesnog brisanja
    # Napomena: tenant vise ne postoji, tako da ne mozemo referencirati tenant.id
    AdminActivityLog.log(
        action_type=AdminActionType.DELETE_TENANT,
        target_type='tenant',
        target_id=tenant_id,  # ID tenanta koji je obrisan
        target_name=tenant_name,
        details={
            'tenant_email': tenant_email,
            'tenant_pib': tenant_pib,
            'backup_created': create_backup
        }
    )

    return jsonify({
        'message': message,
        'deleted_tenant_id': tenant_id,
        'deleted_tenant_name': tenant_name,
        'backup_created': create_backup
    }), 200
