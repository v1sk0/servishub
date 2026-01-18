# Security Implementation - ServisHub

## Pregled

Ovaj dokument opisuje sve sigurnosne mere implementirane u ServisHub aplikaciji, sa fokusom na Javnu Stranicu (Public Site) funkcionalnost.

---

## 1. Input Validacija i Sanitizacija

### 1.1 HTML Sanitizacija (XSS Prevention)

**Lokacija:** `app/utils/security.py`

**Problem:** Korisnici mogu uneti maliciozni HTML/JavaScript kod kroz polja kao sto je `about_content`.

**Resenje:**

```python
ALLOWED_TAGS = {
    'p', 'br', 'strong', 'b', 'em', 'i', 'u', 'ul', 'ol', 'li',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'a', 'span'
}

DANGEROUS_PATTERNS = [
    r'javascript:',        # javascript: URLs
    r'vbscript:',          # vbscript: URLs
    r'data:text/html',     # data: URLs sa HTML-om
    r'on\w+\s*=',          # Event handlers (onclick, onload, onerror, etc.)
    r'<script',            # Script tagovi
    r'</script',
    r'<iframe',            # iframe injection
    r'<object',            # Object/embed tags
    r'<embed',
    r'<form',              # Form injection
    r'<input',
    r'<base',              # Base URL manipulation
    r'<link',              # External resource loading
    r'<meta',              # Meta tag manipulation
    r'<style',             # CSS injection
]

def sanitize_html(html_content: str) -> str:
    """
    Sanitizuje HTML sadrzaj:
    1. Uklanja sve pattern-e iz DANGEROUS_PATTERNS
    2. Uklanja <script> i <style> blokove kompletno
    3. Za dozvoljene tagove, uklanja opasne atribute (onclick, style)
    4. Za nedozvoljene tagove, escape-uje ih
    """
```

**Gde se primenjuje:**
- `about_content` polje u TenantPublicProfile
- `description` polja (ako postoji rich text)
- Bilo koji korisnicki unos koji se prikazuje sa `| safe` filterom

### 1.2 URL Validacija

**Problem:** Maliciozni URL-ovi mogu izvrsiti JavaScript ili preusmeriti korisnike.

**Resenje:**

```python
def sanitize_url(url: str) -> str:
    """
    Validira URL:
    1. Uklanja dangerous protocols (javascript:, vbscript:, data:, file:)
    2. Dozvoljava samo http:// i https://
    3. Automatski dodaje https:// ako nema protokol
    """
    dangerous_protocols = ['javascript:', 'vbscript:', 'data:', 'file:']
```

**Gde se primenjuje:**
- `logo_url`, `cover_image_url`
- `facebook_url`, `instagram_url`, `twitter_url`, `linkedin_url`, `youtube_url`, `website_url`
- `maps_url`

### 1.3 Hex Color Validacija

**Problem:** CSS injection kroz color vrednosti.

**Resenje:**

```python
def validate_hex_color(color: str) -> str:
    """
    Validira hex boju:
    1. Proverava format #RRGGBB (6 hex cifara)
    2. Vraca default #3b82f6 ako nije validan format
    """
    if re.match(r'^#[0-9a-fA-F]{6}$', color):
        return color.lower()
    return '#3b82f6'
```

**Gde se primenjuje:**
- `primary_color`, `secondary_color`

### 1.4 Domain Validacija

**Problem:** Invalid domain format ili zloupoteba servishub domena.

**Resenje:**

```python
def validate_domain(domain: str) -> bool:
    """
    Validira format domena:
    1. Max 255 karaktera
    2. Regex: ^[a-z0-9]([a-z0-9-]*[a-z0-9])?(.[a-z0-9]...)*.[a-z]{2,}$
    3. Uklanja http://, https://, www. prefixe
    """
```

**Dodatna provera u API:**
- Domen ne sme sadrzati "servishub"
- Domen ne sme vec biti u upotrebi

---

## 2. Rate Limiting

### 2.1 In-Memory Rate Limiter

**Lokacija:** `app/utils/security.py`

**Problem:** API abuse, DDoS napadi, brute-force napadi.

**Resenje:**

```python
class RateLimiter:
    """
    In-memory rate limiter sa sliding window algoritmom.

    Features:
    - Prati zahteve po kljucu (IP + endpoint)
    - Automatsko ciscenje starih zapisa
    - Thread-safe
    """

    def is_allowed(self, key: str, limit: int = 60, window: int = 60) -> bool:
        """
        Proverava da li je zahtev dozvoljen.
        Default: 60 zahteva po minutu
        """
```

