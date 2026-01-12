# CLAUDE.md - ServisHub

Instrukcije za Claude Code agente. **ČITAJ OVO PRE BILO KAKVIH IZMENA.**

---

## Opis Projekta

**ServisHub** je SaaS platforma za servise mobilnih telefona i računara.

### Ključne funkcionalnosti
| Modul | Opis |
|-------|------|
| **Servisni nalozi** | Praćenje popravki sa QR kodovima, garancije, naplate |
| **Inventar** | Telefoni na lageru, rezervni delovi |
| **Marketplace** | Razmena delova između servisa i dobavljača |
| **Multi-tenant** | Svaki servis ima izolovan prostor (tenant_id na svemu) |
| **KYC** | Verifikacija identiteta vlasnika servisa |
| **Pretplata** | 3 meseca trial, zatim 3.600 + 1.800/lokacija RSD/mesec |

### Tipovi korisnika
1. **Servisi (Tenanti)** → `/api/v1/*` - JWT auth
2. **Dobavljači** → `/api/supplier/*` - JWT auth
3. **Platform Admini** → `/api/admin/*` - Admin JWT
4. **Krajnji kupci** → `/api/public/*` - Bez auth (QR tracking)

---

## Tech Stack

| Komponenta | Tehnologija | Verzija |
|------------|-------------|---------|
| Backend | Python + Flask | 3.11 + 3.x |
| ORM | SQLAlchemy | 2.0 |
| Baza | PostgreSQL (Railway) | 15 |
| Auth | JWT (PyJWT) | - |
| Validacija | Pydantic | v2 |
| Migracije | Flask-Migrate (Alembic) | - |
| Deploy | Railway + GitHub | - |

---

## Struktura Projekta

```
servishub/
├── app/
│   ├── __init__.py           # App factory, registracija blueprinta
│   ├── config.py             # Dev/Prod/Test config
│   ├── extensions.py         # db, migrate, cors
│   │
│   ├── models/               # SQLAlchemy modeli (18 tabela)
│   │   ├── tenant.py         # Tenant, ServiceLocation, TenantStatus
│   │   ├── user.py           # TenantUser, UserRole, UserLocation
│   │   ├── admin.py          # PlatformAdmin, AdminRole
│   │   ├── ticket.py         # ServiceTicket, TicketStatus
│   │   ├── inventory.py      # PhoneListing, SparePart, PartVisibility
│   │   ├── supplier.py       # Supplier, SupplierListing, SupplierUser
│   │   ├── order.py          # PartOrder, PartOrderItem, PartOrderMessage
│   │   ├── kyc.py            # ServiceRepresentative, SubscriptionPayment
│   │   └── audit.py          # AuditLog
│   │
│   └── api/                  # API Blueprints (115 ruta ukupno)
│       ├── v1/               # B2B za servise (65 ruta)
│       │   ├── auth.py       # Login, register, refresh, me
│       │   ├── tenant.py     # Profil, settings, subscription, KYC
│       │   ├── locations.py  # CRUD lokacija, assign users
│       │   ├── users.py      # CRUD korisnika, roles, passwords
│       │   ├── tickets.py    # CRUD naloga, status, pay
│       │   ├── inventory.py  # Telefoni, delovi
│       │   ├── marketplace.py # Pretraga delova
│       │   └── orders.py     # Narudžbine od dobavljača
│       │
│       ├── admin/            # Platform Admin (21 ruta)
│       │   ├── auth.py       # Admin login
│       │   ├── tenants.py    # Lista/activate/suspend servisa
│       │   ├── kyc.py        # Approve/reject KYC
│       │   └── dashboard.py  # Statistike, grafici
│       │
│       ├── supplier/         # Za dobavljače (22 rute)
│       │   ├── auth.py       # Register, login
│       │   ├── listings.py   # CRUD proizvoda, bulk stock
│       │   └── orders.py     # Primljene narudžbine
│       │
│       ├── public/           # Javni B2C (7 ruta)
│       │   ├── tickets.py    # /track/:token (QR praćenje)
│       │   └── marketplace.py # Javni pregled delova
│       │
│       └── middleware/
│           └── auth.py       # @jwt_required, @admin_required
│
├── migrations/versions/      # Alembic migracije
├── run.py                    # Dev server
├── wsgi.py                   # Production (Gunicorn)
├── Procfile                  # Railway config
└── requirements.txt
```

---

## API Pregled

### V1 API - B2B za Servise (`/api/v1/*`)

| Grupa | Endpointi |
|-------|-----------|
| **Auth** | register, login, refresh, logout, me, change-password |
| **Tenant** | profile, settings, subscription, kyc |
| **Locations** | list, create, get, update, delete, set-primary, assign/remove users |
| **Users** | list, create, get, update, delete, me, password, reset-password, roles |
| **Tickets** | list, create, get, update, status, pay, public/:token |
| **Inventory** | phones (list, create, get, update, sell, collect), parts (list, create, get, update, adjust) |
| **Marketplace** | parts search, parts/:source/:id, suppliers, suppliers/:id, categories, brands |
| **Orders** | list, create, get, send, cancel, confirm-delivery, complete, messages |

