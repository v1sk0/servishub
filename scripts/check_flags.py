"""Check and seed feature flags for all tenants."""
from app import create_app
from app.extensions import db
from app.models.feature_flag import FeatureFlag
from app.models.tenant import Tenant

app = create_app()
with app.app_context():
    flags = FeatureFlag.query.all()
    print(f"Total flags: {len(flags)}")
    for f in flags:
        print(f"  tenant={f.tenant_id} key={f.feature_key} enabled={f.enabled}")

    tenants = Tenant.query.all()
    print(f"\nTotal tenants: {len(tenants)}")
    for t in tenants:
        print(f"  id={t.id} name={t.name}")

    # Seed flags for all tenants that don't have them
    keys = ['pos_enabled', 'credits_enabled']
    added = 0
    for t in tenants:
        for key in keys:
            exists = FeatureFlag.query.filter_by(tenant_id=t.id, feature_key=key).first()
            if not exists:
                ff = FeatureFlag(tenant_id=t.id, feature_key=key, enabled=True)
                db.session.add(ff)
                added += 1
                print(f"  + Added {key} for tenant {t.id} ({t.name})")

    if added:
        db.session.commit()
        print(f"\nSeeded {added} feature flags.")
    else:
        print("\nAll flags already exist.")