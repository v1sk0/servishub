# Javna Stranica Tenanta - Kompletna Dokumentacija

## Pregled

Javna Stranica (Public Site) je funkcionalnost koja omogucava svakom tenantu da ima svoju prezentacijsku web stranicu dostupnu javnosti. Stranica ukljucuje informacije o firmi, cenovnik usluga, kontakt podatke i radno vreme.

---

## Arhitektura

### URL Format

1. **Subdomena** (primarni): `{slug}.servishub.rs`
   - Primer: `mojservis.servishub.rs`
   - Automatski dostupno za sve tenante

2. **Custom Domen** (opciono): `mojservis.rs`
   - Zahteva DNS verifikaciju
   - Potreban CNAME/TXT record za potvrdu vlasnistva

### Flow Zahteva

```
Korisnik -> Request -> Middleware (detect_public_site)
                           |
                           v
                    [Cache Check]
                           |
              +------------+------------+
              |                         |
         [Cache HIT]              [Cache MISS]
              |                         |
              v                         v
       Return cached            Query Database
          tenant                       |
              |                        v
              |                  Cache result
              +------------+------------+
                           |
                           v
                    Set g.is_public_site
                    Set g.public_tenant
                    Set g.public_profile
                           |
                           v
                    Route Handler
                           |
                           v
                    Render Template
```

---

## Struktura Fajlova

```
app/
├── middleware/
│   └── public_site.py          # Middleware za detekciju subdomena/custom domena
│
├── frontend/
│   └── tenant_public.py        # Rute za javnu stranicu (HTML + API)
│
├── api/
│   └── v1/
│       └── tenant.py           # API za upravljanje public profilom (tenant admin)
│
├── models/
│   └── tenant.py               # TenantPublicProfile model
│
├── templates/
│   ├── tenant/
│   │   └── settings/
│   │       └── index.html      # Settings UI sa "Javna Stranica" tabom
│   │
│   └── public/
│       ├── base.html           # Base template za javne stranice
│       └── tenant_page.html    # Glavna javna stranica tenanta
│
└── utils/
    ├── __init__.py
    └── security.py             # Security utilities (sanitization, rate limiting)
```

---

## Database Model

### TenantPublicProfile

```python
class TenantPublicProfile(db.Model):
    """Podesavanja javne stranice tenanta."""
    __tablename__ = 'tenant_public_profile'

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey('tenant.id', ondelete='CASCADE'),
                      nullable=False, unique=True, index=True)

    # Vidljivost
    is_public = Column(Boolean, default=False)

    # Osnovni podaci
    display_name = Column(String(200))          # Override tenant.name
    tagline = Column(String(300))               # Kratki slogan
    about_content = Column(Text)                # HTML sadrzaj o firmi

    # Kontakt
    phone = Column(String(50))
    email = Column(String(100))
    address = Column(String(300))
    city = Column(String(100))
    maps_url = Column(String(500))              # Google Maps embed

    # Radno vreme (JSON format)
    working_hours = Column(JSON, default=dict)
    # Format: {"mon": {"open": "09:00", "close": "18:00", "closed": false}, ...}

    # Branding
    logo_url = Column(String(500))              # Cloudinary URL
    cover_image_url = Column(String(500))
    primary_color = Column(String(7), default='#3b82f6')
    secondary_color = Column(String(7), default='#1e40af')

    # Social linkovi
    facebook_url = Column(String(300))
    instagram_url = Column(String(300))
    twitter_url = Column(String(300))
    linkedin_url = Column(String(300))
    youtube_url = Column(String(300))
    website_url = Column(String(300))

    # Cenovnik
    show_prices = Column(Boolean, default=True)
    price_disclaimer = Column(String(500),
        default='Cene su okvirne i podlozne promenama nakon dijagnostike.')

    # SEO
    meta_title = Column(String(100))
    meta_description = Column(String(300))

    # Custom domen
    custom_domain = Column(String(255), unique=True, index=True)
    custom_domain_verified = Column(Boolean, default=False)
    domain_verification_token = Column(String(64))

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
```

### Indeksi i Constraints