**Decorator za rute:**

```python
@rate_limit(limit=60, window=60)
def api_endpoint():
    """Ograniceno na 60 req/min"""
```

### 2.2 Rate Limit Konfiguracija

| Endpoint Tip | Limit | Window | Key |
|--------------|-------|--------|-----|
| Public API | 60 req | 60 sec | IP + endpoint |
| Auth API | 120 req | 60 sec | IP + endpoint |
| Upload | 10 req | 60 sec | IP + tenant_id |
| DNS Verify | 5 req | 60 sec | tenant_id |

### 2.3 Response na Rate Limit

```json
HTTP 429 Too Many Requests

{
  "error": "Too many requests. Please try again later."
}
```

---

## 3. Subdomain Security

### 3.1 Reserved Subdomains

**Lokacija:** `app/middleware/public_site.py`

**Problem:** Tenant moze pokusati da registruje subdomenu koja imitira sistemske stranice.

**Resenje:**

```python
RESERVED_SUBDOMAINS = {
    # Web infrastruktura
    'www', 'app', 'api', 'admin', 'mail', 'smtp', 'ftp',

    # CDN i staticke resurse
    'cdn', 'static', 'assets', 'img', 'images', 'js', 'css',

    # Okruzenja
    'staging', 'dev', 'test', 'demo', 'beta', 'alpha',

    # Sistemske stranice
    'docs', 'help', 'support', 'status', 'blog', 'news',

    # Auth stranice
    'dashboard', 'panel', 'portal', 'login', 'register', 'signup'
}
```

**Provera:**
```python
def extract_subdomain(host: str) -> str | None:
    # ...
    if subdomain not in RESERVED_SUBDOMAINS:
        return subdomain
    return None
```

### 3.2 Platform Domains

**Problem:** Detekcija da li je request za platformu ili za tenant.

**Resenje:**

```python
PLATFORM_DOMAINS = {
    'servishub.rs',
    'servishub.com',
    'servishub.local',  # Development
}
```

---

## 4. Custom Domain Security

### 4.1 DNS Verification Flow

**Problem:** Tenant pokusava da koristi domen koji mu ne pripada.

**Resenje - Dvostepena verifikacija:**

1. **Verifikacioni record** - dokazuje vlasnistvo
2. **Routing record** - usmerava saobracaj

```python
def verify_custom_domain_dns(domain: str, verification_token: str) -> dict:
    """
    Proverava:
    1. TXT record: _servishub-verify.{domain} = servishub-verify={token}
       ILI
       CNAME: _servishub-verify.{domain} -> {token}.verify.servishub.rs

    2. CNAME: {domain} -> proxy.servishub.rs
       ILI
       A record koji pokazuje na nas proxy
    """
```

### 4.2 Verification Token

```python
# Generisanje tokena
import secrets
verification_token = secrets.token_hex(32)  # 64 karaktera
```

**Osobine:**
- Kriptografski siguran random
- 256 bita entropije
- Jedinstven po tenant/domain kombinaciji

### 4.3 DNS Lookup Security

**Koriscena biblioteka:** `dnspython`

```python
import dns.resolver
import dns.exception

# Timeout i retry konfiguracija
resolver = dns.resolver.Resolver()
resolver.timeout = 5
resolver.lifetime = 10
```

---

## 5. Authentication & Authorization

### 5.1 JWT Tokens

**Provera u middleware:**
```python
@require_auth
def protected_endpoint():
    # Samo autentifikovani korisnici
```

### 5.2 Tenant Isolation

**Problem:** Tenant A ne sme da pristupi podacima Tenant B.

**Resenje:**

```python
# U svakom API endpoint-u
profile = TenantPublicProfile.query.filter_by(
    tenant_id=g.current_tenant.id  # Uvek filtrirati po current_tenant
).first()
```

### 5.3 Public Site Access Control

```python
def require_public_site(f):
    """Decorator koji zahteva da je request za javnu stranicu."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not g.is_public_site or not g.public_tenant:
            abort(404)
        return f(*args, **kwargs)
    return decorated
```

---

## 6. Content Security

### 6.1 Template Escaping

