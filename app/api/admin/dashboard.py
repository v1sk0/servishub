"""
Admin API - Dashboard statistike.

Glavni pregled platforme za administratore sa svim kljucnim metrikama.
"""

from datetime import datetime, timedelta
from flask import Blueprint, jsonify
from sqlalchemy import func, and_

from app.extensions import db
from app.models import Tenant, User, ServiceTicket
from app.models.tenant import TenantStatus
from app.models.inventory import PhoneListing, SparePart
from app.models.supplier import Supplier, SupplierStatus
from app.models.order import PartOrder, OrderStatus
from app.models.representative import ServiceRepresentative, RepresentativeStatus, SubscriptionPayment
from app.api.middleware.auth import platform_admin_required

bp = Blueprint('admin_dashboard', __name__, url_prefix='/dashboard')


# PRIVREMENO - Debug endpoint za proveru baze
@bp.route('/debug-tenants', methods=['GET'])
def debug_tenants():
    """Debug: Lista svih tenanta u bazi (PRIVREMENO - ukloniti posle testiranja!)"""
    from app.models import Tenant
    tenants = Tenant.query.all()
    return jsonify({
        'total': len(tenants),
        'tenants': [{
            'id': t.id,
            'name': t.name,
            'email': t.email,
            'status': t.status.value if t.status else None,
            'created_at': t.created_at.isoformat() if t.created_at else None
        } for t in tenants]
    }), 200


# PRIVREMENO - Debug endpoint za proveru korisnika
@bp.route('/debug-users', methods=['GET'])
def debug_users():
    """Debug: Lista svih korisnika u bazi (PRIVREMENO - ukloniti posle testiranja!)"""
    from app.models import User
    users = User.query.all()
    return jsonify({
        'total': len(users),
        'users': [{
            'id': u.id,
            'tenant_id': u.tenant_id,
            'email': u.email,
            'ime': u.ime,
            'prezime': u.prezime,
            'role': u.role.value if u.role else None,
            'is_active': u.is_active,
            'created_at': u.created_at.isoformat() if u.created_at else None
        } for u in users]
    }), 200


# PRIVREMENO - Debug endpoint za proveru admina
@bp.route('/debug-admins', methods=['GET'])
def debug_admins():
    """Debug: Lista svih platform admina u bazi (PRIVREMENO - ukloniti posle testiranja!)"""
    from app.models.admin import PlatformAdmin
    admins = PlatformAdmin.query.all()
    return jsonify({
        'total': len(admins),
        'admins': [{
            'id': a.id,
            'email': a.email,
            'ime': a.ime,
            'prezime': a.prezime,
            'role': a.role.value if a.role else None,
            'is_active': a.is_active,
            'created_at': a.created_at.isoformat() if a.created_at else None
        } for a in admins]
    }), 200


@bp.route('', methods=['GET'])
@platform_admin_required
def get_dashboard():
    """
    Glavni dashboard endpoint za admin panel.
    Vraća podatke u formatu koji očekuje dashboard.html template.
    """
    now = datetime.utcnow()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Statistike
    total_tenants = Tenant.query.count()
    active_tenants = Tenant.query.filter(
        Tenant.status.in_([TenantStatus.ACTIVE, TenantStatus.TRIAL])
    ).count()

    # Pending KYC
    pending_kyc_count = ServiceRepresentative.query.filter(
        ServiceRepresentative.status == RepresentativeStatus.PENDING
    ).count()

    # Mesečni prihod
    monthly_revenue = db.session.query(
        func.coalesce(func.sum(SubscriptionPayment.total_amount), 0)
    ).filter(
        SubscriptionPayment.status == 'PAID',
        SubscriptionPayment.created_at >= start_of_month
    ).scalar() or 0

    # Poslednji tenanti
    recent_tenants = Tenant.query.order_by(
        Tenant.created_at.desc()
    ).limit(5).all()

    # Pending KYC lista
    pending_kyc_list = ServiceRepresentative.query.filter(
        ServiceRepresentative.status == RepresentativeStatus.PENDING
    ).order_by(
        ServiceRepresentative.created_at.desc()
    ).limit(5).all()

    # Uzmi tenant name za svaki KYC
    kyc_with_tenant = []
    for rep in pending_kyc_list:
        tenant = Tenant.query.get(rep.tenant_id)
        kyc_with_tenant.append({
            'id': rep.id,
            'ime': rep.ime,
            'prezime': rep.prezime,
            'tenant_name': tenant.name if tenant else 'Nepoznato',
            'created_at': rep.created_at.isoformat() if rep.created_at else None
        })

    return jsonify({
        'stats': {
            'total_tenants': total_tenants,
            'active_tenants': active_tenants,
            'pending_kyc': pending_kyc_count,
            'monthly_revenue': float(monthly_revenue)
        },
        'recent_tenants': [{
            'id': t.id,
            'name': t.name,
            'email': t.email,
            'status': t.status.value if t.status else None,
            'created_at': t.created_at.isoformat() if t.created_at else None
        } for t in recent_tenants],
        'pending_kyc': kyc_with_tenant
    }), 200


