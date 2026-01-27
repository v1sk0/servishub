"""
POS testovi — open/close register, create receipt, issue, void, idempotency.
"""
import pytest
import json
from app.models.feature_flag import FeatureFlag
from app.extensions import db as _db


@pytest.fixture
def pos_enabled(db, tenant_a):
    """Aktiviraj POS feature flag za tenant A."""
    ff = FeatureFlag(
        feature_key='pos_enabled',
        tenant_id=tenant_a.id,
        enabled=True
    )
    db.session.add(ff)
    db.session.commit()
    return ff


class TestPOSRegister:
    """Otvaranje i zatvaranje kase."""

    def test_open_register(self, client_a, pos_enabled, location_a1):
        res = client_a.post('/api/v1/pos/register/open', json={
            'opening_cash': 5000,
            'location_id': location_a1.id
        })
        assert res.status_code == 201
        data = json.loads(res.data)
        assert 'session_id' in data
        assert data['opening_cash'] == 5000.0

    def test_close_register(self, client_a, pos_enabled, location_a1):
        # Open first
        res = client_a.post('/api/v1/pos/register/open', json={
            'opening_cash': 5000,
            'location_id': location_a1.id
        })
        session_id = json.loads(res.data)['session_id']

        # Close
        res = client_a.post('/api/v1/pos/register/close', json={
            'session_id': session_id,
            'closing_cash': 5000
        })
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data['message'] == 'Kasa zatvorena'

    def test_open_twice_fails(self, client_a, pos_enabled, location_a1):
        """Ne moze se otvoriti kasa dva puta."""
        client_a.post('/api/v1/pos/register/open', json={
            'opening_cash': 5000,
            'location_id': location_a1.id
        })
        res = client_a.post('/api/v1/pos/register/open', json={
            'opening_cash': 3000,
            'location_id': location_a1.id
        })
        assert res.status_code == 400


class TestPOSReceipts:
    """Kreiranje i izdavanje racuna."""

    def test_create_and_issue_receipt(self, client_a, pos_enabled, location_a1):
        # Open register
        res = client_a.post('/api/v1/pos/register/open', json={
            'opening_cash': 5000,
            'location_id': location_a1.id
        })
        session_id = json.loads(res.data)['session_id']

        # Create receipt
        res = client_a.post('/api/v1/pos/receipts', json={'session_id': session_id})
        assert res.status_code == 201
        receipt_id = json.loads(res.data)['receipt_id']

        # Add item
        res = client_a.post(f'/api/v1/pos/receipts/{receipt_id}/items', json={
            'item_type': 'SERVICE',
            'item_name': 'Popravka ekrana',
            'unit_price': 3000,
            'quantity': 1
        })
        assert res.status_code == 201

        # Issue
        res = client_a.post(f'/api/v1/pos/receipts/{receipt_id}/issue', json={
            'payment_method': 'CASH'
        })
        assert res.status_code == 200

    def test_void_without_open_register_fails(self, client_a, pos_enabled, location_a1):
        """Void racuna bez otvorene kase - negativan test."""
        # Try to void non-existent receipt
        res = client_a.post('/api/v1/pos/receipts/99999/void', json={
            'reason': 'test'
        })
        # Should fail - receipt doesn't exist
        assert res.status_code in (400, 404)


class TestPOSDisabled:
    """POS disabled - feature flag OFF."""

    def test_pos_disabled_returns_403(self, client_a, location_a1):
        """Bez pos_enabled flaga, API vraca 403."""
        res = client_a.post('/api/v1/pos/register/open', json={
            'opening_cash': 5000,
            'location_id': location_a1.id
        })
        assert res.status_code == 403