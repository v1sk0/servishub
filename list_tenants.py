"""Script to list all tenants and subscription settings."""
from app import create_app
from app.models.tenant import Tenant, TenantStatus
from app.models.platform_settings import PlatformSettings

app = create_app()
with app.app_context():
    print('='*60)
    print('LISTA SVIH TENANTA:')
    print('='*60)
    tenants = Tenant.query.order_by(Tenant.created_at).all()
    for t in tenants:
        print(f'ID: {t.id}')
        print(f'  Name: {t.name}')
        print(f'  Status: {t.status.value}')
        print(f'  Email: {t.email}')
        print(f'  PIB: {t.pib}')
        print(f'  Days remaining: {t.days_remaining}')
        if t.promo_ends_at:
            print(f'  Promo ends: {t.promo_ends_at}')
        if t.trial_ends_at:
            print(f'  Trial ends: {t.trial_ends_at}')
        if t.subscription_ends_at:
            print(f'  Subscription ends: {t.subscription_ends_at}')
        print('')

    print(f'UKUPNO TENANTA: {len(tenants)}')
    print('')
    print('='*60)
    print('GRUPACIJA PO STATUSU:')
    print('='*60)
    for status in TenantStatus:
        count = Tenant.query.filter_by(status=status).count()
        if count > 0:
            print(f'{status.value}: {count}')
    print('')
    print('='*60)
    print('PLATFORM SETTINGS:')
    print('='*60)
    s = PlatformSettings.get_settings()
    print(f'Base price: {s.base_price} {s.currency}')
    print(f'Location price: {s.location_price} {s.currency}')
    print(f'Trial days: {s.trial_days}')
    print(f'Demo days: {s.demo_days}')
    print(f'Grace period: {s.grace_period_days} days')