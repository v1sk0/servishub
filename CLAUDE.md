# CLAUDE.md - ServisHub

Instrukcije za Claude Code agente. **ČITAJ OVO PRE BILO KAKVIH IZMENA.**

---

## 🔴 RESUME POINT

**v0.5.4** | 2026-01-12 | Backend 100% | Frontend 100%

### Status: KOMPLETNO - Spreman za deploy

Svi frontend moduli zavrseni:
- Tenant panel (login, register, dashboard, tickets, inventory, marketplace, orders, settings)
- Admin panel (login, dashboard, tenants, KYC)
- Supplier panel (login, register, dashboard, catalog, orders, settings)
- Public stranice (landing, track)

> Ažuriraj ovaj RESUME POINT nakon svake značajne izmene!

---

## Projekat

**ServisHub** - SaaS platforma za servise mobilnih telefona.

| Stack | Tehnologija |
|-------|-------------|
| Backend | Python 3.11 + Flask 3.x + SQLAlchemy 2.0 |
| Frontend | Tailwind CSS + Alpine.js (CDN) + Jinja2 |
| Baza | PostgreSQL 15 (Railway) |
| Auth | JWT (PyJWT) |
| Deploy | Railway + GitHub |

---

## Struktura

```
servishub/
├── app/
│   ├── models/           # 18 SQLAlchemy tabela
│   ├── api/              # 115 API ruta
│   │   ├── v1/           # Tenant API (65)
│   │   ├── admin/        # Admin API (21)
│   │   ├── supplier/     # Supplier API (22)
│   │   └── public/       # Public API (7)
│   ├── frontend/         # HTML rute
│   │   ├── tenant.py     # 30+ ruta
│   │   ├── admin.py
│   │   └── public.py
│   └── templates/        # Jinja2
│       ├── tenant/       # ✅ login, register, dashboard, tickets/*, inventory/*
│       ├── admin/        # ✅ login, dashboard, tenants/*, kyc/*
│       ├── supplier/     # ✅ login, dashboard, catalog/*, orders/*
│       └── public/       # ✅ landing, track
├── migrations/
├── run.py
└── requirements.txt
```

---

## Komande

```bash
cd C:\servishub
venv\Scripts\activate
python run.py              # Dev server → localhost:5000
flask db migrate -m "..."  # Nova migracija
flask db upgrade           # Primeni migracije
flask create-admin         # Kreiraj admin-a
```

---

## API Endpointi

| API | Prefix | Auth | Rute |
|-----|--------|------|------|
| V1 (Tenant) | /api/v1 | JWT tenant | 65 |
| Admin | /api/admin | JWT admin | 21 |
| Supplier | /api/supplier | JWT supplier | 22 |
| Public | /api/public | None | 7 |

**Health:** `GET /health`

---

## Frontend Stranice

| URL | Template | Status |
|-----|----------|--------|
| `/` | public/landing.html | ✅ |
| `/track/:token` | public/track.html | ✅ |
| `/login` | tenant/login.html | ✅ |
| `/register` | tenant/register.html | ✅ |
| `/dashboard` | tenant/dashboard.html | ✅ |
| `/tickets` | tenant/tickets/list.html | ✅ |
| `/tickets/new` | tenant/tickets/new.html | ✅ |
| `/tickets/:id` | tenant/tickets/detail.html | ✅ |
| `/inventory/phones` | tenant/inventory/phones.html | ✅ |
| `/inventory/parts` | tenant/inventory/parts.html | ✅ |
| `/admin/login` | admin/login.html | ✅ |
| `/admin/dashboard` | admin/dashboard.html | ✅ |
| `/admin/tenants` | admin/tenants/list.html | ✅ |
| `/admin/kyc` | admin/kyc/review.html | ✅ |
| `/marketplace` | tenant/marketplace/search.html | ✅ |
| `/orders` | tenant/orders/list.html | ✅ |
| `/settings` | tenant/settings/index.html | ✅ |
| `/supplier/login` | supplier/login.html | ✅ |
| `/supplier/register` | supplier/register.html | ✅ |
| `/supplier/dashboard` | supplier/dashboard.html | ✅ |
| `/supplier/catalog` | supplier/catalog/list.html | ✅ |
| `/supplier/orders` | supplier/orders/list.html | ✅ |
| `/supplier/settings` | supplier/settings.html | ✅ |

---

## Kritična Pravila

### Multi-Tenant Izolacija
```python
# UVEK filtriraj po tenant_id
tickets = ServiceTicket.query.filter_by(tenant_id=g.tenant_id)
# NIKADA: ServiceTicket.query.all()
```

### JWT Storage (Frontend)
```javascript
// Tenant
localStorage.getItem('access_token')
// Admin (odvojeno!)
localStorage.getItem('admin_access_token')
// Supplier (odvojeno!)
localStorage.getItem('supplier_access_token')
```

### Garancije
- Default: 30 dana iz tenant settings
- Počinje od `closed_at`
- `warranty_remaining_days` = expires - now

---

## Kredencijali (DEV)

```
Admin: admin@servishub.rs / Admin123!
Railway: mainline.proxy.rlwy.net:35540
GitHub: github.com/v1sk0/servishub
```

---

## Changelog

| Verzija | Datum | Izmene |
|---------|-------|--------|
| v0.5.4 | 2026-01-12 | Supplier settings, register; Frontend 100% komplet |
| v0.5.3 | 2026-01-12 | Supplier panel komplet (login, dashboard, catalog, orders) |
| v0.5.2 | 2026-01-12 | Marketplace search, Orders list, Settings page (profile, team, locations, KYC) |
| v0.5.1 | 2026-01-12 | Inventory pages (phones, parts), Admin tenants list, KYC review |
| v0.5.0 | 2026-01-12 | Frontend blueprint, tenant stranice, admin stranice, public stranice |
| v0.4.0 | 2026-01-11 | Public API, Supplier API |
| v0.3.0 | 2026-01-10 | Admin API, Orders |
| v0.2.0 | 2026-01-09 | V1 API komplet |
| v0.1.0 | 2026-01-08 | Modeli, infrastruktura, Railway |

---

*Backend: 115 ruta | Frontend: 100% | Railway: Ready*
