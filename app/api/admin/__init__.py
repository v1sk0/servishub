"""
Admin API Blueprint - Platform Admin endpoints.

Svi endpointi u ovom blueprintu zahtevaju admin JWT
i daju pristup celom ekosistemu.
"""

from flask import Blueprint

# Glavni blueprint za admin API
bp = Blueprint('api_admin', __name__)


def register_routes():
    """
    Registruje sve sub-blueprinte za admin API.
    Poziva se iz app factory-ja.
    """
    from . import auth, tenants, kyc, dashboard

    bp.register_blueprint(auth.bp)
    bp.register_blueprint(tenants.bp)
    bp.register_blueprint(kyc.bp)
    bp.register_blueprint(dashboard.bp)

    # TODO: Dodati suppliers management, orders management, support tickets
