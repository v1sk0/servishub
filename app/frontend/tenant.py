"""
Tenant Frontend Routes - Stranice za servisne radnje.

Sve stranice zahtevaju autentifikaciju putem JWT tokena
koji se proverava na frontendu (JavaScript).
"""

from flask import render_template
from . import bp


# ============== Auth Pages ==============

@bp.route('/login')
def login():
    """Stranica za prijavu."""
    return render_template('tenant/login.html')


@bp.route('/register')
def register():
    """Stranica za registraciju novog servisa."""
    return render_template('tenant/register.html')


# ============== Dashboard ==============

@bp.route('/dashboard')
def dashboard():
    """Glavni dashboard za servis."""
    return render_template('tenant/dashboard.html')


# ============== Tickets ==============

@bp.route('/tickets')
def tickets_list():
    """Lista servisnih naloga."""
    return render_template('tenant/tickets/list.html')


@bp.route('/tickets/new')
def tickets_new():
    """Forma za kreiranje novog naloga."""
    return render_template('tenant/tickets/new.html')


@bp.route('/tickets/<int:ticket_id>')
def tickets_detail(ticket_id):
    """Detalji servisnog naloga."""
    return render_template('tenant/tickets/detail.html', ticket_id=ticket_id)


@bp.route('/tickets/<int:ticket_id>/edit')
def tickets_edit(ticket_id):
    """Izmena servisnog naloga."""
    return render_template('tenant/tickets/edit.html', ticket_id=ticket_id)


# ============== Inventory ==============

@bp.route('/inventory/phones')
def phones_list():
    """Lista telefona na lageru."""
    return render_template('tenant/inventory/phones.html')


@bp.route('/inventory/phones/new')
def phones_new():
    """Forma za dodavanje telefona."""
    return render_template('tenant/inventory/phones_new.html')


@bp.route('/inventory/parts')
def parts_list():
    """Lista rezervnih delova."""
    return render_template('tenant/inventory/parts.html')


@bp.route('/inventory/parts/new')
def parts_new():
    """Forma za dodavanje dela."""
    return render_template('tenant/inventory/parts_new.html')


# ============== Marketplace ==============

@bp.route('/marketplace')
def marketplace():
    """Pretraga delova na marketplace-u."""
    return render_template('tenant/marketplace/search.html')


# ============== Orders ==============

@bp.route('/orders')
def orders_list():
    """Lista narudzbina."""
    return render_template('tenant/orders/list.html')


@bp.route('/orders/<int:order_id>')
def orders_detail(order_id):
    """Detalji narudzbine."""
    return render_template('tenant/orders/detail.html', order_id=order_id)


# ============== Locations ==============

@bp.route('/locations')
def locations_list():
    """Lista lokacija servisa."""
    return render_template('tenant/locations/list.html')


@bp.route('/locations/new')
def locations_new():
    """Forma za dodavanje lokacije."""
    return render_template('tenant/locations/new.html')


@bp.route('/locations/<int:location_id>')
def locations_detail(location_id):
    """Detalji lokacije."""
    return render_template('tenant/locations/detail.html', location_id=location_id)


# ============== Team ==============

@bp.route('/team')
def team_list():
    """Lista clanova tima."""
    return render_template('tenant/team/list.html')


@bp.route('/team/new')
def team_new():
    """Forma za dodavanje clana tima."""
    return render_template('tenant/team/new.html')


@bp.route('/team/<int:user_id>')
def team_detail(user_id):
    """Profil clana tima."""
    return render_template('tenant/team/detail.html', user_id=user_id)


# ============== Settings ==============

@bp.route('/settings')
def settings():
    """Podesavanja servisa."""
    return render_template('tenant/settings/index.html')


@bp.route('/settings/profile')
def settings_profile():
    """Profil servisa."""
    return render_template('tenant/settings/profile.html')


@bp.route('/settings/subscription')
def settings_subscription():
    """Status pretplate."""
    return render_template('tenant/settings/subscription.html')


@bp.route('/settings/kyc')
def settings_kyc():
    """KYC verifikacija."""
    return render_template('tenant/settings/kyc.html')
