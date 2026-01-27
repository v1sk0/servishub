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
    from . import auth, tickets, inventory, tenant, locations, users, marketplace, orders, messages, services, public, threads, connections, credits, service_requests, pos, goods

    bp.register_blueprint(auth.bp)
    bp.register_blueprint(tickets.bp)
    bp.register_blueprint(inventory.bp)
    bp.register_blueprint(tenant.bp)
    bp.register_blueprint(locations.bp)
    bp.register_blueprint(users.bp)
    bp.register_blueprint(marketplace.bp)
    bp.register_blueprint(orders.bp)
    bp.register_blueprint(messages.bp)
    bp.register_blueprint(services.bp)
    bp.register_blueprint(public.bp)
    bp.register_blueprint(threads.bp)
    bp.register_blueprint(connections.bp)
    bp.register_blueprint(credits.bp)
    bp.register_blueprint(service_requests.bp)
    bp.register_blueprint(pos.bp)
    bp.register_blueprint(goods.bp)
