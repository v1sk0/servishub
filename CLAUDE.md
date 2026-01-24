# CLAUDE.md - ServisHub

Instrukcije za Claude Code agente. **CITAJ OVO PRE BILO KAKVIH IZMENA.**

---

## RESUME POINT

**v297** | 2026-01-24 | Backend KOMPLETNO | Frontend KOMPLETNO

### Status: IMPLEMENTIRANO - Threaded Messaging + Real-Time

**Plan fajl:** `C:\Users\darko\.claude\plans\nested-giggling-wall.md`

**Implementirano (v297):**
- ✅ Threaded messaging sistem (SYSTEM/SUPPORT/NETWORK)
- ✅ MessageThread, ThreadParticipant, Message modeli
- ✅ Tenant Messages API (`/api/v1/threads`)
- ✅ Admin Threads API (`/api/admin/threads`)
- ✅ Real-time polling (3s za poruke, 2s za typing)
- ✅ Typing indicator sa animiranim dots
- ✅ `after_id` param za efikasan polling
- ✅ Admin Support stranica (`/admin/support`)
- ✅ Tenant Messages stranica (`/messages`)

**Ključni fajlovi:**
| Fajl | Opis |
|------|------|
| `app/services/typing_service.py` | In-memory typing status (3s expiry) |
| `app/api/v1/threads.py` | Tenant API za poruke + typing |
| `app/api/admin/threads.py` | Admin API za poruke + typing |
| `app/templates/admin/support/list.html` | Admin chat UI |
| `app/templates/tenant/messages/inbox.html` | Tenant inbox sa 2 taba |

**Kako radi real-time messaging:**
1. Kad korisnik otvori chat, startuje polling (3s poruke, 2s typing)
2. `pollNewMessages()` koristi `after_id` param - dohvata samo nove poruke
3. `pollTyping()` proverava ko kuca u threadu
4. `onTyping()` detektuje kucanje i šalje status serveru
5. Typing expires nakon 3s neaktivnosti

**Još planirano (networking):**
- Faza 4: Invite + TenantConnection + Network UI
- Faza 5: Security hardening (rate limiting, audit)

---

### Prethodne verzije

**v241** (23. Januar 2026) - Role-Based Access Control + OAuth Fix

**1. Role-Based Access Control za Tim:**
- **Sidebar:** "Tim" link sakriven za TECHNICIAN i RECEPTIONIST
  - Dodat `x-show="isAdmin()"` u tenant_sidebar.html
  - Nova `isAdmin()` metoda proverava OWNER/ADMIN/MANAGER uloge
- **API (users.py):** Zaštićeni team management endpoints
  - `GET /users` - Samo admin role mogu videti listu
  - `GET /users/:id` - Non-admin može videti samo svoj profil
  - `PUT /users/:id` - Samo admin role mogu menjati profile

**2. Google OAuth Login Fix (kritično):**
- **Problem:** Race condition - Alpine.js komponente pokretale API pozive pre nego što su tokeni sačuvani
- **Rešenje:** Sinhroni XMLHttpRequest u `<head>` sekciji tenant.html
  - Blokira SVE učitavanje dok se tokeni ne preuzmu
  - Izvršava se PRE Alpine.js inicijalizacije
  - Redirect na čist URL nakon uspešnog preuzimanja

**Izmenjeni fajlovi:**
- `app/templates/components/tenant_sidebar.html`
- `app/api/v1/users.py`
- `app/templates/layouts/tenant.html`

**Prethodne izmene (v235):**
- **Admin Settings:** Social linkovi dodati u Company modal
  - Facebook, Instagram, LinkedIn, Twitter/X, YouTube
  - Koriste se na landing page u Contact sekciji
- **Model:** `PlatformSettings` azuriran
  - `get_company_data()` - ukljucuje social_* polja
  - `get_contact_data()` - koristi company_* polja direktno
- **API:** `UpdateCompanyRequest` prosiren social poljima
- **Landing Page:** Dinamicki prikazuje kontakt iz company data

**Prethodne izmene (v0.6.3):**
- **Security:** Phone verification za ticket tracking po broju naloga
  - Pretraga po broju (SRV-0003) zahteva poslednja 4 broja telefona
  - Sprečen enumeration napad (pogađanje brojeva naloga)
  - Access token (QR kod) i dalje radi bez verifikacije
- **Tracking Widget:** Ažuriran da traži broj naloga + telefon
- **API:** Nova helper funkcija `_parse_ticket_identifier()` za parsiranje formata
- **UX:** Bolji error messages sa srpskim tekstom

