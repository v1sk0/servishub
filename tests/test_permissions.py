"""
Permission testovi — POS i Credits pristup po roli.
"""
import pytest
import json
from app.models.feature_flag import FeatureFlag
from app.models.user import TenantUser, UserLocation, UserRole
from app.api.middleware.jwt_utils import create_access_token


@pytest.fixture
def pos_enabled(db, tenant_a):
    ff = FeatureFlag(feature_key='pos_enabled', tenant_id=tenant_a.id, enabled=True)
    db.session.add(ff)
    db.session.commit()
    return ff


@pytest.fixture
def credits_enabled(db, tenant_a):
    ff = FeatureFlag(feature_key='credits_enabled', tenant_id=tenant_a.id, enabled=True)
    db.session.add(ff)
    db.session.commit()
    return ff


@pytest.fixture
def client_tech(app, db, user_tech_a):
    """Test klijent sa TECHNICIAN tokenom."""
    class AuthClient:
        def __init__(self):
            self._client = app.test_client()
            with app.app_context():
                token = create_access_token(user_tech_a.id, user_tech_a.tenant_id, user_tech_a.role.value)
                self._headers = {'Authorization': f'Bearer {token}'}

        def get(self, url, **kw):
            kw.setdefault('headers', {}).update(self._headers)
            return self._client.get(url, **kw)

        def post(self, url, **kw):
            kw.setdefault('headers', {}).update(self._headers)
            return self._client.post(url, **kw)

    db.session.commit()
    return AuthClient()


class TestPOSPermissions:
    """POS pristup po roli."""

    def test_owner_can_open_register(self, client_a, pos_enabled, location_a1):
        res = client_a.post('/api/v1/pos/register/open', json={
            'opening_cash': 5000,
            'location_id': location_a1.id
        })
        assert res.status_code == 201

    def test_technician_can_access_pos(self, client_tech, pos_enabled, location_a1):
        """Tehnicar moze da koristi POS (ako je flag aktivan)."""
        res = client_tech.get('/api/v1/pos/register/current')
        # 404 = nema otvorene kase, ali pristup je dozvoljen (nije 403)
        assert res.status_code in (200, 404)

    def test_unauthenticated_cannot_access_pos(self, app, pos_enabled):
        """Bez tokena ne moze pristup POS-u."""
        client = app.test_client()
        res = client.post('/api/v1/pos/register/open', json={'opening_cash': 1000})
        assert res.status_code in (401, 403, 422)


class TestCreditsPermissions:
    """Credits pristup po roli."""

    def test_owner_can_view_balance(self, client_a, credits_enabled):
        res = client_a.get('/api/v1/credits/')
        assert res.status_code == 200

    def test_technician_can_view_balance(self, client_tech, credits_enabled):
        """Tehnicar moze videti stanje kredita."""
        res = client_tech.get('/api/v1/credits/')
        assert res.status_code == 200

    def test_unauthenticated_cannot_view_credits(self, app, credits_enabled):
        """Bez tokena ne moze pristup kreditima."""
        client = app.test_client()
        res = client.get('/api/v1/credits/')
        assert res.status_code in (401, 403, 422)


class TestCrossTenantIsolation:
    """Tenant B ne moze pristupiti podacima tenanta A."""

    def test_tenant_b_cannot_access_tenant_a_pos(self, app, db, pos_enabled, user_b, location_a1):
        """Tenant B ne moze otvoriti kasu na lokaciji tenanta A."""
        with app.app_context():
            token = create_access_token(user_b.id, user_b.tenant_id, user_b.role.value)
            headers = {'Authorization': f'Bearer {token}'}

        client = app.test_client()
        res = client.post('/api/v1/pos/register/open',
                         json={'opening_cash': 1000, 'location_id': location_a1.id},
                         headers=headers)
        # Should fail - location doesn't belong to tenant B
        assert res.status_code in (400, 403, 404)