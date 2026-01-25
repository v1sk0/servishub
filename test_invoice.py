"""Test script for generating invoice for a tenant."""
import sys
from app import create_app
from app.models import Tenant, SubscriptionPayment, PlatformSettings
from app.services.ips_service import IPSService
from app.extensions import db
from datetime import datetime
from decimal import Decimal

app = create_app()

with app.app_context():
    # Find tenant - use testservis or first active tenant
    tenant = Tenant.query.filter_by(slug='testservis').first()

    if not tenant:
        tenant = Tenant.query.filter_by(is_active=True).first()

    if not tenant:
        print("No active tenants found!")
        sys.exit(1)

    print(f"Found tenant: {tenant.slug} (ID: {tenant.id})")
    print(f"  Plan: {tenant.subscription_plan}")
    print(f"  Monthly fee: {tenant.monthly_fee}")

    # Get last invoice number
    last_payment = SubscriptionPayment.query.order_by(
        SubscriptionPayment.id.desc()
    ).first()

    if last_payment and last_payment.invoice_number:
        # Parse last number and increment
        parts = last_payment.invoice_number.split('-')
        last_seq = int(parts[-1])
        new_seq = last_seq + 1
    else:
        new_seq = 1

    # Generate invoice number
    now = datetime.utcnow()
    invoice_number = f"SH-{now.year}-{new_seq:06d}"

    # Generate payment reference using IPSService
    ref_data = IPSService.generate_payment_reference(tenant.id, new_seq)

    print(f"\nGenerating invoice:")
    print(f"  Invoice Number: {invoice_number}")
    print(f"  Payment Reference: {ref_data['full']}")
    print(f"  Display: {ref_data['display']}")
    print(f"  Amount: {tenant.monthly_fee or 5400} RSD")

    # Create payment
    payment = SubscriptionPayment(
        tenant_id=tenant.id,
        invoice_number=invoice_number,
        payment_reference=ref_data['full'],
        payment_reference_model=ref_data['model'],
        total_amount=Decimal(str(tenant.monthly_fee or 5400)),
        currency='RSD',
        status='PENDING',
        period_start=now.replace(day=1),
        period_end=now.replace(day=28),
        due_date=now.replace(day=15),
        created_at=now
    )

    db.session.add(payment)
    db.session.commit()

    print(f"\n✅ Invoice created successfully!")
    print(f"  Payment ID: {payment.id}")
    print(f"  Status: {payment.status}")