- `tenant_id` - UNIQUE, INDEX (jedan profil po tenantu)
- `custom_domain` - UNIQUE, INDEX (za brzu pretragu po domenu)
- Cascade delete: brisanje tenanta automatski brise public profile

---

## API Endpoints

### Tenant Admin API (Autentifikovano)

| Method | Endpoint | Opis |
|--------|----------|------|
| GET | `/api/v1/tenant/public-profile` | Dohvati public profile |
| PUT | `/api/v1/tenant/public-profile` | Azuriraj public profile |
| POST | `/api/v1/tenant/public-profile/logo` | Upload logo (Cloudinary) |
| POST | `/api/v1/tenant/public-profile/cover` | Upload cover image |
| GET | `/api/v1/tenant/public-profile/qrcode` | Generiši QR kod za URL |
| POST | `/api/v1/tenant/public-profile/domain/setup` | Postavi custom domen |
| POST | `/api/v1/tenant/public-profile/domain/verify` | Verifikuj DNS |
| DELETE | `/api/v1/tenant/public-profile/domain` | Ukloni custom domen |

### Public API (Bez Autentifikacije)

| Method | Endpoint | Opis | Rate Limit |
|--------|----------|------|------------|
| GET | `/{slug}.servishub.rs/` | HTML stranica | - |
| GET | `/{slug}.servishub.rs/api/info` | JSON podaci | 60 req/min |
| GET | `/{slug}.servishub.rs/api/services` | Lista usluga | 60 req/min |

### Primer Response-a: `/api/info`

```json
{
  "name": "Moj Servis",
  "slug": "mojservis",
  "tagline": "Profesionalna popravka telefona",
  "about_content": "<p>Opis firme...</p>",
  "contact": {
    "phone": "+381 11 123 4567",
    "email": "info@mojservis.rs",
    "address": "Beogradska 123",
    "city": "Beograd",
    "maps_url": "https://maps.google.com/..."
  },
  "working_hours": {
    "mon": {"open": "09:00", "close": "18:00", "closed": false},
    "tue": {"open": "09:00", "close": "18:00", "closed": false},
    "wed": {"open": "09:00", "close": "18:00", "closed": false},
    "thu": {"open": "09:00", "close": "18:00", "closed": false},
    "fri": {"open": "09:00", "close": "17:00", "closed": false},
    "sat": {"open": "09:00", "close": "14:00", "closed": false},
    "sun": {"open": null, "close": null, "closed": true}
  },
  "branding": {
    "logo_url": "https://cloudinary.com/...",
    "cover_image_url": "https://cloudinary.com/...",
    "primary_color": "#3b82f6",
    "secondary_color": "#1e40af"
  },
  "social": {
    "facebook": "https://facebook.com/mojservis",
    "instagram": "https://instagram.com/mojservis",
    "website": "https://mojservis.rs"
  },
  "services": [...],
  "price_disclaimer": "Cene su okvirne..."
}
```

---

## Security

### 1. HTML Sanitization (XSS Prevention)

**Lokacija:** `app/utils/security.py`

```python
ALLOWED_TAGS = {
    'p', 'br', 'strong', 'b', 'em', 'i', 'u', 'ul', 'ol', 'li',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'a', 'span'
}

DANGEROUS_PATTERNS = [
    r'javascript:', r'vbscript:', r'data:text/html',
    r'on\w+\s*=',  # onclick, onload, etc.
    r'<script', r'</script', r'<iframe', r'<object',
    r'<embed', r'<form', r'<input', r'<base', r'<link',
    r'<meta', r'<style',
]

def sanitize_html(html_content: str) -> str:
    """Uklanja opasne HTML tagove i atribute."""
    # 1. Ukloni opasne pattern-e (javascript:, onclick=, itd.)
    # 2. Ukloni script i style blokove
    # 3. Escape nedozvoljene tagove
    # 4. Sacuvaj dozvoljene tagove bez opasnih atributa
```

**Primena:** Polja `about_content` i `description` se sanitizuju pre cuvanja.

### 2. URL Validation

