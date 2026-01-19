# CLAUDE.md - ServisHub

Instrukcije za Claude Code agente. **CITAJ OVO PRE BILO KAKVIH IZMENA.**

---

## RESUME POINT

**v0.6.2** | 2026-01-19 | Backend 100% | Frontend 100%

### Status: KOMPLETNO - Public Site v2 (nove sekcije + poboljšanja)

**Poslednje izmene (v0.6.2):**
- **Public Site v2:** Kompletna revizija javnog sajta tenanta
  - FAQ sekcija sa accordion stilom
  - Brendovi sekcija (grid sa logotipima)
  - Proces rada sekcija (6 koraka timeline)
  - Status tracking widget
  - Floating WhatsApp dugme
  - Floating Call dugme (mobile)
  - AOS animacije na svim sekcijama
- **Contact fallback:** Kontakt podaci koriste fallback na tenant podatke
- **Settings UI:** Novi "Sekcije" tab za uređivanje FAQ, Brendova, Procesa
- **Database:** Nova migracija `o6p7q8r9s0t1_add_public_site_v2_fields.py`
- **API Fix:** Preprocessing za FormData (dict→list konverzija, prazan email)

**Prethodne izmene (v0.6.1):**
- **Heroku:** Dodata wildcard domena `*.servishub.rs`
- **Cloudflare:** CNAME zapis za wildcard → herokudns.com
- **SSL:** ACM automatski generise SSL za subdomene

**Prethodne izmene (v0.6.0):**
- Fix: Duplikat `/` rute - objedinjena logika u public.py
- Fix: Format radnog vremena (working_hours) konverzija za API
- Fix: SQLAlchemy JSON polja - flag_modified za pravilno cuvanje

Svi frontend moduli zavrseni i verifikovani:
- Tenant panel (23 stranica)
- Admin panel (10 stranica + 2 partials)
- Supplier panel (6 stranica)
- Public stranice (2 stranice)
- Layouts (3 fajla)

**Ukupno:** 53 HTML fajla (51 template + 2 admin partial)

> Azuriraj ovaj RESUME POINT nakon svake znacajne izmene!

---

## Projekat

**ServisHub** - SaaS platforma za servise mobilnih telefona.

| Stack | Tehnologija |
|-------|-------------|
| Backend | Python 3.11 + Flask 3.x + SQLAlchemy 2.0 |
| Frontend | Tailwind CSS + Alpine.js (CDN) + Jinja2 |
| Baza | PostgreSQL 15 (Heroku) |
| Auth | JWT (PyJWT) - odvojeni tokeni za tenant/admin/supplier |
| Deploy | Heroku + GitHub |

---

## Struktura

