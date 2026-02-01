"""
Tenant Frontend Routes - Stranice za servisne radnje.

Sve stranice zahtevaju autentifikaciju putem JWT tokena
koji se proverava na frontendu (JavaScript).
"""

from flask import render_template, abort, current_app
from . import bp
from ..models import Tenant


# ============== Auth Pages ==============

@bp.route('/login/<secret>')
def employee_login(secret):
    """
    Privatna login stranica za zaposlene tenanta.

    Ova stranica je dostupna samo preko tajnog URL-a koji owner
    deli sa svojim zaposlenima. Svaki tenant ima jedinstven secret.
    """
    tenant = Tenant.query.filter_by(login_secret=secret).first()

    if not tenant:
        abort(404)  # Ne odaj da stranica postoji

    if not tenant.is_active:
        abort(403)

    return render_template('tenant/employee_login.html', tenant=tenant)


@bp.route('/login')
def login():
    """Stranica za prijavu."""
    return render_template('tenant/login.html')


@bp.route('/register')
def register():
    """Stranica za registraciju novog servisa."""
    return render_template(
        'tenant/register.html',
        google_maps_api_key=current_app.config.get('GOOGLE_MAPS_API_KEY', '')
    )


@bp.route('/verify-email')
def verify_email():
    """
    Stranica za verifikaciju email adrese.
    Korisnik dolazi ovde klikom na link iz emaila.
    Token se cita iz URL query parametra i salje na API.
    """
    return render_template('tenant/verify_email.html')


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


@bp.route('/tickets/<int:ticket_id>/print')
def tickets_print(ticket_id):
    """Stampanje servisnog naloga (A4, 2 kopije)."""
    return render_template('tenant/tickets/print.html', ticket_id=ticket_id)


@bp.route('/tickets/warranties')
def tickets_warranties():
    """Lista garancija."""
    return render_template('tenant/tickets/warranties.html')


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

# ============== POS / Kasa ==============

@bp.route('/pos')
def pos_register():
    """POS kasa - otvaranje/zatvaranje, kreiranje racuna."""
    return render_template('tenant/pos/register.html')


@bp.route('/pos/receipts')
def pos_receipts():
    """Lista svih racuna."""
    return render_template('tenant/pos/receipts.html')


@bp.route('/pos/daily-report')
def pos_daily_report():
    """Dnevni izvestaj POS prometa."""
    return render_template('tenant/pos/daily_report.html')


# ============== Magacin / Goods ==============

@bp.route('/goods')
def goods_list():
    """Lista robe na stanju."""
    return render_template('tenant/goods/list.html')


@bp.route('/goods/invoices')
def goods_invoices():
    """Lista ulaznih faktura."""
    return render_template('tenant/goods/invoice_list.html')


@bp.route('/goods/invoices/new')
def goods_invoice_new():
    """Unos nove ulazne fakture."""
    return render_template('tenant/goods/invoice.html')


# ============== Finance / Finansije ==============

@bp.route('/finance')
def finance_index():
    """Pregled finansija - svi tipovi prometa."""
    return render_template('tenant/finance/index.html')


@bp.route('/finance/tickets')
def finance_tickets():
    """Promet od servisnih naloga."""
    return render_template('tenant/finance/tickets.html')


@bp.route('/finance/phones')
def finance_phones():
    """Promet od prodaje telefona."""
    return render_template('tenant/finance/phones.html')


@bp.route('/finance/goods')
def finance_goods():
    """Promet od prodaje opreme."""
    return render_template('tenant/finance/goods.html')


@bp.route('/finance/pos')
def finance_pos():
    """Dnevni prometi po kasi."""
    return render_template('tenant/finance/pos.html')


@bp.route('/finance/sms')
def finance_sms():
    """SMS evidencija - pregled poslatih SMS poruka i troškova."""
    return render_template('tenant/finance/sms.html')


# ============== Credits / Krediti ==============

@bp.route('/credits')
def credits_balance():
    """Stanje kredita i istorija transakcija."""
    return render_template('tenant/credits/balance.html')


@bp.route('/credits/purchase')
def credits_purchase():
    """Kupovina paketa kredita."""
    return render_template('tenant/credits/purchase.html')


# ============== Settings ==============

@bp.route('/settings')
def settings():
    """Podesavanja servisa."""
    return render_template('tenant/settings/index.html',
                           google_maps_api_key=current_app.config.get('GOOGLE_MAPS_API_KEY', ''))


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


# ============== Pricing / Cenovnik ==============

@bp.route('/pricing')
def pricing():
    """Cenovnik usluga."""
    return render_template('tenant/pricing/index.html')


# ============== Messages / Poruke ==============

@bp.route('/messages')
def messages_inbox():
    """Inbox poruka - sistemske notifikacije i razgovori."""
    return render_template('tenant/messages/inbox.html')


# ============== Network / Mreža partnera ==============

@bp.route('/network')
def network():
    """Mreža partnera - T2T networking."""
    return render_template('tenant/network/index.html')
