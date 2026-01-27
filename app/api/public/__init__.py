"""
Public API Blueprint - B2C endpoints za krajnje kupce.

Ovaj API ne zahteva autentifikaciju i omogucava:
- Pracenje statusa servisnog naloga putem tokena (QR kod)
- Pregled javnih delova iz marketplace-a
- Kontakt forme

NAPOMENA: Svi endpointi su rate-limited i ne vracaju osetljive podatke.
"""

from flask import Blueprint

bp = Blueprint('api_public', __name__)


def register_routes():
    """Registruje sve public API rute."""
    from . import tickets, marketplace

    bp.register_blueprint(tickets.bp)
    bp.register_blueprint(marketplace.bp)

    # B2C Public User API (task-010)
    from ..public_user import auth as pu_auth
    from ..public_user import requests as pu_requests
    from ..public_user import marketplace as pu_marketplace
    from ..public_user import credits as pu_credits

    bp.register_blueprint(pu_auth.bp)
    bp.register_blueprint(pu_requests.bp)
    bp.register_blueprint(pu_marketplace.bp)
    bp.register_blueprint(pu_credits.bp)