**Default behavior u Jinja2:**
- Sav sadrzaj je automatski escaped
- `{{ variable }}` - escaped
- `{{ variable | safe }}` - neescaped (koristi samo za sanitizovan sadrzaj!)

**Gde se koristi `| safe`:**
- `about_content` - MORA biti prethodno sanitizovano!

### 6.2 Image Upload Security

**Validacija:**
```python
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

def validate_image(file):
    # 1. Proveri ekstenziju
    # 2. Proveri MIME type
    # 3. Proveri velicinu
    # 4. Opciono: proveri magic bytes
```

**Upload destinacija:**
- Cloudinary (eksterni servis)
- Nikada lokalno na server

---

## 7. Caching Security

### 7.1 Cache Key Design

```python
# Kljuc ukljucuje sve relevantne parametre
cache_key = f'subdomain:{subdomain}'
cache_key = f'custom_domain:{domain}'
```

**Nema user-specific podataka u cache-u** - public stranice su iste za sve posetioce.

### 7.2 Cache Invalidation

```python
def invalidate_public_site_cache(tenant_id=None, slug=None, domain=None):
    """
    Invalidira cache kada se profil azurira.
    Poziva se iz API endpoint-a nakon UPDATE operacija.
    """
```

### 7.3 Cache Poisoning Prevention

- Cache kljucevi su internog formata (ne dolaze od korisnika)
- TTL ogranicenje (5 minuta)
- Thread-safe operacije sa Lock()

---

## 8. Error Handling

### 8.1 Error Message Security

**NE otkrivaj:**
- Detalje o infrastrukturi
- Stack trace u produkciji
- Tacne razloge odbijanja

**Primer:**
```python
# Lose
return {'error': 'User darko@example.com not found in database tenant_5'}

# Dobro
return {'error': 'Not found'}, 404
```

### 8.2 Logging

```python
import logging

# Loguj sigurnosne dogadjaje
logger.warning(f'Rate limit exceeded for IP {ip}')
logger.warning(f'Invalid domain verification attempt: {domain}')
```

---

## 9. Security Headers

### 9.1 Preporuceni Headers

```python
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = "default-src 'self'"
    return response
```

### 9.2 CORS za Public API

```python
# Dozvoli pristup sa bilo kog origina za public API
# Ali samo za GET metode
@app.after_request
def add_cors_headers(response):
    if request.path.startswith('/api/public') or g.get('is_public_site'):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    return response
```

---

## 10. Dependency Security

### 10.1 Koriscene Biblioteke

| Biblioteka | Verzija | Svrha | Security Napomene |
|------------|---------|-------|-------------------|
| Flask | 3.x | Web framework | Redovno azurirati |
| SQLAlchemy | 2.x | ORM | Koristi parameterized queries |
| dnspython | 2.4.x | DNS lookup | Timeout konfigurisan |
| bleach | (ako se koristi) | HTML sanitization | Alternativa nasoj implementaciji |

### 10.2 Preporuke

1. Redovno pokretati `pip audit` ili `safety check`
2. Azurirati dependencies mesecno
3. Pratiti security advisories

---

## 11. Security Checklist

### Pre Deploymenta

- [ ] Sve URL-ove validirati sa `sanitize_url()`
- [ ] HTML sadrzaj sanitizovati sa `sanitize_html()`
- [ ] Hex boje validirati sa `validate_hex_color()`
- [ ] Public API endpoint-i imaju rate limiting
- [ ] Tenant isolation proveren u svim query-jima
- [ ] Error poruke ne otkrivaju osetljive informacije
- [ ] Cache invalidation implementiran

### Periodicne Provere

- [ ] Pregled logova za sumnjive aktivnosti
- [ ] Provera dependency vulnerabilities
- [ ] Penetration testing (godisnje)
- [ ] Code review za security-critical promene

---

## 12. Incident Response

### U slucaju Security Incidenta

1. **Izolacija** - Onemoguciti pogodjen endpoint/funkcionalnost
2. **Analiza** - Pregled logova, identifikacija uzroka
3. **Popravka** - Implementacija fix-a
4. **Notifikacija** - Obavestiti pogodene korisnike (ako je potrebno)
5. **Post-mortem** - Dokumentovati i unaprediti

### Kontakt

Za prijavu sigurnosnih problema: security@servishub.rs

---

## Verzije

| Verzija | Datum | Opis |
|---------|-------|------|
| 1.0 | 2026-01-18 | Inicijalna dokumentacija |