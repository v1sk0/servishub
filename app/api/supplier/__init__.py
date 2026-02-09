"""
Supplier API Blueprint - Endpoints for suppliers.

Suppliers have their own authentication and can manage:
- Their profile
- Product listings
- Incoming orders
"""

from flask import Blueprint

bp = Blueprint('api_supplier', __name__)


def register_routes():
    """Register all supplier API routes"""
    from . import auth, listings, orders, dashboard, reports, credits

    bp.register_blueprint(auth.bp)
    bp.register_blueprint(listings.bp)
    bp.register_blueprint(orders.bp)
    bp.register_blueprint(dashboard.bp)
    bp.register_blueprint(reports.bp)
    bp.register_blueprint(credits.bp)