```python
def sanitize_url(url: str) -> str:
    """Validira URL - dozvoljava samo http:// i https://"""
    dangerous_protocols = ['javascript:', 'vbscript:', 'data:', 'file:']
    # Vraca prazan string ako je URL opasan
```

**Primena:** Sva URL polja (logo_url, social linkovi, maps_url, itd.)

### 3. Hex Color Validation

```python
def validate_hex_color(color: str) -> str:
    """Validira hex boju, vraca default ako nije validna."""
    if re.match(r'^#[0-9a-fA-F]{6}$', color):
        return color.lower()
    return '#3b82f6'  # Default plava
```

### 4. Rate Limiting

```python
class RateLimiter:
    """In-memory rate limiter za API endpointe."""

    def is_allowed(self, key: str, limit: int = 60, window: int = 60) -> bool:
        """Proverava da li je request dozvoljen."""

@rate_limit(limit=60, window=60)
def api_info():
    """60 zahteva po minutu po IP adresi."""
```

**Primena:** Svi public API endpointi

### 5. Reserved Subdomains

```python
RESERVED_SUBDOMAINS = {
    'www', 'app', 'api', 'admin', 'mail', 'smtp', 'ftp',
    'cdn', 'static', 'assets', 'img', 'images', 'js', 'css',
    'staging', 'dev', 'test', 'demo', 'beta', 'alpha',
    'docs', 'help', 'support', 'status', 'blog', 'news',
    'dashboard', 'panel', 'portal', 'login', 'register', 'signup'
}
```

**Svrha:** Sprecava tenant da koristi subdomen koji bi mogao da se zloupotrebi.

### 6. Custom Domain DNS Verification

```python
def verify_custom_domain_dns(domain: str, verification_token: str) -> dict:
    """
    Verifikuje DNS postavke:
    1. CNAME: _servishub-verify.{domain} -> {token}.verify.servishub.rs
       ILI
       TXT: _servishub-verify.{domain} -> servishub-verify={token}
    2. CNAME: {domain} -> proxy.servishub.rs (za routing)
    """
```

**Svrha:** Dokazuje vlasnistvo nad domenom pre aktivacije.

---

## Performance

### 1. In-Memory Caching

**Lokacija:** `app/middleware/public_site.py`

```python
_cache = {}
_cache_lock = Lock()
_cache_ttl = 300  # 5 minuta

def _get_cached(key: str):
    """Dohvata vrednost iz kesa ako nije istekla."""

def _set_cached(key: str, value):
    """Cuva vrednost u kesu sa TTL-om."""

def invalidate_public_site_cache(tenant_id=None, slug=None, domain=None):
    """Invalidira kes kada se profil azurira."""
```

**Cache Keys:**
- `subdomain:{slug}` - za subdomen lookup
- `custom_domain:{domain}` - za custom domen lookup

**TTL:** 5 minuta - balans izmedju performansi i svezine podataka

### 2. Database Indexes

- `tenant_public_profile.tenant_id` - INDEX
- `tenant_public_profile.custom_domain` - INDEX
- `tenant.slug` - INDEX (postojeci)

### 3. Eager Loading

```python
# U rutama se koristi joinedload za related objekte
profile = TenantPublicProfile.query.options(
    joinedload(TenantPublicProfile.tenant)
).filter_by(...).first()
```

---

## DNS Konfiguracija

### Za Subdomen (Automatski)

Nema potrebe za konfiguracijom od strane tenanta. Wildcard DNS je konfigurisan:

```
*.servishub.rs  CNAME  servishub.herokuapp.com
```

### Za Custom Domen

Tenant mora da postavi dva DNS recorda:

#### 1. Verifikacioni Record (TXT ili CNAME)

**Opcija A - TXT Record:**
```
Host: _servishub-verify.mojservis.rs
Type: TXT
Value: servishub-verify={verification_token}
```

**Opcija B - CNAME Record:**
```
Host: _servishub-verify.mojservis.rs
Type: CNAME
Value: {verification_token}.verify.servishub.rs
```

#### 2. Routing Record (CNAME ili A)

