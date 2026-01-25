"""
Admin Frontend Routes - Stranice za platform admine.

Platform admini upravljaju svim servisima u sistemu.
"""

from flask import render_template
from . import bp


# ============== Auth ==============

@bp.route('/admin/login')
def admin_login():
    """Admin login stranica."""
    return render_template('admin/login.html')


# ============== Dashboard ==============

@bp.route('/admin')
@bp.route('/admin/dashboard')
def admin_dashboard():
    """Admin dashboard sa globalnom statistikom."""
    return render_template('admin/dashboard.html')


# ============== Tenants ==============

@bp.route('/admin/tenants')
def admin_tenants_list():
    """Lista svih servisa."""
    return render_template('admin/tenants/list.html')


@bp.route('/admin/tenants/<int:tenant_id>')
def admin_tenants_detail(tenant_id):
    """Detalji servisa."""
    return render_template('admin/tenants/detail.html', tenant_id=tenant_id)


# ============== KYC ==============

@bp.route('/admin/kyc')
def admin_kyc_list():
    """KYC zahtevi na cekanju."""
    return render_template('admin/kyc/list.html')


@bp.route('/admin/kyc/<int:representative_id>')
def admin_kyc_detail(representative_id):
    """Detalji KYC zahteva."""
    return render_template('admin/kyc/detail.html', representative_id=representative_id)


# ============== Suppliers ==============

@bp.route('/admin/suppliers')
def admin_suppliers_list():
    """Lista dobavljaca."""
    return render_template('admin/suppliers/list.html')


@bp.route('/admin/suppliers/<int:supplier_id>')
def admin_suppliers_detail(supplier_id):
    """Detalji dobavljaca."""
    return render_template('admin/suppliers/detail.html', supplier_id=supplier_id)


# ============== Payments ==============

@bp.route('/admin/payments')
def admin_payments_list():
    """Lista uplata."""
    return render_template('admin/payments/list.html')


# ============== Billing ==============

@bp.route('/admin/billing/bank-import')
def admin_bank_import():
    """Uvoz bankovnih izvoda."""
    return render_template('admin/billing/bank_import.html')


@bp.route('/admin/billing/transactions')
def admin_transactions():
    """Bankovne transakcije - matching UI."""
    return render_template('admin/billing/transactions.html')


@bp.route('/admin/billing/import/<int:import_id>')
def admin_import_detail(import_id):
    """Detalji importa."""
    return render_template('admin/billing/import_detail.html', import_id=import_id)


# ============== Activity Log ==============

@bp.route('/admin/activity')
def admin_activity_list():
    """Log aktivnosti admina."""
    return render_template('admin/activity/list.html')


# ============== Security Events ==============

@bp.route('/admin/security')
def admin_security_events():
    """Security events - login pokusaji, rate limits, itd."""
    return render_template('admin/security/events.html')


# ============== Support ==============

@bp.route('/admin/support')
def admin_support():
    """Admin support - podrska korisnicima."""
    return render_template('admin/support/list.html')


# ============== Packages ==============

@bp.route('/admin/paketi')
def admin_packages():
    """Paketi usluga i cenovnik."""
    return render_template('admin/packages/index.html')


# ============== Settings ==============

@bp.route('/admin/settings')
def admin_settings():
    """Platform podesavanja."""
    return render_template('admin/settings/index.html')
