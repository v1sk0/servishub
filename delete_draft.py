"""Delete orphaned DRAFT receipt 20260127-001."""
from app import create_app
from app.extensions import db
from app.models.pos import Receipt, ReceiptItem

app = create_app()
with app.app_context():
    r = Receipt.query.filter_by(receipt_number='20260127-001').first()
    if r:
        print(f'Found: id={r.id}, status={r.status.value}, total={r.total_amount}')
        ReceiptItem.query.filter_by(receipt_id=r.id).delete()
        db.session.delete(r)
        db.session.commit()
        print('Deleted.')
    else:
        print('Receipt 20260127-001 not found')

    # Also close any open session for today to start fresh
    from app.models.pos import CashRegisterSession, CashRegisterStatus
    from datetime import date
    sessions = CashRegisterSession.query.filter_by(
        date=date.today(),
        status=CashRegisterStatus.OPEN
    ).all()
    for s in sessions:
        print(f'Closing session id={s.id}, tenant={s.tenant_id}, location={s.location_id}')
        s.status = CashRegisterStatus.CLOSED
    db.session.commit()
    print(f'Closed {len(sessions)} open session(s). Ready for fresh test.')