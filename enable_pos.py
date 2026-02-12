"""Add 9999 credits for Xphone tenant (ID=133)."""
from decimal import Decimal
from app import create_app
from app.extensions import db
from app.models.tenant import Tenant
from app.models.credits import OwnerType, CreditTransactionType
from app.services.credit_service import add_credits

app = create_app()
with app.app_context():
    t = Tenant.query.filter(Tenant.name.ilike('%xphone%')).first()
    if not t:
        print('Tenant Xphone not found!')
        exit(1)

    print(f'Found tenant: ID={t.id}, Name={t.name}')

    txn = add_credits(
        owner_type=OwnerType.TENANT,
        owner_id=t.id,
        amount=Decimal('9999'),
        transaction_type=CreditTransactionType.ADMIN,
        description='Admin: 9999 credits for XPhone tenant',
        ref_type='admin_adjust',
    )
    db.session.commit()

    print(f'Added 9999 credits. Transaction ID: {txn.id}')
    print(f'Balance after: {txn.balance_after}')
