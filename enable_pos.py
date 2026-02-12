"""Enable POS feature flag for Xphone tenant."""
from app import create_app
from app.extensions import db
from app.models.tenant import Tenant
from app.models.feature_flag import FeatureFlag

app = create_app()
with app.app_context():
    # Find Xphone tenant
    t = Tenant.query.filter(Tenant.name.ilike('%xphone%')).first()
    if not t:
        print('Tenant Xphone not found!')
        exit(1)

    print(f'Found tenant: ID={t.id}, Name={t.name}')

    # Check if flag already exists
    existing = FeatureFlag.query.filter_by(feature_key='pos_enabled', tenant_id=t.id).first()
    if existing:
        if existing.enabled:
            print('POS already enabled for this tenant.')
        else:
            existing.enabled = True
            db.session.commit()
            print('POS flag updated to enabled.')
    else:
        flag = FeatureFlag(feature_key='pos_enabled', tenant_id=t.id, enabled=True)
        db.session.add(flag)
        db.session.commit()
        print('POS flag created and enabled.')

    # Verify
    flags = FeatureFlag.query.filter_by(tenant_id=t.id).all()
    for f in flags:
        print(f'  {f.feature_key} = {f.enabled}')