```
servishub/
├── app/
│   ├── __init__.py          # App factory
│   ├── config.py            # Konfiguracija
│   ├── extensions.py        # Flask ekstenzije
│   │
│   ├── models/              # 11 SQLAlchemy modula
│   │   ├── tenant.py        # Tenant, ServiceLocation
│   │   ├── tenant_public_profile.py # TenantPublicProfile (javna stranica)
│   │   ├── user.py          # TenantUser, UserLocation
│   │   ├── ticket.py        # ServiceTicket
│   │   ├── inventory.py     # PhoneListing, SparePart
│   │   ├── supplier.py      # Supplier, SupplierListing, SupplierUser
│   │   ├── order.py         # PartOrder, PartOrderItem, PartOrderMessage
│   │   ├── representative.py # ServiceRepresentative (KYC)
│   │   ├── admin.py         # PlatformAdmin
│   │   └── audit.py         # AuditLog
│   │
│   ├── api/                 # 115+ API ruta
│   │   ├── v1/              # Tenant API (65 ruta)
│   │   │   ├── auth.py      # login, register, refresh, me
│   │   │   ├── tenant.py    # profile, settings, subscription, kyc
│   │   │   ├── users.py     # CRUD korisnika
│   │   │   ├── locations.py # CRUD lokacija
│   │   │   ├── tickets.py   # CRUD naloga
│   │   │   ├── inventory.py # phones, parts
│   │   │   ├── marketplace.py # pretraga, brands
│   │   │   └── orders.py    # narudzbine
│   │   │
│   │   ├── admin/           # Admin API (21 ruta)
│   │   │   ├── auth.py      # admin login
│   │   │   ├── dashboard.py # statistika
│   │   │   ├── tenants.py   # upravljanje servisima
│   │   │   └── kyc.py       # KYC verifikacija
│   │   │
│   │   ├── supplier/        # Supplier API (22 rute)
│   │   │   ├── auth.py      # supplier login/register
│   │   │   ├── listings.py  # katalog
│   │   │   └── orders.py    # narudzbine
│   │   │
│   │   ├── public/          # Public API (7 ruta)
│   │   │   ├── marketplace.py # javna pretraga
│   │   │   └── tickets.py   # track nalog (QR)
│   │   │
│   │   ├── middleware/
│   │   │   ├── auth.py      # JWT dekoratori
│   │   │   └── jwt_utils.py # JWT pomocne funkcije
│   │   │
│   │   └── schemas/         # Pydantic validacija
│   │
│   ├── frontend/            # HTML rute
│   │   ├── tenant.py        # /login, /dashboard, /tickets, /inventory...
│   │   ├── admin.py         # /admin/*
│   │   ├── supplier.py      # /supplier/*
│   │   └── public.py        # /, /track
│   │
│   ├── templates/           # 51 Jinja2 template
│   │   ├── layouts/         # 3 layout-a
│   │   │   ├── base.html    # Osnovni (public, admin)
│   │   │   ├── tenant.html  # Tenant panel (plava tema)
│   │   │   └── supplier.html # Supplier panel (ljubicasta tema)
│   │   │
│   │   ├── tenant/          # 23 stranice
│   │   │   ├── login.html, register.html, dashboard.html
│   │   │   ├── tickets/ (list, new, detail, edit)
│   │   │   ├── inventory/ (phones, phones_new, parts, parts_new)
│   │   │   ├── marketplace/ (search)
│   │   │   ├── orders/ (list, detail)
│   │   │   ├── locations/ (list, new, detail)
│   │   │   ├── team/ (list, new, detail)
│   │   │   └── settings/ (index, profile, subscription, kyc)
│   │   │
│   │   ├── admin/           # 10 stranica + 2 partials
│   │   │   ├── _sidebar.html        # SHARED: navigacija za sve admin stranice
│   │   │   ├── _admin_styles.html   # SHARED: CSS teme (light/glass)
│   │   │   ├── login.html, dashboard.html
│   │   │   ├── tenants/ (list, detail)
│   │   │   ├── kyc/ (list, detail) - preimenovano: "Predstavnici"
│   │   │   ├── suppliers/ (list, detail)
│   │   │   ├── payments/ (list)
│   │   │   └── settings/ (index)
│   │   │
│   │   ├── supplier/        # 6 stranica
│   │   │   ├── login.html, register.html, dashboard.html
│   │   │   ├── catalog/ (list, new, detail)
│   │   │   ├── orders/ (list, detail)
│   │   │   └── settings.html
│   │   │
│   │   ├── public/          # 3 stranice (ServisHub landing)
│   │   │   ├── landing.html
│   │   │   ├── track.html
│   │   │   └── marketplace.html
│   │   │
│   │   └── tenant_public/   # 2 stranice (javni sajt tenanta)
│   │       ├── base.html    # Layout sa nav, footer, floating buttons
│   │       └── home.html    # Homepage sa svim sekcijama
│   │
│   ├── services/            # Business logic
│   ├── repositories/        # Data access
│   └── tasks/               # Celery (buduci rad)
│
├── migrations/              # Alembic migracije
├── docs/                    # Dokumentacija
│   ├── MASTER_SUMMARY.md    # Glavni pregled sistema
│   ├── THEME_SPECIFICATION.md # Dizajn sistem i boje
│   ├── UI_UX_PERFORMANCE.md # Performance optimizacije
│   ├── PUBLIC_SITE_DOCUMENTATION.md # Javne stranice tenanta
│   └── SECURITY_IMPLEMENTATION.md # Sigurnosne mere
├── run.py                   # Entry point
├── requirements.txt
├── Procfile                 # Heroku konfiguracija
└── .env                     # Environment varijable
```

