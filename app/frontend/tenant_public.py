"""
Tenant Public Site Routes - Javna stranica tenanta.

Ove rute služe za prikaz javne stranice tenanta na:
- {slug}.servishub.rs (subdomena)
- custom_domain (npr. mojservis.rs)

Middleware (public_site.py) postavlja g.public_tenant i g.public_profile
ako je request za javnu stranicu.

Security:
- All routes require is_public flag on profile
- Rate limiting on API endpoints (60 req/min)
- No sensitive data exposed in public responses
"""

from flask import Blueprint, render_template, g, abort, jsonify
from app.models import ServiceItem, TenantGoogleIntegration, TenantGoogleReview
from app.utils.security import rate_limit, get_client_ip


bp = Blueprint('tenant_public', __name__)


def require_public_site(f):
    """Decorator koji zahteva da je request za javnu stranicu."""
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.get('is_public_site') or not g.get('public_tenant'):
            abort(404)
        return f(*args, **kwargs)
    return decorated_function


# ============== Main Pages ==============
#
# NAPOMENA: Ruta '/' je objedinjena u frontend/public.py landing() funkciji
# koja detektuje g.is_public_site i prikazuje odgovarajuci template.
# Ostale rute (/cenovnik, /kontakt, /o-nama) ostaju ovde jer nemaju duplikate.


@bp.route('/cenovnik')
@require_public_site
def cenovnik():
    """Stranica sa cenovnikom."""
    tenant = g.public_tenant
    profile = g.public_profile

    if not profile.show_prices:
        abort(404)

    services = ServiceItem.query.filter_by(
        tenant_id=tenant.id,
        is_active=True
    ).order_by(ServiceItem.category, ServiceItem.display_order).all()

    # Grupiši usluge po kategorijama
    services_by_category = {}
    for service in services:
        cat = service.category or 'Ostalo'
        if cat not in services_by_category:
            services_by_category[cat] = []
        services_by_category[cat].append(service)

    return render_template(
        'tenant_public/cenovnik.html',
        tenant=tenant,
        profile=profile,
        services=services,
        services_by_category=services_by_category
    )


@bp.route('/kontakt')
@require_public_site
def kontakt():
    """Kontakt stranica."""
    tenant = g.public_tenant
    profile = g.public_profile

    return render_template(
        'tenant_public/kontakt.html',
        tenant=tenant,
        profile=profile
    )


@bp.route('/o-nama')
@require_public_site
def o_nama():
    """O nama stranica."""
    tenant = g.public_tenant
    profile = g.public_profile

    return render_template(
        'tenant_public/o_nama.html',
        tenant=tenant,
        profile=profile
    )


# ============== API Endpoints (Public, No Auth) ==============
# Rate limited to prevent abuse

@bp.route('/api/info')
@require_public_site
@rate_limit(limit=60, window=60)  # 60 requests per minute
def api_info():
    """
    JSON podaci o tenantu za javnu stranicu.

    Returns:
        Public profile data including contact, branding, social links.
        Excludes sensitive data like custom domain verification tokens.
    """
    tenant = g.public_tenant
    profile = g.public_profile

    return jsonify(profile.to_public_dict(tenant))


@bp.route('/api/services')
@require_public_site
@rate_limit(limit=60, window=60)  # 60 requests per minute
def api_services():
    """
    JSON lista usluga.

    Returns:
        List of active services with pricing (if show_prices is enabled).
        Includes price disclaimer.
    """
    tenant = g.public_tenant
    profile = g.public_profile

    if not profile.show_prices:
        return jsonify({'services': [], 'message': 'Cenovnik nije javno dostupan'}), 200

    services = ServiceItem.query.filter_by(
        tenant_id=tenant.id,
        is_active=True
    ).order_by(ServiceItem.category, ServiceItem.display_order).all()

    return jsonify({
        'services': [s.to_dict() for s in services],
        'disclaimer': profile.price_disclaimer
    })


@bp.route('/api/reviews')
@require_public_site
@rate_limit(limit=60, window=60)
def api_reviews():
    """
    JSON lista Google recenzija.

    Returns:
        Google rating info and list of visible reviews.
    """
    tenant = g.public_tenant

    integration = TenantGoogleIntegration.query.filter_by(
        tenant_id=tenant.id
    ).first()

    if not integration or not integration.google_place_id:
        return jsonify({
            'has_reviews': False,
            'rating': None,
            'total_reviews': 0,
            'reviews': []
        })

    reviews = TenantGoogleReview.query.filter_by(
        tenant_id=tenant.id,
        is_visible=True
    ).order_by(TenantGoogleReview.review_time.desc()).limit(10).all()

    return jsonify({
        'has_reviews': True,
        'rating': float(integration.google_rating) if integration.google_rating else None,
        'total_reviews': integration.total_reviews or 0,
        'reviews': [r.to_dict() for r in reviews]
    })
