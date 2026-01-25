"""Check tenants in the database."""
from app import create_app
from app.models import Tenant

app = create_app()

with app.app_context():
    tenants = Tenant.query.all()
    print(f"Total tenants: {len(tenants)}")
    for t in tenants:
        print(f"ID: {t.id}, Slug: {t.slug}, Status: {t.status}, Plan: {t.subscription_plan}, Fee: {t.monthly_fee}")
