"""Check SMS config for Dolce Vita tenant."""
from app import create_app
from app.models import Tenant
from app.models.sms_management import TenantSmsConfig

app = create_app()

with app.app_context():
    tenant = Tenant.query.filter_by(slug='dolcevita').first()
    if not tenant:
        print("Tenant not found!")
        exit(1)

    print(f"Tenant: {tenant.name} (ID: {tenant.id})")

    config = TenantSmsConfig.get_or_create(tenant.id)
    print(f"\nSMS Config:")
    print(f"  - sms_enabled: {config.sms_enabled}")
    print(f"  - monthly_limit: {config.monthly_limit}")
    print(f"  - current_usage: {config.get_current_month_usage()}")
    print(f"  - remaining: {config.get_remaining()}")
    print(f"  - can_send: {config.can_send()}")
