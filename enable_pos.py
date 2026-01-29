"""Enable pos_enabled feature flag for tenant 68."""
from app import create_app
from app.extensions import db
from app.models.feature_flag import FeatureFlag

app = create_app()
with app.app_context():
    flag = FeatureFlag.query.filter_by(tenant_id=68, feature_key='pos_enabled').first()
    if flag:
        flag.enabled = True
        print(f'Updated existing flag: {flag.enabled}')
    else:
        flag = FeatureFlag(tenant_id=68, feature_key='pos_enabled', enabled=True)
        db.session.add(flag)
        print('Created new flag')
    db.session.commit()

    # Verify
    flag = FeatureFlag.query.filter_by(tenant_id=68, feature_key='pos_enabled').first()
    print(f'pos_enabled for tenant 68 is now: {flag.enabled}')
