"""
Public Frontend Routes - Javne stranice.

Ove stranice ne zahtevaju autentifikaciju.
"""

from flask import render_template
from . import bp


# ============== Landing ==============

@bp.route('/')
def landing():
    """Landing stranica."""
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
