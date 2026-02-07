"""
Frontend Blueprint - Serviranje HTML stranica.

Ovaj modul sadrzi rute za serviranje Jinja2 sablona.
Razdvojen je od API blueprinta koji vracaju JSON.
"""

from flask import Blueprint

bp = Blueprint('frontend', __name__)


def register_routes():
    """Registruje sve frontend rute."""
    import sys
    print("[DEBUG] Frontend register_routes called", file=sys.stderr)
    try:
        from . import tenant
        print("[DEBUG] tenant imported OK", file=sys.stderr)
    except Exception as e:
        print(f"[DEBUG] tenant import FAILED: {e}", file=sys.stderr)
    try:
        from . import admin
        print("[DEBUG] admin imported OK", file=sys.stderr)
    except Exception as e:
        print(f"[DEBUG] admin import FAILED: {e}", file=sys.stderr)
    try:
        from . import public
        print("[DEBUG] public imported OK", file=sys.stderr)
    except Exception as e:
        print(f"[DEBUG] public import FAILED: {e}", file=sys.stderr)
    try:
        from . import supplier
        print("[DEBUG] supplier imported OK", file=sys.stderr)
    except Exception as e:
        print(f"[DEBUG] supplier import FAILED: {e}", file=sys.stderr)
    print(f"[DEBUG] Frontend bp.url_map has {len(bp.deferred_functions)} deferred functions", file=sys.stderr)
