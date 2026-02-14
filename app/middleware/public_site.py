"""
Public Site Middleware - detekcija subdomena i custom domena.

Ovaj middleware detektuje da li je request za javnu stranicu tenanta:
1. Subdomena: {slug}.shub.rs
2. Custom domen: mojservis.rs (ako je verifikovan)

Postavlja g.public_tenant i g.is_public_site za korišćenje u rutama.

Security:
- Reserved subdomains prevent tenant subdomain hijacking
- Custom domains require DNS verification before activation
- Only profiles with is_public=True are served

Performance:
- Simple in-memory cache for tenant/profile lookups
- Cache invalidated on profile updates
- TTL: 5 minutes for performance, short enough for quick updates
"""

from flask import request, g
from app.models import Tenant, TenantPublicProfile
from datetime import datetime, timedelta
from threading import Lock


# ============================================
# CACHING LAYER
# ============================================

# Simple in-memory cache for tenant lookups
_cache = {}
_cache_lock = Lock()
_cache_ttl = 300  # 5 minutes


def _get_cached(key: str):
    """Get value from cache if not expired."""
    with _cache_lock:
        if key in _cache:
            value, expires_at = _cache[key]
            if datetime.utcnow() < expires_at:
                return value
            else:
                del _cache[key]
    return None


def _set_cached(key: str, value):
    """Set value in cache with TTL."""
    with _cache_lock:
        _cache[key] = (value, datetime.utcnow() + timedelta(seconds=_cache_ttl))


def invalidate_public_site_cache(tenant_id: int = None, slug: str = None, domain: str = None):
    """
    Invalidate cache entries for a tenant.

    Call this when updating TenantPublicProfile.

    Args:
        tenant_id: Tenant ID to invalidate
        slug: Tenant slug to invalidate
        domain: Custom domain to invalidate
    """
    with _cache_lock:
        to_remove = []
        if tenant_id:
            for key, (value, _) in list(_cache.items()):
                if isinstance(value, tuple) and len(value) == 2:
                    tenant, profile = value
                    if tenant and tenant.id == tenant_id:
                        to_remove.append(key)
        if slug:
            key = f'subdomain:{slug}'
            if key in _cache:
                to_remove.append(key)
        if domain:
            key = f'custom_domain:{domain}'
            if key in _cache:
                to_remove.append(key)

        for key in set(to_remove):
            if key in _cache:
                del _cache[key]


# ============================================
# DOMAIN CONFIGURATION
# ============================================

# Domeni koji se ne tretiraju kao subdomena tenanta
RESERVED_SUBDOMAINS = {
    'www', 'app', 'api', 'admin', 'mail', 'smtp', 'ftp',
    'cdn', 'static', 'assets', 'img', 'images', 'js', 'css',
    'staging', 'dev', 'test', 'demo', 'beta', 'alpha',
    'docs', 'help', 'support', 'status', 'blog', 'news',
    'dashboard', 'panel', 'portal', 'login', 'register', 'signup'
}

# Glavni domeni platforme
PLATFORM_DOMAINS = {
    'shub.rs',
    'shub.local',  # Lokalni development
}


# ============================================
# DOMAIN EXTRACTION
# ============================================

def extract_subdomain(host: str) -> str | None:
    """
    Izvlači subdomen iz host headera.

    Args:
        host: Host header (npr. "mojservis.shub.rs")

    Returns:
        Subdomen string ili None ako nije subdomena
    """
    host = host.lower().split(':')[0]  # Ukloni port

    # Proveri za svaki platformski domen
    for platform_domain in PLATFORM_DOMAINS:
        if host.endswith(f'.{platform_domain}'):
            subdomain = host.replace(f'.{platform_domain}', '')
            # Proveri da nije rezervisana subdomena
            if subdomain and subdomain not in RESERVED_SUBDOMAINS:
                return subdomain

    return None


def extract_custom_domain(host: str) -> str | None:
    """
    Proverava da li je host custom domen tenanta.

    Args:
        host: Host header (npr. "mojservis.rs")

    Returns:
        Custom domen string ili None
    """
    host = host.lower().split(':')[0]  # Ukloni port

    # Ako je platformski domen, nije custom
    for platform_domain in PLATFORM_DOMAINS:
        if host == platform_domain or host.endswith(f'.{platform_domain}'):
            return None

    # Ignoriši localhost i IP adrese
    if 'localhost' in host or '127.0.0.1' in host or host.replace('.', '').isdigit():
        return None

    return host


# ============================================
# TENANT LOOKUP
# ============================================

def find_tenant_by_subdomain(subdomain: str) -> tuple:
    """
    Pronalazi tenant po subdomenu (slug).

    Uses caching for performance.

    Returns:
        Tuple (Tenant, TenantPublicProfile) ili (None, None)
    """
    cache_key = f'subdomain:{subdomain}'

    # Check cache first
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    # Query database
    tenant = Tenant.query.filter_by(slug=subdomain).first()
    if not tenant:
        _set_cached(cache_key, (None, None))
        return None, None

    profile = TenantPublicProfile.query.filter_by(tenant_id=tenant.id).first()
    result = (tenant, profile)

    _set_cached(cache_key, result)
    return result