---

## Komande

```bash
cd C:\servishub
venv\Scripts\activate
python run.py              # Dev server → localhost:5000
flask db migrate -m "..."  # Nova migracija
flask db upgrade           # Primeni migracije
flask create-admin         # Kreiraj platform admin-a
```

---

## API Struktura

| API | Prefix | Auth | Rute |
|-----|--------|------|------|
| V1 (Tenant) | /api/v1 | JWT (access_token) | 65 |
| Admin | /api/admin | JWT (admin_access_token) | 21 |
| Supplier | /api/supplier | JWT (supplier_access_token) | 22 |
| Public | /api/public | None | 7 |

**Health:** `GET /health`

---

## Frontend Stranice - Kompletna Lista

### Tenant Panel (23)
| URL | Template |
|-----|----------|
| `/login` | tenant/login.html |
| `/register` | tenant/register.html |
| `/dashboard` | tenant/dashboard.html |
| `/tickets` | tenant/tickets/list.html |
| `/tickets/new` | tenant/tickets/new.html |
| `/tickets/:id` | tenant/tickets/detail.html |
| `/tickets/:id/edit` | tenant/tickets/edit.html |
| `/inventory/phones` | tenant/inventory/phones.html |
| `/inventory/phones/new` | tenant/inventory/phones_new.html |
| `/inventory/parts` | tenant/inventory/parts.html |
| `/inventory/parts/new` | tenant/inventory/parts_new.html |
| `/marketplace` | tenant/marketplace/search.html |
| `/orders` | tenant/orders/list.html |
| `/orders/:id` | tenant/orders/detail.html |
| `/locations` | tenant/locations/list.html |
| `/locations/new` | tenant/locations/new.html |
| `/locations/:id` | tenant/locations/detail.html |
| `/team` | tenant/team/list.html |
| `/team/new` | tenant/team/new.html |
| `/team/:id` | tenant/team/detail.html |
| `/settings` | tenant/settings/index.html |
| `/settings/profile` | tenant/settings/profile.html |
| `/settings/subscription` | tenant/settings/subscription.html |
| `/settings/kyc` | tenant/settings/kyc.html |

### Admin Panel (10 stranica + 2 partials)

**Partials (shared komponente):**
| Fajl | Namena |
|------|--------|
| `_sidebar.html` | Navigacija - koristi `active_page` varijablu |
| `_admin_styles.html` | CSS teme (light/glassmorphism) |

**Stranice:**
| URL | Template | active_page |
|-----|----------|-------------|
| `/admin/login` | admin/login.html | - |
| `/admin/dashboard` | admin/dashboard.html | dashboard |
| `/admin/tenants` | admin/tenants/list.html | tenants |
| `/admin/tenants/:id` | admin/tenants/detail.html | tenants |
| `/admin/kyc` | admin/kyc/list.html | - (nije u navigaciji) |
| `/admin/kyc/:id` | admin/kyc/detail.html | - (nije u navigaciji) |
| `/admin/suppliers` | admin/suppliers/list.html | suppliers |
| `/admin/suppliers/:id` | admin/suppliers/detail.html | suppliers |
| `/admin/payments` | admin/payments/list.html | payments |
| `/admin/settings` | admin/settings/index.html | settings |

**Napomena:** KYC stranice postoje ali nisu u sidebar navigaciji - funkcionalnost se premesta u detalje servisa.

### Supplier Panel (6)
| URL | Template |
|-----|----------|
| `/supplier/login` | supplier/login.html |
| `/supplier/register` | supplier/register.html |
| `/supplier/dashboard` | supplier/dashboard.html |
| `/supplier/catalog` | supplier/catalog/list.html |
| `/supplier/catalog/new` | supplier/catalog/new.html |
| `/supplier/catalog/:id` | supplier/catalog/detail.html |
| `/supplier/orders` | supplier/orders/list.html |
| `/supplier/orders/:id` | supplier/orders/detail.html |
| `/supplier/settings` | supplier/settings.html |

