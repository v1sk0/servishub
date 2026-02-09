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
    from . import auth, tenants, kyc, dashboard, activity, security, settings, payments, scheduler, threads
    from . import bank_import, bank_transactions, notifications, sms
    from . import suppliers, credits

    bp.register_blueprint(auth.bp)
    bp.register_blueprint(tenants.bp)
    bp.register_blueprint(kyc.bp)
    bp.register_blueprint(dashboard.bp)
    bp.register_blueprint(activity.bp)
    bp.register_blueprint(security.bp)
    bp.register_blueprint(settings.bp)
    bp.register_blueprint(payments.bp)
    bp.register_blueprint(threads.bp)
    bp.register_blueprint(bank_import.bp)
    bp.register_blueprint(bank_transactions.bp)
    bp.register_blueprint(notifications.bp)
    bp.register_blueprint(sms.bp)
    bp.register_blueprint(suppliers.bp)
    bp.register_blueprint(credits.bp)
    # scheduler rute su direktno na bp, nije sub-blueprint
