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
