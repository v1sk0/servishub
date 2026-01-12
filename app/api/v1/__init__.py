"""
V1 API Blueprint - B2B endpoints za servise (tenante).

Svi endpointi u ovom blueprintu zahtevaju JWT autentifikaciju
i pripadaju odredjenom tenantu.
"""

from flask import Blueprint

# Glavni blueprint za v1 API
bp = Blueprint('api_v1', __name__)


def register_routes():
    """
    Registruje sve sub-blueprinte za v1 API.
    Poziva se iz app factory-ja.
    """
    from . import auth, tickets, inventory

    bp.register_blueprint(auth.bp)
    bp.register_blueprint(tickets.bp)
    bp.register_blueprint(inventory.bp)

    # TODO: Registrovati ostale blueprinte kako se budu implementirali
    # from . import marketplace, partners, representatives, orders
