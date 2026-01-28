"""
Finance API - izveštaji o prometu.

Endpointi za pregled prometa po tipovima: servisni nalozi, telefoni, roba, kasa.
"""

from datetime import date, timedelta
from flask import Blueprint, request, g
from app.api.middleware.auth import jwt_required
from app.services.finance_service import FinanceService

bp = Blueprint('finance', __name__, url_prefix='/finance')


@bp.route('/summary', methods=['GET'])
@jwt_required
def get_summary():
    """Sumarni pregled svih tipova prometa."""
    days = request.args.get('days', 30, type=int)
    return FinanceService.get_summary(g.tenant_id, days)


@bp.route('/tickets', methods=['GET'])
@jwt_required
def get_tickets():
    """Promet od servisnih naloga."""
    days = request.args.get('days', 30, type=int)
    end = date.today()
    start = end - timedelta(days=days)
    return FinanceService.get_ticket_revenue(g.tenant_id, start, end)


@bp.route('/phones', methods=['GET'])
@jwt_required
def get_phones():
    """Promet od prodaje telefona."""
    days = request.args.get('days', 30, type=int)
    end = date.today()
    start = end - timedelta(days=days)
    return FinanceService.get_phone_sales(g.tenant_id, start, end)


@bp.route('/goods', methods=['GET'])
@jwt_required
def get_goods():
    """Promet od prodaje robe."""
    days = request.args.get('days', 30, type=int)
    end = date.today()
    start = end - timedelta(days=days)
    return FinanceService.get_goods_sales(g.tenant_id, start, end)


@bp.route('/pos-daily', methods=['GET'])
@jwt_required
def get_pos_daily():
    """Dnevni prometi po kasi."""
    days = request.args.get('days', 30, type=int)
    end = date.today()
    start = end - timedelta(days=days)
    return FinanceService.get_pos_daily(g.tenant_id, start, end)
