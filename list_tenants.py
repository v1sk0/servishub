"""List all tenants in the database."""
from app import create_app
from app.extensions import db
from app.models import Tenant

app = create_app()
with app.app_context():
    tenants = Tenant.query.all()
    print(f"\n=== Found {len(tenants)} tenants ===\n")
    for t in tenants:
        print(f"ID={t.id} | Name={t.name} | Slug={t.slug} | Status={t.status}")
    print()