**Prethodne izmene (v0.6.2):**
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
- Tenant panel (28 stranica) - ukljucuje tickets/print, warranties, verify_email, pricing
- Admin panel (13 stranica + 2 partials) - ukljucuje activity, packages, security
- Supplier panel (9 stranica)
- Public stranice (5 stranica) - ukljucuje privacy, terms
- Tenant Public (5 stranica) - home, base, cenovnik, kontakt, o_nama
- Components (2 fajla) - sidebar partials
- Layouts (3 fajla)

**Ukupno:** 67 HTML fajlova

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
│   ├── models/              # 16 SQLAlchemy modula
│   │   ├── tenant.py        # Tenant, ServiceLocation
│   │   ├── tenant_public_profile.py # TenantPublicProfile (javna stranica)
│   │   ├── user.py          # TenantUser, UserLocation
│   │   ├── ticket.py        # ServiceTicket, TicketNotificationLog
│   │   ├── inventory.py     # PhoneListing, SparePart
│   │   ├── supplier.py      # Supplier, SupplierListing, SupplierUser
│   │   ├── order.py         # PartOrder, PartOrderItem, PartOrderMessage
│   │   ├── representative.py # ServiceRepresentative (KYC)
│   │   ├── admin.py         # PlatformAdmin
│   │   ├── admin_activity.py # AdminActivityLog
│   │   ├── audit.py         # AuditLog
│   │   ├── email_verification.py # PendingEmailVerification
│   │   ├── platform_settings.py # PlatformSettings (globalna config)
│   │   ├── security_event.py # SecurityEvent (security log)
│   │   ├── service.py       # ServiceItem (cenovnik usluga)
│   │   └── tenant_message.py # TenantMessage (admin->tenant poruke)
│   │
│   ├── api/                 # 120+ API ruta
│   │   ├── v1/              # Tenant API (70+ ruta)
│   │   │   ├── auth.py      # login, register, refresh, me
│   │   │   ├── tenant.py    # profile, settings, subscription, kyc
│   │   │   ├── users.py     # CRUD korisnika
│   │   │   ├── locations.py # CRUD lokacija
│   │   │   ├── tickets.py   # CRUD naloga, notify, write-off
│   │   │   ├── inventory.py # phones, parts
│   │   │   ├── marketplace.py # pretraga, brands
│   │   │   ├── orders.py    # narudzbine
│   │   │   ├── services.py  # cenovnik usluga (ServiceItem)
│   │   │   ├── messages.py  # tenant poruke od admina
│   │   │   └── public.py    # javni pricing endpoint
│   │   │
│   │   ├── admin/           # Admin API (35+ ruta)
│   │   │   ├── auth.py      # admin login
│   │   │   ├── dashboard.py # statistika
│   │   │   ├── tenants.py   # upravljanje servisima
│   │   │   ├── kyc.py       # KYC verifikacija
│   │   │   ├── settings.py  # platform settings, company data
│   │   │   ├── payments.py  # uplate i fakture
│   │   │   ├── activity.py  # admin activity log
│   │   │   ├── security.py  # security events
│   │   │   └── scheduler.py # background jobs status
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
│   ├── templates/           # 67 Jinja2 template
│   │   ├── layouts/         # 3 layout-a
│   │   │   ├── base.html    # Osnovni (public, admin)
│   │   │   ├── tenant.html  # Tenant panel (plava tema)
│   │   │   └── supplier.html # Supplier panel (ljubicasta tema)
│   │   │
│   │   ├── components/      # 2 sidebar partials
│   │   │   ├── tenant_sidebar.html
│   │   │   └── supplier_sidebar.html
│   │   │
│   │   ├── tenant/          # 28 stranica
│   │   │   ├── login.html, register.html, dashboard.html, verify_email.html
│   │   │   ├── tickets/ (list, new, detail, edit, print, warranties)
│   │   │   ├── inventory/ (phones, phones_new, parts, parts_new)
│   │   │   ├── marketplace/ (search)
│   │   │   ├── orders/ (list, detail)
│   │   │   ├── locations/ (list, new, detail)
│   │   │   ├── team/ (list, new, detail)
│   │   │   ├── settings/ (index, profile, subscription, kyc)
│   │   │   └── pricing/ (index)
│   │   │
│   │   ├── admin/           # 13 stranica + 2 partials
│   │   │   ├── _sidebar.html        # SHARED: navigacija za sve admin stranice
│   │   │   ├── _admin_styles.html   # SHARED: CSS teme (light/glass)
│   │   │   ├── login.html, dashboard.html
│   │   │   ├── tenants/ (list, detail)
│   │   │   ├── kyc/ (list, detail)
│   │   │   ├── suppliers/ (list, detail)
│   │   │   ├── payments/ (list)
│   │   │   ├── settings/ (index)
│   │   │   ├── activity/ (list)
│   │   │   ├── packages/ (index)
│   │   │   └── security/ (events)
│   │   │
│   │   ├── supplier/        # 9 stranica
│   │   │   ├── login.html, register.html, dashboard.html, settings.html
│   │   │   ├── catalog/ (list, new, detail)
│   │   │   └── orders/ (list, detail)
│   │   │
│   │   ├── public/          # 5 stranica (ServisHub landing)
│   │   │   ├── landing.html, track.html, marketplace.html
│   │   │   ├── privacy.html
│   │   │   └── terms.html
│   │   │
│   │   └── tenant_public/   # 5 stranica (javni sajt tenanta)
│   │       ├── base.html    # Layout sa nav, footer, floating buttons
│   │       ├── home.html    # Homepage sa svim sekcijama
│   │       ├── cenovnik.html, kontakt.html, o_nama.html
│   │
│   ├── services/            # Business logic
│   │   ├── typing_service.py # Real-time typing indicators (in-memory)
│   │   └── ...
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
| V1 (Tenant) | /api/v1 | JWT (access_token) | 70+ |
| Admin | /api/admin | JWT (admin_access_token) | 35+ |
| Supplier | /api/supplier | JWT (supplier_access_token) | 22 |
| Public | /api/public | None | 7 |

