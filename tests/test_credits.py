"""
Credits testovi — add/deduct/refund, promo, idempotency, negativni scenariji.
"""
import pytest
import json
from decimal import Decimal
from app.models.feature_flag import FeatureFlag
from app.models.credits import CreditBalance, OwnerType, CreditTransactionType
from app.services.credit_service import (
    get_or_create_balance, add_credits, deduct_credits,
    refund_credits, CREDIT_PACKAGES
)


@pytest.fixture
def credits_enabled(db, tenant_a):
    """Aktiviraj Credits feature flag za tenant A."""
    ff = FeatureFlag(
        feature_key='credits_enabled',
        tenant_id=tenant_a.id,
        enabled=True
    )
    db.session.add(ff)
    db.session.commit()
    return ff


@pytest.fixture
def balance_a(db, tenant_a):
    """Kreiran balance za tenant A sa 50 kredita."""
    bal = get_or_create_balance(OwnerType.TENANT, tenant_a.id)
    add_credits(OwnerType.TENANT, tenant_a.id, Decimal('50'),
                CreditTransactionType.WELCOME, 'Test krediti')
    db.session.commit()
    return bal


class TestCreditOperations:
    """Core credit operacije."""

    def test_add_credits(self, db, tenant_a):
        bal = get_or_create_balance(OwnerType.TENANT, tenant_a.id)
        add_credits(OwnerType.TENANT, tenant_a.id, Decimal('100'),
                    CreditTransactionType.WELCOME, 'Test')
        db.session.commit()
        db.session.refresh(bal)
        assert bal.balance == Decimal('100')

    def test_deduct_credits(self, db, tenant_a, balance_a):
        deduct_credits(OwnerType.TENANT, tenant_a.id, Decimal('20'),
                       CreditTransactionType.CONNECTION_FEE, 'Test potrosnja')
        db.session.commit()
        db.session.refresh(balance_a)
        assert balance_a.balance == Decimal('30')

    def test_deduct_insufficient_balance(self, db, tenant_a, balance_a):
        """Negativan test: nedovoljan balance."""
        result = deduct_credits(OwnerType.TENANT, tenant_a.id, Decimal('100'),
                                CreditTransactionType.CONNECTION_FEE, 'Previse')
        assert result is False

    def test_refund_credits(self, db, tenant_a, balance_a):
        txn = deduct_credits(OwnerType.TENANT, tenant_a.id, Decimal('20'),
                             CreditTransactionType.CONNECTION_FEE, 'Potrosnja')
        db.session.flush()
        refund_credits(OwnerType.TENANT, tenant_a.id, txn.id, 'Refund')
        db.session.commit()
        db.session.refresh(balance_a)
        assert balance_a.balance == Decimal('50')


class TestCreditsAPI:
    """Credits API endpointi."""

    def test_get_balance(self, client_a, credits_enabled, balance_a):
        res = client_a.get('/api/v1/credits/')
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data['balance'] == 50.0

    def test_get_packages(self, client_a, credits_enabled):
        res = client_a.get('/api/v1/credits/packages')
        assert res.status_code == 200
        data = json.loads(res.data)
        assert len(data['packages']) == len(CREDIT_PACKAGES)

    def test_purchase_idempotency(self, client_a, credits_enabled):
        """Dupla kupovina sa istim idempotency_key ne kreira duplikat."""
        payload = {
            'package': 'starter',
            'payment_method': 'bank_transfer',
            'idempotency_key': 'test-idem-key-123'
        }
        res1 = client_a.post('/api/v1/credits/purchase', json=payload)
        assert res1.status_code == 201

        res2 = client_a.post('/api/v1/credits/purchase', json=payload)
        assert res2.status_code == 200
        data2 = json.loads(res2.data)
        assert 'deduplicirano' in data2.get('message', '').lower() or data2.get('purchase_id')

    def test_purchase_without_idempotency_key_fails(self, client_a, credits_enabled):
        """Kupovina bez idempotency_key vraca 400."""
        res = client_a.post('/api/v1/credits/purchase', json={
            'package': 'starter',
            'payment_method': 'bank_transfer'
        })
        assert res.status_code == 400

    def test_purchase_invalid_package_fails(self, client_a, credits_enabled):
        """Nepoznat paket vraca 400."""
        res = client_a.post('/api/v1/credits/purchase', json={
            'package': 'nonexistent',
            'payment_method': 'bank_transfer',
            'idempotency_key': 'key-999'
        })
        assert res.status_code == 400

    def test_transaction_history(self, client_a, credits_enabled, balance_a):
        res = client_a.get('/api/v1/credits/history')
        assert res.status_code == 200
        data = json.loads(res.data)
        assert 'transactions' in data


class TestCreditsDisabled:
    """Credits disabled - feature flag OFF."""

    def test_credits_disabled_returns_403(self, client_a):
        res = client_a.get('/api/v1/credits/')
        assert res.status_code == 403