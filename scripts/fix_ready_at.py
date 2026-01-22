"""Fix ready_at for existing READY tickets."""
from app import create_app
from app.models.ticket import ServiceTicket, TicketStatus
from app.extensions import db

app = create_app()
with app.app_context():
    tickets = ServiceTicket.query.filter(
        ServiceTicket.status == TicketStatus.READY,
        ServiceTicket.ready_at.is_(None)
    ).all()

    print(f'Found {len(tickets)} READY tickets without ready_at')

    for t in tickets:
        t.ready_at = t.updated_at
        print(f'  Setting ready_at for ticket #{t.ticket_number} to {t.updated_at}')

    db.session.commit()
    print('Done!')