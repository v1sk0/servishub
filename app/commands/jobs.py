"""
Background jobs za ServisHub - poziva se via Heroku Scheduler.

Komande:
- flask check-orders: Auto-expire isteklih narudzbina + reminder supplier-ima (svaka 10 min)
"""
import click
from datetime import datetime, timedelta
from flask.cli import with_appcontext


@click.command('check-orders')
@with_appcontext
def check_orders_cmd():
    """
    Pokrece se svakih 10 minuta via Heroku Scheduler.
    1. Expire-uje SENT orders koji su stariji od 2h (expires_at)
    2. Expire-uje OFFERED orders koji su stariji od 4h (expires_at)
    3. Salje reminder supplier-ima za pending SENT orders
    """
    expired_count = expire_stale_orders()
    reminder_count = send_pending_reminders()
    click.echo(f'Expired {expired_count} orders, sent {reminder_count} reminders')


def expire_stale_orders():
    """Auto-expire SENT i OFFERED orders kojima je istekao expires_at."""
    from app.extensions import db
    from app.models import PartOrder, OrderStatus

    now = datetime.utcnow()
    expired = PartOrder.query.filter(
        PartOrder.status.in_([OrderStatus.SENT, OrderStatus.OFFERED]),
        PartOrder.expires_at.isnot(None),
        PartOrder.expires_at < now,
    ).all()

    count = 0
    for order in expired:
        if order.status == OrderStatus.SENT:
            order.status = OrderStatus.CANCELLED
            order.cancelled_at = now
            order.cancellation_reason = 'Automatski otkazano - dobavljac nije odgovorio u roku'
            order.cancelled_by = 'SYSTEM'
        elif order.status == OrderStatus.OFFERED:
            order.status = OrderStatus.CANCELLED
            order.cancelled_at = now
            order.cancellation_reason = 'Automatski otkazano - kupac nije potvrdio u roku'
            order.cancelled_by = 'SYSTEM'
            # BEZ stock rollback - stock nije bio dekrementiiran

        order.expires_at = None
        order.updated_at = now
        count += 1

        # Email (non-blocking)
        try:
            from app.services.email_service import send_supplier_order_email
            send_supplier_order_email(order, 'expired')
        except (ImportError, Exception):
            pass

    if count:
        db.session.commit()

    return count


def send_pending_reminders():
    """Salje reminder supplier-ima koji imaju pending SENT orders starije od 15 min."""
    from app.extensions import db
    from app.models import PartOrder, OrderStatus
    from app.models.notification import NotificationLog

    now = datetime.utcnow()
    threshold = now - timedelta(minutes=15)

    pending = PartOrder.query.filter(
        PartOrder.status == OrderStatus.SENT,
        PartOrder.sent_at < threshold,
        PartOrder.expires_at > now,
    ).all()

    count = 0
    for order in pending:
        # Proveri da li je reminder vec poslan u poslednjih 15 min
        event_key = f'reminder_sent_{order.id}_{now.strftime("%Y%m%d%H")}'
        if NotificationLog.already_sent(event_key):
            continue

        try:
            from app.services.email_service import send_supplier_order_email
            send_supplier_order_email(order, 'reminder_pending')
            count += 1
        except (ImportError, Exception):
            pass

    return count
