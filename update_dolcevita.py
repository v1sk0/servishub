"""
Script to add 9999 credits to Dolce Vita tenant.
Uses raw SQL to avoid SQLAlchemy Enum issue.

Run with: heroku run python update_dolcevita.py
"""
from app import create_app
from app.extensions import db
from app.models import Tenant
from sqlalchemy import text
from decimal import Decimal
from datetime import datetime, timezone

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

    # Update slug if needed
    if tenant.slug != 'dolcevita':
        old_slug = tenant.slug
        tenant.slug = 'dolcevita'
        print(f"Slug changed: {old_slug} -> dolcevita")
        db.session.commit()
    else:
        print("Slug already set to 'dolcevita'")

    # Get credit balance using raw SQL (avoiding enum issue)
    result = db.session.execute(text("""
        SELECT id, balance, total_received_free
        FROM credit_balance
        WHERE owner_type = 'tenant' AND tenant_id = :tenant_id
    """), {'tenant_id': tenant.id})
    row = result.fetchone()

    credits_to_add = Decimal('9999')

    if row:
        balance_id, current_balance, total_received_free = row
        print(f"Current balance: {current_balance}")

        # Update balance using raw SQL
        db.session.execute(text("""
            UPDATE credit_balance
            SET balance = balance + :amount,
                total_received_free = total_received_free + :amount,
                updated_at = :now
            WHERE id = :balance_id
        """), {
            'amount': credits_to_add,
            'balance_id': balance_id,
            'now': datetime.now(timezone.utc)
        })

        # Create transaction record
        db.session.execute(text("""
            INSERT INTO credit_transaction
            (credit_balance_id, transaction_type, amount, balance_before, balance_after, description, created_at)
            VALUES (:balance_id, 'ADMIN', :amount, :before, :after, :desc, :now)
        """), {
            'balance_id': balance_id,
            'amount': credits_to_add,
            'before': current_balance,
            'after': current_balance + credits_to_add,
            'desc': 'Admin: Interni servis - 9999 kredita',
            'now': datetime.now(timezone.utc)
        })

        db.session.commit()
        print(f"\n✅ Done!")
        print(f"  - Credits added: {credits_to_add}")
        print(f"  - Balance: {current_balance} -> {current_balance + credits_to_add}")
    else:
        # Create new balance
        print("No credit balance found, creating new one...")
        db.session.execute(text("""
            INSERT INTO credit_balance
            (owner_type, tenant_id, balance, total_purchased, total_spent, total_received_free, created_at, updated_at)
            VALUES ('tenant', :tenant_id, :amount, 0, 0, :amount, :now, :now)
        """), {
            'tenant_id': tenant.id,
            'amount': credits_to_add,
            'now': datetime.now(timezone.utc)
        })

        # Get the new balance id
        result = db.session.execute(text("""
            SELECT id FROM credit_balance WHERE owner_type = 'tenant' AND tenant_id = :tenant_id
        """), {'tenant_id': tenant.id})
        balance_id = result.scalar()

        # Create transaction record
        db.session.execute(text("""
            INSERT INTO credit_transaction
            (credit_balance_id, transaction_type, amount, balance_before, balance_after, description, created_at)
            VALUES (:balance_id, 'ADMIN', :amount, 0, :amount, :desc, :now)
        """), {
            'balance_id': balance_id,
            'amount': credits_to_add,
            'desc': 'Admin: Interni servis - 9999 kredita',
            'now': datetime.now(timezone.utc)
        })

        db.session.commit()
        print(f"\n✅ Done!")
        print(f"  - New credit balance created")
        print(f"  - Credits: {credits_to_add}")