**CNAME (preporuceno):**
```
Host: mojservis.rs (ili @)
Type: CNAME
Value: proxy.servishub.rs
```

**A Record (alternativa):**
```
Host: mojservis.rs (ili @)
Type: A
Value: {IP adresa servishub proxy-ja}
```

### Verifikacija

1. Tenant unosi domen u Settings
2. Sistem generiše `verification_token` (64 karaktera hex)
3. Tenant postavlja DNS record
4. Tenant klikne "Verifikuj"
5. Sistem proverava DNS (koristeci dnspython)
6. Ako je uspesno, `custom_domain_verified = True`

---

## Frontend Settings UI

### Lokacija

`app/templates/tenant/settings/index.html`

### Tab: "Javna Stranica"

#### Sub-tabovi:

1. **Osnovni podaci**
   - Toggle: is_public (ukljuci/iskljuci javnu stranicu)
   - display_name
   - tagline
   - about_content (rich text editor - buduci plan)

2. **Kontakt**
   - phone
   - email
   - address
   - city
   - maps_url

3. **Radno vreme**
   - 7 dana (pon-ned)
   - Za svaki dan: open time, close time, closed checkbox

4. **Branding**
   - logo_url (sa preview)
   - cover_image_url (sa preview)
   - primary_color (color picker)
   - secondary_color (color picker)

5. **Drustvene mreze**
   - facebook_url
   - instagram_url
   - twitter_url
   - linkedin_url
   - youtube_url
   - website_url

6. **Cenovnik**
   - show_prices toggle
   - price_disclaimer textarea

7. **SEO**
   - meta_title
   - meta_description

8. **Custom Domen**
   - Prikaz trenutnog statusa
   - Input za novi domen
   - Dugme "Postavi domen"
   - Instrukcije za DNS
   - Dugme "Verifikuj DNS"
   - Dugme "Ukloni domen"

### Preview Sekcija

- Link ka javnoj stranici
- QR kod (generisan dinamicki)
- Dugme "Kopiraj link"

---

## JavaScript State Management

```javascript
// Alpine.js state
publicProfile: {
    is_public: false,
    display_name: '',
    tagline: '',
    about_content: '',
    phone: '',
    email: '',
    address: '',
    city: '',
    maps_url: '',
    working_hours: {
        mon: { open: '09:00', close: '18:00', closed: false },
        // ... ostali dani
    },
    logo_url: '',
    cover_image_url: '',
    primary_color: '#3b82f6',
    secondary_color: '#1e40af',
    facebook_url: '',
    instagram_url: '',
    // ... ostali social
    show_prices: true,
    price_disclaimer: '',
    meta_title: '',
    meta_description: ''
},
customDomain: {
    domain: null,
    verified: false,
    verification_instructions: null
},
tenantSlug: '',
qrCode: null
```

### Metode

```javascript
async loadPublicProfile() {
    // GET /api/v1/tenant/public-profile
}

async savePublicProfile() {
    // PUT /api/v1/tenant/public-profile
    // Sa client-side sanitizacijom
}

sanitizePublicProfile(profile) {
    // Uklanja potencijalno opasne karaktere
}

async loadQRCode() {
    // GET /api/v1/tenant/public-profile/qrcode
}

copyToClipboard(text) {
    // Kopira URL u clipboard
}

async setupDomain() {
    // POST /api/v1/tenant/public-profile/domain/setup
}

async verifyDomain() {
    // POST /api/v1/tenant/public-profile/domain/verify
}

async removeDomain() {
    // DELETE /api/v1/tenant/public-profile/domain
}
```

---

## Javna Stranica Template

### Struktura (`templates/public/tenant_page.html`)

