"""Reset POS for today."""
from app import create_app
from app.extensions import db
from app.models.pos import CashRegisterSession, Receipt, ReceiptItem, DailyReport
from datetime import date

app = create_app()
with app.app_context():
    today = date.today()
    sessions = CashRegisterSession.query.filter_by(date=today).all()
    for s in sessions:
        receipts = Receipt.query.filter_by(session_id=s.id).all()
        for r in receipts:
            ReceiptItem.query.filter_by(receipt_id=r.id).delete()
            db.session.delete(r)
        reports = DailyReport.query.filter_by(session_id=s.id).all()
        for rpt in reports:
            db.session.delete(rpt)
        db.session.delete(s)
    db.session.commit()
    print(f'Deleted {len(sessions)} session(s) for {today}. POS is clean.')