@bp.route('/stats', methods=['GET'])
@platform_admin_required
def get_dashboard_stats():
    """
    Glavne statistike platforme za admin dashboard.

    Vraca:
        - Broj tenanata po statusu
        - Prihodi (mesecni, godisnji)
        - Aktivnost (tiketi, narudzbine)
        - KYC statistike
    """
    now = datetime.utcnow()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start_of_year = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    last_30_days = now - timedelta(days=30)

    # =========================================================================
    # TENANTI
    # =========================================================================
    total_tenants = Tenant.query.count()
    active_tenants = Tenant.query.filter(Tenant.status == TenantStatus.ACTIVE).count()
    trial_tenants = Tenant.query.filter(Tenant.status == TenantStatus.TRIAL).count()
    suspended_tenants = Tenant.query.filter(Tenant.status == TenantStatus.SUSPENDED).count()

    # Novi tenanti ovog meseca
    new_tenants_this_month = Tenant.query.filter(
        Tenant.created_at >= start_of_month
    ).count()

    # Trial-i koji isticu u narednih 7 dana
    trials_expiring_soon = Tenant.query.filter(
        and_(
            Tenant.status == TenantStatus.TRIAL,
            Tenant.trial_ends_at <= now + timedelta(days=7),
            Tenant.trial_ends_at > now
        )
    ).count()

    # =========================================================================
    # PRIHODI
    # =========================================================================
    # Mesecni prihod od pretplata
    monthly_revenue = db.session.query(
        func.coalesce(func.sum(SubscriptionPayment.total_amount), 0)
    ).filter(
        SubscriptionPayment.status == 'PAID',
        SubscriptionPayment.created_at >= start_of_month
    ).scalar() or 0

    # Godisnji prihod
    yearly_revenue = db.session.query(
        func.coalesce(func.sum(SubscriptionPayment.total_amount), 0)
    ).filter(
        SubscriptionPayment.status == 'PAID',
        SubscriptionPayment.created_at >= start_of_year
    ).scalar() or 0

    # Prihod od komisija (supplier orders)
    monthly_commission = db.session.query(
        func.coalesce(func.sum(PartOrder.platform_fee), 0)
    ).filter(
        PartOrder.status == OrderStatus.COMPLETED,
        PartOrder.created_at >= start_of_month
    ).scalar() or 0

    # =========================================================================
    # AKTIVNOST
    # =========================================================================
    # Ukupno tiketa
    total_tickets = ServiceTicket.query.count()

    # Tiketi ovog meseca
    tickets_this_month = ServiceTicket.query.filter(
        ServiceTicket.created_at >= start_of_month
    ).count()

    # Aktivni korisnici (ulogovani u poslednjih 30 dana)
    active_users = User.query.filter(
        User.last_login_at >= last_30_days
    ).count()

    # Ukupno korisnika
    total_users = User.query.count()

    # =========================================================================
    # MARKETPLACE
    # =========================================================================
    # Dobavljaci
    total_suppliers = Supplier.query.count()
    active_suppliers = Supplier.query.filter(
        Supplier.status == SupplierStatus.ACTIVE
    ).count()

    # Narudzbine ovog meseca
    orders_this_month = PartOrder.query.filter(
        PartOrder.created_at >= start_of_month
    ).count()

    # Vrednost narudzbina ovog meseca
    orders_value_this_month = db.session.query(
        func.coalesce(func.sum(PartOrder.total_amount), 0)
    ).filter(
        PartOrder.created_at >= start_of_month,
        PartOrder.status.in_([
            OrderStatus.CONFIRMED,
            OrderStatus.SHIPPED,
            OrderStatus.DELIVERED,
            OrderStatus.COMPLETED
        ])
    ).scalar() or 0

    # =========================================================================
    # KYC
    # =========================================================================
    pending_kyc = ServiceRepresentative.query.filter(
        ServiceRepresentative.status == RepresentativeStatus.PENDING
    ).count()

    verified_kyc = ServiceRepresentative.query.filter(
        ServiceRepresentative.status == RepresentativeStatus.VERIFIED
    ).count()

    # =========================================================================
    # INVENTAR (agregirano preko svih tenanata)
    # =========================================================================
    total_phones = PhoneListing.query.filter(
        PhoneListing.is_sold == False
    ).count()

    total_parts = db.session.query(
        func.coalesce(func.sum(SparePart.quantity), 0)
    ).scalar() or 0

    return jsonify({
        'tenants': {
            'total': total_tenants,
            'active': active_tenants,
            'trial': trial_tenants,
            'suspended': suspended_tenants,
            'new_this_month': new_tenants_this_month,
            'trials_expiring_soon': trials_expiring_soon
        },
        'revenue': {
            'monthly_subscriptions': float(monthly_revenue),
            'yearly_subscriptions': float(yearly_revenue),
            'monthly_commission': float(monthly_commission),
            'monthly_total': float(monthly_revenue) + float(monthly_commission),
            'currency': 'RSD'
        },
        'activity': {
            'total_tickets': total_tickets,
            'tickets_this_month': tickets_this_month,
            'total_users': total_users,
            'active_users_30d': active_users
        },
        'marketplace': {
            'total_suppliers': total_suppliers,
            'active_suppliers': active_suppliers,
            'orders_this_month': orders_this_month,
            'orders_value_this_month': float(orders_value_this_month)
        },
        'kyc': {
            'pending': pending_kyc,
            'verified': verified_kyc
        },
        'inventory': {
            'total_phones_for_sale': total_phones,
            'total_spare_parts': int(total_parts)
        },
        'generated_at': now.isoformat()
    }), 200


