"""Script to migrate all tenants to PROMO and remove TRIAL/DEMO."""
from datetime import datetime
from dateutil.relativedelta import relativedelta
from app import create_app
from app.models.tenant import Tenant, TenantStatus
from app.models.platform_settings import PlatformSettings
from app.extensions import db

app = create_app()
with app.app_context():
    print('='*60)
    print('MIGRACIJA NA PROMO LICENCU')
    print('='*60)

    # 1. Prebaci sve tenante na PROMO
    tenants = Tenant.query.all()
    promo_end = datetime.utcnow() + relativedelta(months=2)

    for t in tenants:
        old_status = t.status.value
        t.status = TenantStatus.PROMO
        t.promo_ends_at = promo_end
        # Clear old fields
        t.trial_ends_at = None
        t.demo_ends_at = None
        print(f'[OK] {t.name}: {old_status} -> PROMO (do {promo_end.strftime("%Y-%m-%d")})')

    db.session.commit()
    print(f'\nPrebaceno {len(tenants)} tenanta na PROMO.')

    # 2. Ukloni TRIAL i DEMO iz PlatformSettings
    print('')
    print('='*60)
    print('UKLANJANJE TRIAL/DEMO IZ PLATFORM SETTINGS')
    print('='*60)

    settings = PlatformSettings.get_settings()
    old_trial = settings.trial_days
    old_demo = settings.demo_days

    settings.trial_days = 0
    settings.demo_days = 0
    db.session.commit()

    print(f'trial_days: {old_trial} -> 0')
    print(f'demo_days: {old_demo} -> 0')

    # 3. Verifikacija
    print('')
    print('='*60)
    print('VERIFIKACIJA:')
    print('='*60)
    for status in TenantStatus:
        count = Tenant.query.filter_by(status=status).count()
        if count > 0:
            print(f'{status.value}: {count}')

    print('')
    print('DONE! Svi tenanti su sada na PROMO licenci (2 meseca FREE).')