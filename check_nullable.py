"""Check if prezime column is nullable."""
from app import create_app
from app.extensions import db

app = create_app()
with app.app_context():
    result = db.session.execute(db.text(
        "SELECT column_name, is_nullable FROM information_schema.columns "
        "WHERE table_name = 'tenant_user' AND column_name = 'prezime'"
    )).fetchone()
    print(f"tenant_user.prezime: {result}")

    result2 = db.session.execute(db.text(
        "SELECT column_name, is_nullable FROM information_schema.columns "
        "WHERE table_name = 'service_representative' AND column_name = 'prezime'"
    )).fetchone()
    print(f"service_representative.prezime: {result2}")
