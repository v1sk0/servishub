"""
Billing testovi — PROMO tranzicija, trust 72h, nema bypass.
"""
import pytest
from datetime import datetime, timedelta
from app.models.tenant import Tenant, TenantStatus


class TestPromoTransition:
    """PROMO -> ACTIVE automatska tranzicija."""

    def test_new_tenant_starts_as_promo(self, db, tenant_a):
        assert tenant_a.status == TenantStatus.PROMO
        assert tenant_a.promo_ends_at is not None

    def test_promo_is_active(self, db, tenant_a):
        """PROMO tenant ima aktivan pristup."""
        assert tenant_a.is_active is True

    def test_promo_activate_sets_fields(self, db, tenant_a):
        """activate_promo postavlja status i promo_ends_at."""
        tenant_a.activate_promo(months=2)
        db.session.commit()
        assert tenant_a.status == TenantStatus.PROMO
        assert tenant_a.promo_ends_at > datetime.utcnow()

    def test_expired_promo_is_expired(self, db, tenant_a):
        """Istekao PROMO se detektuje kao expired."""
        tenant_a.promo_ends_at = datetime.utcnow() - timedelta(days=1)
        db.session.commit()
        assert tenant_a.days_remaining == 0


class TestTrustActivation:
    """Trust / 'Na rec' — 72h period."""

    def test_trust_not_active_by_default(self, db, tenant_a):
        assert tenant_a.is_trust_active is False

    def test_activate_trust_sets_72h(self, db, tenant_a):
        """Aktivacija trust-a traje 72 sata."""
        tenant_a.activate_trust()
        db.session.commit()
        assert tenant_a.is_trust_active is True
        assert tenant_a.trust_hours_remaining > 0
        assert tenant_a.trust_hours_remaining <= 72

    def test_expired_trust_is_inactive(self, db, tenant_a):
        """Istekao trust (>72h) je neaktivan."""
        tenant_a.trust_activated_at = datetime.utcnow() - timedelta(hours=73)
        db.session.commit()
        assert tenant_a.is_trust_active is False
        assert tenant_a.trust_hours_remaining == 0

    def test_trust_once_per_month(self, db, tenant_a):
        """Trust se moze koristiti jednom mesecno."""
        tenant_a.activate_trust()
        tenant_a.last_trust_activation_period = datetime.utcnow().strftime('%Y-%m')
        db.session.commit()
        assert tenant_a.can_activate_trust is False


class TestNoBypass:
    """Nema activate/unsuspend bypass endpointa."""

    def test_no_activate_endpoint(self, app, client_a):
        """Activate endpoint je uklonjen."""
        # Admin tenants activate treba da vrati 404 ili 405
        res = client_a.post('/api/admin/tenants/1/activate', json={})
        assert res.status_code in (404, 405)

    def test_no_unsuspend_endpoint(self, app, client_a):
        """Unsuspend endpoint je uklonjen."""
        res = client_a.post('/api/admin/tenants/1/unsuspend', json={})
        assert res.status_code in (404, 405)