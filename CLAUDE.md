# CLAUDE.md - ServisHub

Instrukcije za Claude Code agente. **CITAJ OVO PRE BILO KAKVIH IZMENA.**

---

## RESUME POINT

**v0.5.9** | 2026-01-18 | Backend 100% | Frontend 100%

### Status: KOMPLETNO - UI/UX Performance optimizacije

**Poslednje izmene (v0.5.9):**
- Eliminisan FOUC (Flash of Unstyled Content) - smooth fade-in
- Alpine.js trzanje fiksirano (x-cloak)
- Tab transitions u Settings stranici
- Loading skeletons za Dashboard i Tickets
- Chart.js tooltips theme-aware (light/glass)
- Kreirana docs/UI_UX_PERFORMANCE.md dokumentacija

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
│   ├── models/              # 10 SQLAlchemy modula
│   │   ├── tenant.py        # Tenant, ServiceLocation
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
│   │   └── public/          # 2 stranice
│   │       ├── landing.html
│   │       ├── track.html
│   │       └── marketplace.html
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