**Health:** `GET /health`

---

## Frontend Stranice - Kompletna Lista

### Tenant Panel (28)
| URL | Template |
|-----|----------|
| `/login` | tenant/login.html |
| `/register` | tenant/register.html |
| `/dashboard` | tenant/dashboard.html |
| `/verify-email` | tenant/verify_email.html |
| `/tickets` | tenant/tickets/list.html |
| `/tickets/new` | tenant/tickets/new.html |
| `/tickets/:id` | tenant/tickets/detail.html |
| `/tickets/:id/edit` | tenant/tickets/edit.html |
| `/tickets/:id/print` | tenant/tickets/print.html |
| `/tickets/warranties` | tenant/tickets/warranties.html |
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
| `/pricing` | tenant/pricing/index.html |
| `/messages` | tenant/messages/inbox.html |

### Admin Panel (13 stranica + 2 partials)

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
| `/admin/kyc` | admin/kyc/list.html | - |
| `/admin/kyc/:id` | admin/kyc/detail.html | - |
| `/admin/suppliers` | admin/suppliers/list.html | suppliers |
| `/admin/suppliers/:id` | admin/suppliers/detail.html | suppliers |
| `/admin/payments` | admin/payments/list.html | payments |
| `/admin/settings` | admin/settings/index.html | settings |
| `/admin/activity` | admin/activity/list.html | activity |
| `/admin/packages` | admin/packages/index.html | packages |
| `/admin/security` | admin/security/events.html | security |
| `/admin/support` | admin/support/list.html | support |

### Supplier Panel (9)
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

### Public (5)
| URL | Template |
|-----|----------|
| `/` | public/landing.html |
| `/track/:token` | public/track.html |
| `/marketplace` | public/marketplace.html |
| `/privacy` | public/privacy.html |
| `/terms` | public/terms.html |

### Tenant Public (5) - Javni sajt servisa
| URL | Template |
|-----|----------|
| `subdomain.servishub.rs/` | tenant_public/home.html |
| `subdomain.servishub.rs/cenovnik` | tenant_public/cenovnik.html |
| `subdomain.servishub.rs/kontakt` | tenant_public/kontakt.html |
| `subdomain.servishub.rs/o-nama` | tenant_public/o_nama.html |
| (base layout) | tenant_public/base.html |

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

### 7. Real-Time Messaging (Typing Indicators)

**Arhitektura:**
```
typing_service.py (in-memory, shared)
═══════════════════════════════════════
_typing_status = {
    thread_id: {
        user_key: {
            'name': 'Petar',
            'type': 'tenant',
            'expires': timestamp + 3s
        }
    }
}
```

**API Endpoints:**
```
# Tenant
POST /api/v1/threads/{id}/typing   # {typing: true/false}
GET  /api/v1/threads/{id}/typing   # {typing: [{name, type}]}
GET  /api/v1/threads/{id}/messages?after_id=123  # samo nove poruke

# Admin
POST /api/admin/threads/{id}/typing
GET  /api/admin/threads/{id}/typing
GET  /api/admin/threads/{id}/messages?after_id=123
```

**Frontend Polling:**
```javascript
// Kad se otvori chat - startuj polling
this.messagePollingInterval = setInterval(() => this.pollNewMessages(), 3000);
this.typingPollingInterval = setInterval(() => this.pollTyping(), 2000);

// pollNewMessages() koristi after_id za efikasnost
const url = `/api/v1/threads/${id}/messages?after_id=${lastMessageId}`;

// onTyping() - kad korisnik kuca
if (!this.isTyping) {
    this.isTyping = true;
    this.sendTypingStatus(true);
}
// Timeout posle 2s -> sendTypingStatus(false)
```