### Public (2)
| URL | Template |
|-----|----------|
| `/` | public/landing.html |
| `/track/:token` | public/track.html |
| `/marketplace` | public/marketplace.html |

---

## Kriticna Pravila

### 1. Multi-Tenant Izolacija
```python
# UVEK filtriraj po tenant_id
tickets = ServiceTicket.query.filter_by(tenant_id=g.tenant_id)
# NIKADA: ServiceTicket.query.all()
```

### 2. JWT Storage (Frontend)
```javascript
// Tenant panel - MORA koristiti ove kljuceve
localStorage.getItem('access_token')
localStorage.getItem('refresh_token')

// Admin panel - ODVOJENI tokeni!
localStorage.getItem('admin_access_token')

// Supplier panel - ODVOJENI tokeni!
localStorage.getItem('supplier_access_token')
localStorage.getItem('supplier_refresh_token')
```

### 3. Template Extends
```jinja2
{# Tenant stranice #}
{% extends "layouts/tenant.html" %}
{% block content %}...{% endblock %}

{# Admin stranice - koriste base.html, imaju svoj sidebar #}
{% extends "layouts/base.html" %}
{% block content %}...{% endblock %}

{# Supplier stranice #}
{% extends "layouts/supplier.html" %}
{% block page_content %}...{% endblock %}

{# Public stranice #}
{% extends "layouts/base.html" %}
{% block content %}...{% endblock %}
```

### 4. API Helper Funkcije
```javascript
// Tenant - koristi api() iz layouts/tenant.html
const data = await api('/tickets');

// Admin - koristi adminApi() iz admin stranica
const data = await adminApi('/api/admin/tenants');

// Supplier - koristi supplierApi() iz layouts/supplier.html
const data = await supplierApi('/api/supplier/listings');
```

### 5. Garancije
- Default: iz tenant.settings_json.default_warranty_days
- Pocinje od `closed_at` timestamp-a
- `warranty_remaining_days` = warranty_expires_at - now

### 6. TenantPublicProfile Model (Public Site v2)

```python
# Osnovni podaci
is_public, display_name, tagline, description

# Kontakt (fallback na Tenant ako prazno)
phone, phone_secondary, email, address, city, postal_code
maps_url, maps_embed_url

# Branding
logo_url, cover_image_url, primary_color, secondary_color

# Radno vreme (JSON)
working_hours = {"mon": "09:00-18:00", "tue": "09:00-18:00", ...}

# Social linkovi
facebook_url, instagram_url, twitter_url, linkedin_url, youtube_url, tiktok_url

# SEO
meta_title, meta_description, meta_keywords

# Custom domain
custom_domain, custom_domain_verified, custom_domain_ssl_status

# === PUBLIC SITE v2 POLJA ===

# FAQ sekcija
faq_title = "Često postavljana pitanja"
faq_items = [{"question": "...", "answer": "..."}]

# Brendovi
show_brands_section = True
supported_brands = ["apple", "samsung", "xiaomi", ...]

# Proces rada
show_process_section = True
process_title = "Kako funkcioniše"
process_steps = [{"step": 1, "icon": "📱", "title": "...", "description": "..."}]

# WhatsApp
show_whatsapp_button = False
whatsapp_number = "381641234567"  # bez + i razmaka
whatsapp_message = "Zdravo! Imam pitanje..."

# Status tracking widget
show_tracking_widget = True
tracking_widget_title = "Pratite status popravke"

# Hero stil
hero_style = "centered"  # 'centered', 'split', 'minimal'
```

**Kontakt Fallback:**
Ako je polje u `TenantPublicProfile` prazno, template koristi podatke iz `Tenant` modela:
- `profile.address` → `tenant.adresa_sedista`
- `profile.city` → `tenant.grad`
- `profile.phone` → `tenant.telefon`
- `profile.email` → `tenant.email`

---

## Boja Tema