@bp.route('/charts/revenue', methods=['GET'])
@platform_admin_required
def get_revenue_chart():
    """
    Podaci za grafikon prihoda po mesecima (poslednjih 12 meseci).
    """
    now = datetime.utcnow()
    months_data = []

    for i in range(11, -1, -1):
        # Racunaj pocetak i kraj meseca
        month_date = now - timedelta(days=i * 30)
        month_start = month_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        if month_date.month == 12:
            month_end = month_start.replace(year=month_date.year + 1, month=1)
        else:
            month_end = month_start.replace(month=month_date.month + 1)

        # Prihod od pretplata
        subscriptions = db.session.query(
            func.coalesce(func.sum(SubscriptionPayment.total_amount), 0)
        ).filter(
            SubscriptionPayment.status == 'PAID',
            SubscriptionPayment.created_at >= month_start,
            SubscriptionPayment.created_at < month_end
        ).scalar() or 0

        # Prihod od komisija
        commissions = db.session.query(
            func.coalesce(func.sum(PartOrder.platform_fee), 0)
        ).filter(
            PartOrder.status == OrderStatus.COMPLETED,
            PartOrder.created_at >= month_start,
            PartOrder.created_at < month_end
        ).scalar() or 0

        months_data.append({
            'month': month_start.strftime('%Y-%m'),
            'subscriptions': float(subscriptions),
            'commissions': float(commissions),
            'total': float(subscriptions) + float(commissions)
        })

    return jsonify({
        'data': months_data,
        'currency': 'RSD'
    }), 200


@bp.route('/charts/tenants', methods=['GET'])
@platform_admin_required
def get_tenants_chart():
    """
    Podaci za grafikon rasta tenanata po mesecima (poslednjih 12 meseci).
    """
    now = datetime.utcnow()
    months_data = []

    for i in range(11, -1, -1):
        month_date = now - timedelta(days=i * 30)
        month_start = month_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        if month_date.month == 12:
            month_end = month_start.replace(year=month_date.year + 1, month=1)
        else:
            month_end = month_start.replace(month=month_date.month + 1)

        # Novi tenanti u tom mesecu
        new_tenants = Tenant.query.filter(
            Tenant.created_at >= month_start,
            Tenant.created_at < month_end
        ).count()

        # Ukupno tenanata do kraja tog meseca
        total_tenants = Tenant.query.filter(
            Tenant.created_at < month_end
        ).count()

        months_data.append({
            'month': month_start.strftime('%Y-%m'),
            'new': new_tenants,
            'total': total_tenants
        })

    return jsonify({
        'data': months_data
    }), 200


@bp.route('/recent-activity', methods=['GET'])
@platform_admin_required
def get_recent_activity():
    """
    Poslednje aktivnosti na platformi za prikaz u dashboardu.
    """
    # Poslednje registracije
    recent_tenants = Tenant.query.order_by(
        Tenant.created_at.desc()
    ).limit(5).all()

    # Poslednje uplate
    recent_payments = SubscriptionPayment.query.filter(
        SubscriptionPayment.status == 'PAID'
    ).order_by(
        SubscriptionPayment.created_at.desc()
    ).limit(5).all()

    # Poslednji KYC zahtevi
    recent_kyc = ServiceRepresentative.query.filter(
        ServiceRepresentative.status == RepresentativeStatus.PENDING
    ).order_by(
        ServiceRepresentative.created_at.desc()
    ).limit(5).all()

    return jsonify({
        'recent_registrations': [{
            'id': t.id,
            'name': t.name,
            'email': t.email,
            'created_at': t.created_at.isoformat()
        } for t in recent_tenants],
        'recent_payments': [{
            'id': p.id,
            'tenant_id': p.tenant_id,
            'amount': float(p.total_amount),
            'created_at': p.created_at.isoformat()
        } for p in recent_payments],
        'pending_kyc': [{
            'id': r.id,
            'full_name': r.full_name,
            'tenant_id': r.tenant_id,
            'created_at': r.created_at.isoformat()
        } for r in recent_kyc]
    }), 200