```
+--------------------------------------------------+
|  HEADER                                          |
|  [Cover Image]                                   |
|  [Logo] [Ime Servisa]                           |
|  "Tagline..."                                    |
+--------------------------------------------------+

+--------------------------------------------------+
|  O NAMA                                          |
|  {{ about_content | safe }}                      |
+--------------------------------------------------+

+--------------------------------------------------+
|  CENOVNIK USLUGA                                 |
|  +------------+---------------+--------+         |
|  | Usluga     | Opis          | Cena   |         |
|  +------------+---------------+--------+         |
|  | Zamena...  | Profesional.. | 3000   |         |
|  | ...        | ...           | ...    |         |
|  +------------+---------------+--------+         |
|  * {{ price_disclaimer }}                        |
+--------------------------------------------------+

+-----------------------+--------------------------+
|  RADNO VREME          |  KONTAKT                 |
|  Pon: 09:00 - 18:00   |  Adresa, Grad            |
|  Uto: 09:00 - 18:00   |  Telefon                 |
|  ...                  |  Email                   |
|  Ned: Zatvoreno       |  [Google Maps]           |
+-----------------------+--------------------------+

+--------------------------------------------------+
|  FOOTER                                          |
|  [FB] [IG] [TW] [LI] [YT] [Web]                  |
|  © 2026 Ime Servisa                              |
|  Powered by ServisHub                            |
+--------------------------------------------------+
```

---

## Migracija Baze

### Kreiranje Migracije

```bash
flask db migrate -m "Add TenantPublicProfile model"
```

### Sadrzaj Migracije

```python
def upgrade():
    op.create_table('tenant_public_profile',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Integer(),
                  sa.ForeignKey('tenant.id', ondelete='CASCADE'),
                  nullable=False, unique=True),
        # ... ostale kolone
    )
    op.create_index('ix_tenant_public_profile_tenant_id',
                    'tenant_public_profile', ['tenant_id'])
    op.create_index('ix_tenant_public_profile_custom_domain',
                    'tenant_public_profile', ['custom_domain'])

def downgrade():
    op.drop_table('tenant_public_profile')
```

---

## Heroku/DNS Setup

### Heroku Domains

```bash
# Dodaj wildcard subdomen
heroku domains:add "*.servishub.rs" -a servishub

# Proveri
heroku domains -a servishub
```

### DNS Provider (servishub.rs)

```
# Wildcard za subdomene
*.servishub.rs    CNAME   servishub.herokuapp.com.

# Root domen
servishub.rs      A       <Heroku IP>
                  ALIAS   servishub.herokuapp.com.

# www redirect
www.servishub.rs  CNAME   servishub.herokuapp.com.
```

---

## Testiranje

### Unit Tests

```python
def test_extract_subdomain():
    assert extract_subdomain('mojservis.servishub.rs') == 'mojservis'
    assert extract_subdomain('www.servishub.rs') == None  # reserved
    assert extract_subdomain('servishub.rs') == None

def test_sanitize_html():
    assert '<script>' not in sanitize_html('<script>alert(1)</script>')
    assert 'onclick' not in sanitize_html('<a onclick="alert(1)">link</a>')

def test_rate_limiter():
    limiter = RateLimiter()
    for i in range(60):
        assert limiter.is_allowed('test', limit=60, window=60)
    assert not limiter.is_allowed('test', limit=60, window=60)  # 61st blocked
```

### Integration Tests

1. Kreiraj tenant sa public profile
2. Pristupi `{slug}.servishub.rs`
3. Verifikuj da se prikazuju ispravni podaci
4. Testiraj rate limiting sa 61+ zahteva

### Manual Testing

1. Ukljuci javnu stranicu u Settings
2. Otvori `{slug}.servishub.local:5000` (lokalno)
3. Proveri sve sekcije
4. Testiraj custom domen flow (DNS verifikacija)

---

## Buduci Razvoj

### Planirane Funkcionalnosti

1. **Rich Text Editor** za about_content (TinyMCE/Quill)
2. **Image Upload** direktno na Cloudinary
3. **Analytics** - broj poseta javnoj stranici
4. **Kontakt Forma** - direktno slanje upita
5. **Rezervacija Termina** - online zakazivanje
6. **Multi-language** - podrska za vise jezika
7. **Custom CSS** - napredna customizacija

### Performance Improvements

1. **Redis Cache** umesto in-memory (za scale)
2. **CDN** za staticke resurse
3. **Edge Caching** za javne stranice

---

## Changelog

### v1.2.0 (2026-01-19)