def find_tenant_by_custom_domain(domain: str) -> tuple:
    """
    Pronalazi tenant po custom domenu.

    Uses caching for performance.

    Returns:
        Tuple (Tenant, TenantPublicProfile) ili (None, None)
    """
    cache_key = f'custom_domain:{domain}'

    # Check cache first
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    # Query database
    profile = TenantPublicProfile.query.filter_by(
        custom_domain=domain,
        custom_domain_verified=True
    ).first()

    if not profile:
        _set_cached(cache_key, (None, None))
        return None, None

    result = (profile.tenant, profile)
    _set_cached(cache_key, result)
    return result


# ============================================
# MIDDLEWARE SETUP
# ============================================

def setup_public_site_middleware(app):
    """
    Registruje middleware koji detektuje public site requests.

    Middleware postavlja:
    - g.is_public_site: bool - da li je request za javnu stranicu
    - g.public_tenant: Tenant - tenant čija je javna stranica
    - g.public_profile: TenantPublicProfile - profil javne stranice
    - g.public_domain_type: str - 'subdomain' ili 'custom_domain'
    """

    @app.before_request
    def detect_public_site():
        """Detektuje da li je request za javnu stranicu tenanta."""
        # Reset vrednosti
        g.is_public_site = False
        g.public_tenant = None
        g.public_profile = None
        g.public_domain_type = None

        # Dohvati host
        host = request.host.lower()

        # Prvo probaj custom domen
        custom_domain = extract_custom_domain(host)
        if custom_domain:
            tenant, profile = find_tenant_by_custom_domain(custom_domain)
            if tenant and profile and profile.is_public:
                g.is_public_site = True
                g.public_tenant = tenant
                g.public_profile = profile
                g.public_domain_type = 'custom_domain'
                return

        # Zatim probaj subdomenu
        subdomain = extract_subdomain(host)
        if subdomain:
            tenant, profile = find_tenant_by_subdomain(subdomain)
            if tenant and profile and profile.is_public:
                g.is_public_site = True
                g.public_tenant = tenant
                g.public_profile = profile
                g.public_domain_type = 'subdomain'
                return


# ============================================
# DNS VERIFICATION
# ============================================

def verify_custom_domain_dns(domain: str, verification_token: str, heroku_target: str = None) -> dict:
    """
    Verifikuje DNS postavke za custom domen.

    Proverava:
    1. CNAME record: _shub-verify.{domain} -> {token}.verify.shub.rs
    2. TXT record: _shub-verify.{domain} -> shub-verify={token}
    3. CNAME record: {domain} -> heroku_target ili proxy.shub.rs (za routing)

    Args:
        domain: Custom domain to verify
        verification_token: Expected verification token
        heroku_target: Heroku CNAME target (npr. "xyz.herokudns.com")

    Returns:
        Dict sa statusom verifikacije
    """
    import dns.resolver
    import dns.exception

    result = {
        'verified': False,
        'verification_record': False,
        'routing_record': False,
        'errors': []
    }

    verify_host = f'_shub-verify.{domain}'
    expected_cname = f'{verification_token}.verify.shub.rs'
    expected_txt = f'shub-verify={verification_token}'

    # Proveri CNAME verifikacioni record
    try:
        answers = dns.resolver.resolve(verify_host, 'CNAME')
        for rdata in answers:
            if str(rdata.target).rstrip('.').lower() == expected_cname.lower():
                result['verification_record'] = True
                break
    except dns.exception.DNSException:
        pass

    # Ako CNAME nije pronađen, probaj TXT
    if not result['verification_record']:
        try:
            answers = dns.resolver.resolve(verify_host, 'TXT')
            for rdata in answers:
                txt_value = str(rdata).strip('"')
                if txt_value == expected_txt:
                    result['verification_record'] = True
                    break
        except dns.exception.DNSException:
            pass

    # Proveri routing CNAME (domain -> heroku_target ili proxy.shub.rs)
    valid_targets = {'proxy.shub.rs'}
    if heroku_target:
        valid_targets.add(heroku_target.rstrip('.').lower())
    try:
        answers = dns.resolver.resolve(domain, 'CNAME')
        for rdata in answers:
            target = str(rdata.target).rstrip('.').lower()
            if target in valid_targets:
                result['routing_record'] = True
                break
    except dns.exception.DNSException:
        # Možda je A record umesto CNAME (Cloudflare proxy/flattening)
        try:
            answers = dns.resolver.resolve(domain, 'A')
            # A record postoji - prihvatamo (Cloudflare CNAME flattening resolves to A)
            result['routing_record'] = True
        except dns.exception.DNSException:
            result['errors'].append('Ne mogu da pronađem DNS record za domen')

    # Finalna verifikacija
    result['verified'] = result['verification_record'] and result['routing_record']

    if not result['verification_record']:
        result['errors'].append('Verifikacioni DNS record nije pronađen ili nije ispravan')

    if not result['routing_record']:
        result['errors'].append('Routing DNS record (CNAME/A) nije pronađen')

    return result