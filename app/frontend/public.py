"""
Public Frontend Routes - Javne stranice.

Ove stranice ne zahtevaju autentifikaciju.
"""

from flask import render_template, g
from . import bp


# ============== Landing ==============

@bp.route('/')
def landing():
    """
    Landing stranica ili javna stranica tenanta.

    Ako je zahtev za javnu stranicu tenanta (subdomen ili custom domen),
    prikazuje se tenant public home page. Inače, prikazuje se glavni landing.
    """
    # Proveri da li je ovo zahtev za javnu stranicu tenanta
    if g.get('is_public_site') and g.get('public_tenant') and g.get('public_profile'):
        from app.models import ServiceItem

        tenant = g.public_tenant
        profile = g.public_profile

        # Proveri da li je profil javno dostupan
        if not profile.is_public:
            return render_template('public/landing.html')

        # Dohvati aktivne usluge
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
            'tenant_public/home.html',
            tenant=tenant,
            profile=profile,
            services=services,
            services_by_category=services_by_category
        )

    # Inače prikaži glavni ServisHub landing
    return render_template('public/landing.html')


# ============== Ticket Tracking ==============

@bp.route('/track/<string:token>')
def track_ticket(token):
    """Pracenje statusa servisnog naloga putem QR koda."""
    return render_template('public/track.html', token=token)


# ============== Public Marketplace ==============

@bp.route('/parts')
def public_parts():
    """Javna pretraga delova."""
    return render_template('public/marketplace.html')


# ============== Legal Pages ==============

@bp.route('/privacy')
def privacy_policy():
    """Politika privatnosti."""
    return render_template('public/privacy.html')


@bp.route('/terms')
def terms_of_service():
    """Uslovi koriscenja."""
    return render_template('public/terms.html')
