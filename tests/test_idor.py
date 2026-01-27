"""
IDOR Security Tests — verifikuju tenant izolaciju i location scoping.

Testira:
1. Tenant A ne sme videti resurse Tenant-a B (cross-tenant → 404)
2. TECHNICIAN ne sme pristupiti tuđoj lokaciji unutar istog tenanta (→ 403)
3. OWNER može cross-location (→ 200)
4. Invariante: poslednja lokacija, deactivation fallback
"""
import pytest
from app.extensions import db
from app.models.tenant import ServiceLocation, LocationStatus


# =============================================================================
# 1. TENANT ISOLATION — cross-tenant pristup mora biti 404 (ne 403!)
# =============================================================================

class TestTenantIsolation:
    """Tenant A ne sme videti resurse Tenant-a B."""

    def test_locations_cross_tenant(self, client_a, location_b1):
        """GET /locations/<location_b_id> sa JWT-em tenanta A → 404"""
        res = client_a.get(f'/api/v1/locations/{location_b1.id}')
        assert res.status_code == 404

    def test_select_location_cross_tenant(self, client_a, location_b1):
        """POST /auth/select-location sa tuđom lokacijom → 400 ili 403"""
        res = client_a.post('/api/v1/auth/select-location',
                            json={'location_id': location_b1.id})
        assert res.status_code in (400, 403)

    def test_location_list_only_own_tenant(self, client_a, location_a1, location_a2, location_b1):
        """GET /locations vraća samo lokacije svog tenanta"""
        res = client_a.get('/api/v1/locations')
        assert res.status_code == 200
        data = res.get_json()
        location_ids = [loc['id'] for loc in data['locations']]
        assert location_a1.id in location_ids
        assert location_b1.id not in location_ids

    def test_delete_location_cross_tenant(self, client_a, location_b1):
        """DELETE /locations/<location_b_id> → 404"""
        res = client_a.delete(f'/api/v1/locations/{location_b1.id}')
        assert res.status_code == 404

    def test_update_location_cross_tenant(self, client_a, location_b1):
        """PUT /locations/<location_b_id> → 404"""
        res = client_a.put(f'/api/v1/locations/{location_b1.id}',
                           json={'name': 'Hacked'})
        assert res.status_code == 404


# =============================================================================
# 2. LOCATION SCOPING — TECHNICIAN vs OWNER cross-location
# =============================================================================

class TestLocationScoping:
    """TECHNICIAN ne sme pristupiti tuđoj lokaciji unutar istog tenanta."""

    def test_select_location_technician_no_access(self, client_tech_a, location_a2):
        """TECHNICIAN pokušava select-location na lokaciju kojoj nema pristup → 403"""
        res = client_tech_a.post('/api/v1/auth/select-location',
                                 json={'location_id': location_a2.id})
        assert res.status_code == 403

    def test_select_location_owner_any_location(self, client_admin_a, location_a2):
        """OWNER može izabrati bilo koju aktivnu lokaciju → 200"""
        res = client_admin_a.post('/api/v1/auth/select-location',
                                  json={'location_id': location_a2.id})
        assert res.status_code == 200
        data = res.get_json()
        assert data['location_id'] == location_a2.id

    def test_select_nonexistent_location(self, client_a):
        """select-location sa nepostojećim ID-em → 400"""
        res = client_a.post('/api/v1/auth/select-location',
                            json={'location_id': 99999})
        assert res.status_code == 400

    def test_select_location_missing_body(self, client_a):
        """select-location bez location_id → 400"""
        res = client_a.post('/api/v1/auth/select-location', json={})
        assert res.status_code == 400


# =============================================================================
# 3. INVARIANT ENFORCEMENT — lokacijske invariante
# =============================================================================

class TestInvariantEnforcement:
    """Testovi za location invariante."""

    def test_cannot_delete_primary_location(self, client_admin_a, location_a1):
        """Brisanje primary lokacije → 400"""
        res = client_admin_a.delete(f'/api/v1/locations/{location_a1.id}')
        assert res.status_code == 400
        assert 'primary' in res.get_json()['error'].lower()

    def test_cannot_delete_last_active_location(self, app, client_admin_a, location_a1, tenant_a):
        """Ako je jedina aktivna lokacija (i primary), ne može se obrisati"""
        # location_a1 je primary i jedina — ne sme se obrisati
        res = client_admin_a.delete(f'/api/v1/locations/{location_a1.id}')
        assert res.status_code == 400

    def test_delete_non_primary_archives(self, app, client_admin_a, location_a1, location_a2):
        """Brisanje ne-primary lokacije → arhivira je"""
        res = client_admin_a.delete(f'/api/v1/locations/{location_a2.id}')
        assert res.status_code == 200
        with app.app_context():
            db.session.expire_all()
            loc = ServiceLocation.query.get(location_a2.id)
            assert loc.status == LocationStatus.ARCHIVED
            assert loc.is_active is False
            assert loc.archived_at is not None

    def test_deactivation_fallback(self, app, client_admin_a, location_a1, location_a2, user_tech_a):
        """Deaktivacija lokacije → korisnici prebačeni na primary"""
        # Postavi tech korisnika na location_a2
        with app.app_context():
            user_tech_a.current_location_id = location_a2.id
            db.session.commit()

        # Deaktiviraj location_a2
        res = client_admin_a.put(f'/api/v1/locations/{location_a2.id}',
                                 json={'is_active': False})
        assert res.status_code == 200

        with app.app_context():
            db.session.expire_all()
            from app.models.user import TenantUser
            user = TenantUser.query.get(user_tech_a.id)
            # Korisnik je prebačen na primary (location_a1)
            assert user.current_location_id == location_a1.id


# =============================================================================
# 4. AUTH ENDPOINT PROTECTION
# =============================================================================

class TestAuthProtection:
    """Testovi za auth endpoint zaštitu."""

    def test_me_returns_current_location(self, client_a, location_a1, admin_a):
        """GET /auth/me vraća lokacije korisnika"""
        res = client_a.get('/api/v1/auth/me')
        assert res.status_code == 200
        data = res.get_json()
        assert data['user']['id'] == admin_a.id
        location_ids = [loc['id'] for loc in data['locations']]
        assert location_a1.id in location_ids

    def test_unauthenticated_select_location(self, app):
        """POST /auth/select-location bez tokena → 401"""
        client = app.test_client()
        res = client.post('/api/v1/auth/select-location',
                          json={'location_id': 1})
        assert res.status_code == 401