### Supplier API (`/api/supplier/*`)

| Grupa | Endpointi |
|-------|-----------|
| **Auth** | register, login, refresh, logout, me |
| **Listings** | list, create, get, update, delete, bulk-stock, stats, import |
| **Orders** | list, pending, get, confirm, reject, ship, messages, stats |

### Admin API (`/api/admin/*`)

| Grupa | Endpointi |
|-------|-----------|
| **Auth** | login, refresh, logout, me |
| **Tenants** | list, get, activate, suspend, extend-trial |
| **KYC** | pending, approve, reject, request-resubmit, stats |
| **Dashboard** | stats, revenue-chart, tenant-chart, recent-activity |

### Public API (`/api/public/*`)

| Endpoint | Opis |
|----------|------|
| GET /track/:token | Praćenje naloga (QR) |
| GET /track/:token/qr | Podaci za QR generisanje |
| GET /track/:token/receipt | Podaci za printanje potvrde |
| GET /marketplace/parts | Javna pretraga delova |
| GET /marketplace/suppliers | Lista verifikovanih dobavljača |
| GET /marketplace/categories | Kategorije delova |
| GET /marketplace/cities | Gradovi sa aktivnim servisima |

---

## Baza Podataka

### Railway PostgreSQL
```
Host: mainline.proxy.rlwy.net:35540
Database: railway
User: postgres
```

### Tabele (18)
```
tenant, service_location, tenant_user, user_location
platform_admin
service_ticket
phone_listing, spare_part
supplier, supplier_listing, supplier_user
part_order, part_order_item, part_order_message
service_representative, subscription_payment
audit_log
alembic_version
```

---

## Komande

### Lokalni razvoj
```bash
cd C:\servishub
venv\Scripts\activate
pip install -r requirements.txt
python run.py
# → http://localhost:5000
```

### Migracije
```bash
flask db migrate -m "Opis"
flask db upgrade
```

### CLI
```bash
flask create-admin   # Interaktivno kreira Platform Admina
```

### Health Check
```bash
curl http://localhost:5000/health
# → {"status": "healthy", "service": "servishub"}
```

---

## JWT Autentifikacija

### V1 (Tenant)
```
Header: Authorization: Bearer <access_token>
Payload: { type: "access", tenant_id, user_id, exp, iat }
```

### Admin
```
Header: Authorization: Bearer <admin_token>
Payload: { type: "admin_access", admin_id, role, exp, iat }
```

### Supplier
```
Header: Authorization: Bearer <supplier_token>
Payload: { type: "supplier_access", supplier_id, user_id, exp, iat }
```

---

## Kritična Pravila

### 1. Multi-Tenant Izolacija
```python
# UVEK filtriraj po tenant_id iz JWT-a
tickets = ServiceTicket.query.filter_by(tenant_id=g.tenant_id)

# NIKADA ovako:
tickets = ServiceTicket.query.all()  # ❌ OPASNO
```

### 2. Visibility (Delovi)
- `PRIVATE` → samo vlasnik vidi
- `PARTNER` → vide drugi servisi (B2B cena)
- `PUBLIC` → vide svi (javna cena)

### 3. Komisija
- 5% na marketplace transakcije
- Obračunava se pri kreiranju narudžbine

### 4. Garancije
- Default: 30 dana (iz tenant settings)
- Počinje od `closed_at` (zatvaranje naloga)
- `warranty_remaining_days` = expires - now

### 5. Ticket Access Token
- 64-karakterni hex string
- Generiše se pri kreiranju naloga
- Koristi se za QR praćenje (javno)

---

## Status Implementacije

| Komponenta | Status |
|------------|--------|
| Modeli (18 tabela) | ✅ DONE |
| V1 API (65 ruta) | ✅ DONE |
| Admin API (21 ruta) | ✅ DONE |
| Supplier API (22 rute) | ✅ DONE |
| Public API (7 ruta) | ✅ DONE |
| Railway PostgreSQL | ✅ DONE |
| GitHub repo | ✅ DONE |

### Preostaje
- [ ] Email notifikacije
- [ ] SMS integracija
- [ ] Frontend (Tailwind + Alpine.js)
- [ ] Cloudinary upload
- [ ] Stripe plaćanja

---

## Povezani Resursi

| Resurs | Lokacija |
|--------|----------|
| GitHub | https://github.com/v1sk0/servishub |
| Railway | meticulous-appreciation |
| Plan | C:\Users\darko\.claude\plans\dynamic-stirring-ullman.md |
| Dolce Vita | C:\dolcevita\ |

---

## Kredencijali (DEV)

```
Platform Admin:
  Email: admin@servishub.rs
  Pass:  Admin123!  ← PROMENITI U PRODUKCIJI!

Railway PostgreSQL:
  URL: postgresql://postgres:...@mainline.proxy.rlwy.net:35540/railway
```

---

*Ažurirano: 2026-01-12 | 115 API ruta | 18 tabela*