| Panel | Primary Color | Accent |
|-------|---------------|--------|
| Tenant | Blue (#2563eb) | Blue |
| Admin | Gray/Red (#374151) | Red |
| Supplier | Purple (#7c3aed) | Purple |

---

## Platform Admin - Koriscenje Partials

### Struktura Admin Stranice

```jinja2
{% extends "layouts/base.html" %}
{% block title %}Naslov - ServisHub Admin{% endblock %}

{% block head %}
{% include "admin/_admin_styles.html" %}
{% endblock %}

{% block content %}
<div :class="{'admin-glass': theme === 'glass', 'admin-light': theme === 'light'}"
     x-data="pageFunction()" x-init="init()">
    <div class="admin-wrapper min-h-screen bg-gray-100">
        {% set active_page = 'dashboard' %}
        {% include "admin/_sidebar.html" %}

        <div class="ml-64">
            <!-- Topbar -->
            <div class="admin-topbar ...">...</div>
            <!-- Content -->
            <div class="p-8">...</div>
        </div>
    </div>
</div>
<script>
function pageFunction() {
    return {
        theme: localStorage.getItem('admin-theme') || 'light',
        setTheme(t) { this.theme = t; localStorage.setItem('admin-theme', t); },
        logout() {
            localStorage.removeItem('admin_access_token');
            localStorage.removeItem('admin_refresh_token');
            window.location.href = '/admin/login';
        },
        // ... ostale funkcije
    }
}
</script>
{% endblock %}
```

### active_page Vrednosti

| Vrednost | Stranica |
|----------|----------|
| `dashboard` | Dashboard |
| `tenants` | Servisi (lista i detalj) |
| `suppliers` | Dobavljaci (lista i detalj) |
| `payments` | Uplate |
| `settings` | Podesavanja |

**Napomena:** KYC/Predstavnici je uklonjen iz sidebar navigacije - premesta se u detalje servisa.

---

## Kredencijali (DEV)

```
Admin: admin@servishub.rs / Admin123!
Heroku: servishub.herokuapp.com
GitHub: github.com/v1sk0/servishub
```

---

## Sledeci Koraci

1. [ ] Testiranje svih stranica lokalno
2. [x] Deploy na Heroku
3. [ ] Custom domain setup (servishub.rs)
4. [ ] Email notifikacije (Celery)
5. [ ] SMS integracija

---

## Changelog

| Verzija | Datum | Izmene |
|---------|-------|--------|
| v0.6.2 | 2026-01-19 | **Public Site v2:** FAQ, Brendovi, Proces, WhatsApp, Status tracking, AOS animacije, Contact fallback |
| v0.6.1 | 2026-01-19 | **Wildcard Subdomain:** Heroku + Cloudflare DNS, savePublicProfile fix |
| v0.6.0 | 2026-01-19 | **Public Site Fix:** Route deduplication, working_hours format, JSON flag_modified |
| v0.5.9 | 2026-01-18 | **UI/UX Performance:** FOUC fix, x-cloak, tab transitions, skeletons, chart tooltips |
| v0.5.8 | 2026-01-18 | **Public Site:** Javne stranice tenanta (subdomain), settings tab, dokumentacija |
| v0.5.7 | 2026-01-15 | **Platform Admin standardizacija:** vizuelna konzistencija svih stranica, KYC uklonjen iz sidebar-a |
| v0.5.6 | 2026-01-15 | **Platform Admin refaktoring:** sidebar partial, theme support, KYC→Predstavnici |
| v0.5.5 | 2026-01-12 | Verifikacija strukture, fix layout extends, cleanup |
| v0.5.4 | 2026-01-12 | Supplier settings, register; Frontend 100% komplet |
| v0.5.3 | 2026-01-12 | Supplier panel komplet (login, dashboard, catalog, orders) |
| v0.5.2 | 2026-01-12 | Marketplace search, Orders list, Settings page |
| v0.5.1 | 2026-01-12 | Inventory pages, Admin tenants list, KYC review |
| v0.5.0 | 2026-01-12 | Frontend blueprint, sve stranice |
| v0.4.0 | 2026-01-11 | Public API, Supplier API |
| v0.3.0 | 2026-01-10 | Admin API, Orders |
| v0.2.0 | 2026-01-09 | V1 API komplet |
| v0.1.0 | 2026-01-08 | Modeli, infrastruktura, Heroku |

---

*Backend: 115+ ruta | Frontend: 53 fajla (51 template + 2 admin partials) | Heroku: Ready*