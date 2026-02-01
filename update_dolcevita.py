"""
Script to enable credits feature flag for Dolce Vita tenant.

Run with: heroku run python update_dolcevita.py
"""
from app import create_app
from app.extensions import db
from app.models import Tenant
from app.models.feature_flag import FeatureFlag
from sqlalchemy import text

app = create_app()

with app.app_context():
    # Find Dolce Vita tenant
    tenant = Tenant.query.filter(
        (Tenant.slug == 'dolcevita') |
        (Tenant.name.ilike('%dolce%vita%'))
    ).first()

    if not tenant:
        print("Tenant not found. Available tenants:")
        for t in Tenant.query.all():
            print(f"  {t.id}: {t.name} (slug: {t.slug})")
        exit(1)

    print(f"Found tenant: ID={tenant.id}, Name={tenant.name}, slug={tenant.slug}")

    # Enable credits_enabled feature flag for this tenant
    flag = FeatureFlag.query.filter_by(
        feature_key='credits_enabled',
        tenant_id=tenant.id
    ).first()

    if flag:
        if flag.enabled:
            print("credits_enabled flag already enabled")
        else:
            flag.enabled = True
            db.session.commit()
            print("credits_enabled flag ENABLED")
    else:
        flag = FeatureFlag(
            feature_key='credits_enabled',
            tenant_id=tenant.id,
            enabled=True
        )
        db.session.add(flag)
        db.session.commit()
        print("credits_enabled flag CREATED and ENABLED")

    # Check credit balance
    result = db.session.execute(text("""
        SELECT balance FROM credit_balance
        WHERE owner_type = 'tenant' AND tenant_id = :tenant_id
    """), {'tenant_id': tenant.id})
    row = result.fetchone()

    if row:
        print(f"Current credit balance: {row[0]}")
    else:
        print("WARNING: No credit balance found!")

    print("\n✅ Done! Refresh the page to see the credit widget.")
