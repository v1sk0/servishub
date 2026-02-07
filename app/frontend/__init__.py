"""
Frontend Blueprint - Serviranje HTML stranica.

Ovaj modul sadrzi rute za serviranje Jinja2 sablona.
Razdvojen je od API blueprinta koji vracaju JSON.
"""

from flask import Blueprint

bp = Blueprint('frontend', __name__)


def register_routes():
    """Registruje sve frontend rute."""
    from . import tenant, admin, public, supplier
