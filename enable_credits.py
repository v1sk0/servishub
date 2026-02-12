"""Enable credits_enabled feature flag for Xphone tenant."""
from app import create_app
from app.extensions import db
from app.models.tenant import Tenant
from app.models.feature_flag import FeatureFlag

app = create_app()
with app.app_context():
    t = Tenant.query.filter(Tenant.name.ilike('%xphone%')).first()
    if not t:
        print('Tenant Xphone not found!')
        exit(1)

    print(f'Found tenant: ID={t.id}, Name={t.name}')

    existing = FeatureFlag.query.filter_by(feature_key='credits_enabled', tenant_id=t.id).first()
    if existing:
        if existing.enabled:
            print('Credits already enabled.')
        else:
            existing.enabled = True
            db.session.commit()
            print('Credits flag updated to enabled.')
    else:
        flag = FeatureFlag(feature_key='credits_enabled', tenant_id=t.id, enabled=True)
        db.session.add(flag)
        db.session.commit()
        print('Credits flag created and enabled.')

    flags = FeatureFlag.query.filter_by(tenant_id=t.id).all()
    for f in flags:
        print(f'  {f.feature_key} = {f.enabled}')
