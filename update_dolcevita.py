"""
Script to update Dolce Vita tenant:
1. Set slug to 'dolcevita' (for dolcevita.servishub.rs)
2. Add 9999 credits

Run with: heroku run python update_dolcevita.py
"""
from app import create_app
from app.extensions import db
from app.models import Tenant
from app.models.credits import CreditBalance, CreditTransaction, OwnerType, CreditTransactionType
from decimal import Decimal
from datetime import datetime, timezone

app = create_app()

with app.app_context():
    # Find Dolce Vita tenant
    tenant = Tenant.query.filter(
        (Tenant.name.ilike('%dolce%vita%')) |
        (Tenant.name.ilike('%dolcevita%'))
    ).first()

    if not tenant:
        # List all tenants
        print("Tenant not found. Available tenants:")
        for t in Tenant.query.all():
            print(f"  {t.id}: {t.name} (slug: {t.slug})")
        exit(1)

    print(f"Found tenant: ID={tenant.id}, Name={tenant.name}, Current slug={tenant.slug}")

    # 1. Update slug
    old_slug = tenant.slug
    tenant.slug = 'dolcevita'
    print(f"Slug changed: {old_slug} -> dolcevita")

    # 2. Add 9999 credits
    # Get or create credit balance
    balance = CreditBalance.query.filter_by(
        owner_type=OwnerType.TENANT,
        tenant_id=tenant.id
    ).first()

    if not balance:
        balance = CreditBalance(
            owner_type=OwnerType.TENANT,
            tenant_id=tenant.id,
            current_balance=Decimal('0'),
            total_purchased=Decimal('0'),
            total_spent=Decimal('0'),
            total_received_free=Decimal('0')
        )
        db.session.add(balance)
        db.session.flush()

    credits_to_add = Decimal('9999')
    balance_before = balance.current_balance

    # Update balance
    balance.current_balance += credits_to_add
    balance.total_received_free += credits_to_add

    # Create transaction record
    transaction = CreditTransaction(
        credit_balance_id=balance.id,
        transaction_type=CreditTransactionType.ADMIN,
        amount=credits_to_add,
        balance_before=balance_before,
        balance_after=balance.current_balance,
        description='Admin: Interni servis - 9999 kredita',
        created_at=datetime.now(timezone.utc)
    )
    db.session.add(transaction)

    print(f"Credits added: {balance_before} + {credits_to_add} = {balance.current_balance}")

    # Commit changes
    db.session.commit()
    print("\n✅ Done!")
    print(f"  - Slug: dolcevita.servishub.rs")
    print(f"  - Credits: {balance.current_balance}")