**Infrastructure - Wildcard Subdomain Setup:**

**Heroku Configuration:**
- Dodata wildcard domena `*.servishub.rs` na Heroku app `servicehubdolce`
- DNS Target: `shallow-chinchilla-m9h0ogbc3nyistsb36tddywe.herokudns.com`
- ACM (Automated Certificate Management) automatski generise SSL sertifikate

**Cloudflare DNS:**
- Dodat CNAME zapis: `*` → `shallow-chinchilla-m9h0ogbc3nyistsb36tddywe.herokudns.com`
- Proxy status: OFF (DNS only) - potrebno za Heroku ACM

**Kompletna DNS konfiguracija:**
| Domain | Type | Target |
|--------|------|--------|
| `servishub.rs` | ALIAS | systematic-bean-o5pcn7cxkt3ofr6msd32sj80.herokudns.com |
| `www.servishub.rs` | CNAME | calm-mamenchisaurus-uosuol1jv84vyexgkjhcxsln.herokudns.com |
| `*.servishub.rs` | CNAME | shallow-chinchilla-m9h0ogbc3nyistsb36tddywe.herokudns.com |

**Bug Fix - savePublicProfile():**
- Eksplicitna konverzija `working_hours` u API format PRE sanitizacije
- `sanitizePublicProfile()` sada detektuje da li je vec konvertovano (proverava `_closed` kljuceve)
- Resava Pydantic validation error pri toggle-ovanju `is_public`

**Izmenjeni fajlovi:**
- `app/templates/tenant/settings/index.html` - `savePublicProfile()` eksplicitna konverzija

---

### v1.1.0 (2026-01-19)

**Bug Fixes:**
- **Route Deduplication:** Objedinjena `/` ruta u `public.py` - resava konflikt izmedju main landing-a i tenant public home stranice
- **Working Hours Format:** Dodata `formatWorkingHoursForApi()` funkcija koja konvertuje format iz settings forme (`mon_open`, `mon_close`, `mon_closed`) u API format (`mon: "09:00-17:00"`)
- **SQLAlchemy JSON Fields:** Dodat `flag_modified()` za JSON polja (`working_hours`, `why_us_items`, `gallery_images`, `testimonials`) radi pravilnog detektovanja promena

**Izmenjeni fajlovi:**
- `app/frontend/public.py` - Landing ruta sada detektuje `g.is_public_site` i prikazuje odgovarajuci template
- `app/frontend/tenant_public.py` - Uklonjena duplikat `/` ruta (objedinjena u public.py)
- `app/templates/tenant/settings/index.html` - Dodata `formatWorkingHoursForApi()` i azurirana `sanitizePublicProfile()`
- `app/api/v1/tenant.py` - Dodat `flag_modified()` za JSON polja

### v1.0.0 (2026-01-18)

- Initial implementation
- Subdomain routing
- Custom domain support with DNS verification
- Security: HTML sanitization, URL validation, rate limiting
- Performance: In-memory caching
- Settings UI with 8 sub-tabs
- QR code generation
- Public API endpoints

---

## Working Hours Format

### Settings Forma (Frontend)

```javascript
// Novi format za form binding
working_hours: {
    mon_open: '09:00',
    mon_close: '17:00',
    mon_closed: false,
    tue_open: '09:00',
    tue_close: '17:00',
    tue_closed: false,
    // ... ostali dani
    sun_open: '',
    sun_close: '',
    sun_closed: true
}
```

### API/Database Format

```javascript
// Format koji se cuva u bazi i koristi u template-ima
working_hours: {
    mon: '09:00-17:00',
    tue: '09:00-17:00',
    wed: '09:00-17:00',
    thu: '09:00-17:00',
    fri: '09:00-17:00',
    sat: '09:00-14:00',
    sun: 'Zatvoreno'
}
```

### Konverzija

**Frontend -> API:** `formatWorkingHoursForApi()` u settings/index.html
**API -> Frontend:** `parseWorkingHours()` u settings/index.html

---

## Kontakt

Za pitanja o implementaciji, kontaktirajte razvojni tim.