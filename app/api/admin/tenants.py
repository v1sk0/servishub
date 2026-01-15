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

    return jsonify({
        'tenant': {
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
            'updated_at': tenant.updated_at.isoformat() if tenant.updated_at else None
        },
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
    Aktivira TRIAL za tenant iz DEMO statusa.

    Ovo radi admin nakon sto kontaktira vlasnika servisa i verifikuje KYC.
    - Menja status DEMO -> TRIAL
    - Postavlja trial_ends_at na 60 dana od sada
    - Verifikuje primarnog KYC predstavnika
    """
    tenant = Tenant.query.get_or_404(tenant_id)

    from app.models.tenant import TenantStatus

    # Proveri da je tenant u DEMO statusu
    if tenant.status != TenantStatus.DEMO:
        return jsonify({
            'error': f'Tenant nije u DEMO statusu. Trenutni status: {tenant.status.value}'
        }), 400

    # Promeni status na TRIAL
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
    Aktivira tenant - postavlja status na ACTIVE.
    Koristi se nakon uspesne prve uplate.
    """
    tenant = Tenant.query.get_or_404(tenant_id)

    # Postavi status
    from app.models.tenant import TenantStatus
    tenant.status = TenantStatus.ACTIVE

    # Postavi subscription period (1 mesec od sada)
    tenant.subscription_ends_at = datetime.utcnow() + timedelta(days=30)

    db.session.commit()

    return jsonify({
        'message': f'Tenant "{tenant.name}" je aktiviran.',
        'tenant_id': tenant.id,
        'status': tenant.status.value,
        'subscription_ends_at': tenant.subscription_ends_at.isoformat()
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

    from app.models.tenant import TenantStatus
    tenant.status = TenantStatus.SUSPENDED

    # Sacuvaj razlog u settings
    if not tenant.settings:
        tenant.settings = {}
    tenant.settings['suspension_reason'] = reason
    tenant.settings['suspended_at'] = datetime.utcnow().isoformat()
    tenant.settings['suspended_by'] = g.current_admin.id

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
        tenant.status = TenantStatus.TRIAL
    else:
        tenant.status = TenantStatus.ACTIVE

    # Ukloni suspension info
    if tenant.settings:
        tenant.settings.pop('suspension_reason', None)
        tenant.settings.pop('suspended_at', None)
        tenant.settings.pop('suspended_by', None)

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

    if tenant.trial_ends_at:
        # Produzenje od trenutnog datuma isteka
        tenant.trial_ends_at = tenant.trial_ends_at + timedelta(days=days)
    else:
        # Novo postavljanje
        tenant.trial_ends_at = datetime.utcnow() + timedelta(days=days)

    from app.models.tenant import TenantStatus
    tenant.status = TenantStatus.TRIAL

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
