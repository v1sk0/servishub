"""
Supplier Frontend Routes - Stranice za dobavljace.

Dobavljaci upravljaju svojim katalogom delova i narudzbinama.
"""

from flask import render_template
from . import bp


# ============== Auth ==============

@bp.route('/supplier/login')
def supplier_login():
    """Supplier login stranica."""
    return render_template('supplier/login.html')


@bp.route('/supplier/register')
def supplier_register():
    """Supplier registracija."""
    return render_template('supplier/register.html')


# ============== Dashboard ==============

@bp.route('/supplier')
@bp.route('/supplier/dashboard')
def supplier_dashboard():
    """Supplier dashboard sa statistikom."""
    return render_template('supplier/dashboard.html')


# ============== Catalog ==============

@bp.route('/supplier/catalog')
def supplier_catalog():
    """Lista artikala u katalogu."""
    return render_template('supplier/catalog/list.html')


@bp.route('/supplier/catalog/new')
def supplier_catalog_new():
    """Dodavanje novog artikla."""
    return render_template('supplier/catalog/new.html')


@bp.route('/supplier/catalog/<int:listing_id>')
def supplier_catalog_detail(listing_id):
    """Detalji artikla."""
    return render_template('supplier/catalog/detail.html', listing_id=listing_id)


# ============== Orders ==============

@bp.route('/supplier/orders')
def supplier_orders():
    """Lista narudzbina."""
    return render_template('supplier/orders/list.html')


@bp.route('/supplier/orders/<int:order_id>')
def supplier_order_detail(order_id):
    """Detalji narudzbine."""
    return render_template('supplier/orders/detail.html', order_id=order_id)


# ============== Reports ==============

@bp.route('/supplier/reports')
def supplier_reports():
    """Izvestaji dobavljaca."""
    return render_template('supplier/reports.html')


# ============== Delivery ==============

@bp.route('/supplier/delivery')
def supplier_delivery():
    """Konfiguracija dostave dobavljaca."""
    return render_template('supplier/delivery.html')


# ============== Settings ==============

@bp.route('/supplier/settings')
def supplier_settings():
    """Podesavanja dobavljaca."""
    return render_template('supplier/settings.html')
