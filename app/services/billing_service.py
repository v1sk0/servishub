"""
Billing Service - Server-side billing enforcement.

Lokacijski limiti po planu, prorate obračun, gating novih lokacija.
UI NE SME računati iznose — ovaj servis je jedini izvor istine.
"""

from datetime import date
from decimal import Decimal

from ..extensions import db
from ..models import Tenant, PlatformSettings
from ..models.tenant import ServiceLocation, LocationStatus


# Limiti aktivnih lokacija po paketu
# TODO: Kad se implementira package sistem, ovo vezati za Tenant.package_code
LOCATION_LIMITS = {
    'free': 1,
    'starter': 3,
    'pro': 10,
    'enterprise': 999,
}

# Default paket dok se ne implementira package sistem
DEFAULT_PACKAGE = 'pro'


def can_add_location(tenant_id: int) -> dict:
    """
    Server-side provera da li tenant može dodati novu lokaciju.

    Returns:
        dict sa: allowed, current, limit, requires_upgrade
    """
    tenant = Tenant.query.get(tenant_id)
    if not tenant:
        return {'allowed': False, 'current': 0, 'limit': 0, 'requires_upgrade': True}

    current_count = ServiceLocation.query.filter_by(
        tenant_id=tenant_id, status=LocationStatus.ACTIVE
    ).count()

    package = getattr(tenant, 'package_code', None) or DEFAULT_PACKAGE
    limit = LOCATION_LIMITS.get(package, LOCATION_LIMITS[DEFAULT_PACKAGE])

    return {
        'allowed': current_count < limit,
        'current': current_count,
        'limit': limit,
        'requires_upgrade': current_count >= limit
    }


def calculate_prorate(tenant_id: int) -> dict:
    """
    Server-side prorate obračun za dodavanje lokacije usred meseca.
    Jedini izvor istine — UI samo prikazuje rezultat.

    Returns:
        dict sa: amount_rsd, amount_eur, days_remaining, daily_rate_eur
    """
    tenant = Tenant.query.get(tenant_id)
    if not tenant or not tenant.subscription_ends_at:
        return {'amount_rsd': 0, 'amount_eur': 0, 'days_remaining': 0, 'daily_rate_eur': 0}

    today = date.today()
    end = tenant.subscription_ends_at.date() if hasattr(tenant.subscription_ends_at, 'date') else tenant.subscription_ends_at
    days_remaining = (end - today).days

    if days_remaining <= 0:
        return {'amount_rsd': 0, 'amount_eur': 0, 'days_remaining': 0, 'daily_rate_eur': 0}

    # Dnevna cena iz PlatformSettings (location_price / 30)
    settings = PlatformSettings.get_settings()
    location_price_rsd = Decimal(str(settings.location_price or 1800))
    daily_rate_rsd = location_price_rsd / Decimal('30')
    amount_rsd = daily_rate_rsd * Decimal(str(days_remaining))

    # EUR konverzija (aproksimacija)
    eur_rate = Decimal('117.5')
    daily_rate_eur = daily_rate_rsd / eur_rate
    amount_eur = amount_rsd / eur_rate

    return {
        'amount_rsd': float(amount_rsd.quantize(Decimal('0.01'))),
        'amount_eur': float(amount_eur.quantize(Decimal('0.01'))),
        'days_remaining': days_remaining,
        'daily_rate_eur': float(daily_rate_eur.quantize(Decimal('0.0001')))
    }
