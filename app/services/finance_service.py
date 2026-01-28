"""
Finance Service - izveštaji o prometu i profitu.

Servisni nalozi, prodaja telefona, prodaja robe, dnevni prometi po kasi.
"""

from datetime import date, datetime, timedelta
from ..extensions import db
from ..models.ticket import ServiceTicket, TicketStatus
from ..models.inventory import PhoneListing
from ..models.pos import Receipt, ReceiptItem, DailyReport, ReceiptStatus, SaleItemType


class FinanceService:
    """Static metode za finansijske izveštaje."""

    @staticmethod
    def get_ticket_revenue(tenant_id: int, start_date: date, end_date: date):
        """Naplaćeni servisni nalozi u periodu."""
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        tickets = ServiceTicket.query.filter(
            ServiceTicket.tenant_id == tenant_id,
            ServiceTicket.status == TicketStatus.DELIVERED,
            ServiceTicket.is_paid == True,
            ServiceTicket.paid_at >= start_dt,
            ServiceTicket.paid_at <= end_dt
        ).all()

        total = sum(float(t.final_price or 0) for t in tickets)
        return {
            'total': total,
            'count': len(tickets),
            'items': [{
                'id': t.id,
                'ticket_number': t.ticket_number,
                'customer': t.customer_name,
                'device': f"{t.brand} {t.model}" if t.brand else '',
                'price': float(t.final_price or 0),
                'date': t.paid_at.strftime('%Y-%m-%d') if t.paid_at else ''
            } for t in tickets]
        }

    @staticmethod
    def get_phone_sales(tenant_id: int, start_date: date, end_date: date):
        """Prodati telefoni u periodu."""
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        phones = PhoneListing.query.filter(
            PhoneListing.tenant_id == tenant_id,
            PhoneListing.sold == True,
            PhoneListing.sold_at >= start_dt,
            PhoneListing.sold_at <= end_dt
        ).all()

        total = sum(float(p.sales_price or 0) for p in phones)
        cost = sum(float(p.purchase_price or 0) for p in phones)
        return {
            'total': total,
            'profit': total - cost,
            'count': len(phones),
            'items': [{
                'id': p.id,
                'model': f"{p.brand} {p.model}",
                'price': float(p.sales_price or 0),
                'cost': float(p.purchase_price or 0),
                'profit': float((p.sales_price or 0) - (p.purchase_price or 0)),
                'date': p.sold_at.strftime('%Y-%m-%d') if p.sold_at else ''
            } for p in phones]
        }

    @staticmethod
    def get_goods_sales(tenant_id: int, start_date: date, end_date: date):
        """Prodaja robe kroz POS u periodu."""
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        items = db.session.query(ReceiptItem).join(Receipt).filter(
            Receipt.tenant_id == tenant_id,
            Receipt.status == ReceiptStatus.ISSUED,
            ReceiptItem.item_type == SaleItemType.GOODS,
            Receipt.issued_at >= start_dt,
            Receipt.issued_at <= end_dt
        ).all()

        total = sum(float(i.line_total or 0) for i in items)
        cost = sum(float(i.line_cost or 0) for i in items)
        return {
            'total': total,
            'profit': total - cost,
            'count': len(items)
        }

    @staticmethod
    def get_pos_daily(tenant_id: int, start_date: date, end_date: date):
        """Dnevni Z-izveštaji u periodu."""
        reports = DailyReport.query.filter(
            DailyReport.tenant_id == tenant_id,
            DailyReport.date >= start_date,
            DailyReport.date <= end_date
        ).order_by(DailyReport.date.desc()).all()

        return {
            'total_cash': sum(float(r.total_cash or 0) for r in reports),
            'total_card': sum(float(r.total_card or 0) for r in reports),
            'total': sum(float(r.total_revenue or 0) for r in reports),
            'days': [{
                'date': r.date.strftime('%Y-%m-%d'),
                'location': r.location.name if r.location else 'N/A',
                'location_id': r.location_id,
                'cash': float(r.total_cash or 0),
                'card': float(r.total_card or 0),
                'total': float(r.total_revenue or 0),
                'receipt_count': r.receipt_count or 0
            } for r in reports]
        }

    @staticmethod
    def get_summary(tenant_id: int, days: int = 30):
        """Sumarni pregled svih tipova prometa."""
        end = date.today()
        start = end - timedelta(days=days)

        return {
            'period': {
                'start': start.isoformat(),
                'end': end.isoformat(),
                'days': days
            },
            'tickets': FinanceService.get_ticket_revenue(tenant_id, start, end),
            'phones': FinanceService.get_phone_sales(tenant_id, start, end),
            'goods': FinanceService.get_goods_sales(tenant_id, start, end),
            'pos': FinanceService.get_pos_daily(tenant_id, start, end)
        }