**Typing Indicator CSS:**
```css
.typing-dots span {
    animation: typingBounce 1.4s infinite ease-in-out;
}
.typing-dots span:nth-child(1) { animation-delay: 0s; }
.typing-dots span:nth-child(2) { animation-delay: 0.2s; }
.typing-dots span:nth-child(3) { animation-delay: 0.4s; }
```

---

### 8. Ticket Tracking API (Public)

**Endpoint:** `GET /api/public/track/<identifier>`

**Podržani formati identifikatora:**

| Format | Primer | Verifikacija |
|--------|--------|--------------|
| Access Token (64 char) | `a1b2c3d4...` | ❌ Nije potrebna |
| Broj naloga | `SRV-0003`, `3`, `0003` | ✅ Poslednja 4 broja telefona |

**Parametri za pretragu po broju:**
- `tenant_id` - ID tenanta (prosleđuje se automatski sa javne stranice)
- `phone` - Poslednja 4 broja telefona kupca (obavezno za sigurnost)

**Sigurnosne mere:**
1. **Phone verification** - Sprečava enumeration napad (pogađanje brojeva 1, 2, 3...)
2. **Tenant context** - Broj naloga je jedinstven samo u okviru tenanta
3. **Access token** - 64-char token za siguran pristup bez verifikacije (QR kod)

**Primer korišćenja:**
```
# Sa access tokenom (QR kod, SMS, email)
GET /api/public/track/a1b2c3d4e5f6...

# Sa brojem naloga (widget na javnoj stranici)
GET /api/public/track/3?tenant_id=8&phone=1234
```

**Odgovori:**
- `200` - Podaci o nalogu
- `400` - Neispravan format ili nedostaje telefon
- `403` - Telefon se ne poklapa
- `404` - Nalog nije pronađen

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

## Billing Sistem

### Status Flow
```
DEMO (7 dana) ──────────────────────────────────────> CANCELLED
     │
     └──> TRIAL (60 dana, admin aktivira) ──────────> CANCELLED
                    │
                    └──> ACTIVE (pretplata) ────────> CANCELLED
                              │
                              └──> EXPIRED (grace 7 dana)
                                        │
                                        └──> SUSPENDED
```

### Cene (PlatformSettings)
- `base_price`: Mesecna cena baznog paketa (default: 3600 RSD)
- `location_price`: Cena dodatne lokacije (default: 1800 RSD)
- `trial_days`: Trajanje trial perioda (default: 60 dana)
- `grace_period_days`: Grace period pre suspenzije (default: 7 dana)

### Trust Score
- Bodovi: 0-100 (visi = bolji)
- Omogucava "na rec" produzenje (max 7 dana)
- Smanjuje se za kasnjenje
- Povecava se za redovne uplate

### CLI Komande za Billing
```bash
flask billing-daily       # Sve dnevne provere
flask check-subscriptions # Provera isteklih pretplata
flask generate-invoices   # Generisanje faktura (1. u mesecu)
flask mark-overdue        # Oznaci prekoracene fakture
flask update-overdue-days # Azuriraj dane kasnjenja
flask send-billing-emails --type=reminders  # Email podsecanja
```

---

## Platform Settings (Globalna Podesavanja)

### Endpoint: `/api/admin/settings/company`

Sadrzi podatke o firmi ServisHub koji se koriste na fakturama i landing page.

**Polja:**
```python
# Osnovni podaci
company_name, company_address, company_city, company_postal_code
company_country, company_pib, company_mb
company_phone, company_email, company_website
company_bank_name, company_bank_account

# Social linkovi (za landing page)
social_facebook, social_instagram, social_linkedin
social_twitter, social_youtube
```

**Tok podataka:**
```
Admin Panel → Company Modal → PlatformSettings
     ↓
get_company_data() + get_contact_data()
     ↓
Public API /api/v1/public/pricing
     ↓
Landing Page (kontakt sekcija, social ikone)
```

---

## Changelog

| Verzija | Datum | Izmene |
|---------|-------|--------|
| v297 | 2026-01-24 | **Real-Time Messaging:** Typing indicators, fast polling (3s), typing_service, admin support chat, tenant inbox sa dva taba |
| v241 | 2026-01-23 | **Security:** Role-based Tim visibility (sidebar), API zaštita team management endpoints, **OAuth Fix:** sinhroni token handling (race condition fix) |
| v235 | 2026-01-21 | **Admin Settings:** Social linkovi u Company modal, landing page dinamicki kontakt |
| v0.6.3 | 2026-01-19 | **Security:** Phone verification za ticket tracking, sprečen enumeration napad |
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

*Backend: 120+ ruta | Frontend: 67 fajlova | Heroku: Ready*