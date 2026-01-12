# ServisHub - Status Implementacije

**Poslednje azuriranje:** 2026-01-12
**Lokacija projekta:** C:\servishub
**GitHub:** https://github.com/v1sk0/servishub
**Railway:** meticulous-appreciation

---

## SUMARNO STANJE

| Faza | Status | Napomena |
|------|--------|----------|
| Faza 1: Setup i Infrastruktura | GOTOVO | Flask app, modeli, migracije |
| Faza 2: Auth Modul | GOTOVO | JWT za tenant, admin, supplier |
| Faza 3: Audit Log System | GOTOVO | AuditLog model |
| Faza 4: KYC i Predstavnici | GOTOVO | ServiceRepresentative model |
| Faza 5: Tickets Modul | GOTOVO | CRUD API, status, garancije |
| Faza 6: Inventory Modul | GOTOVO | Telefoni, delovi |
| Faza 7: Marketplace i Orders | GOTOVO | Supplier, PartOrder modeli |
| Faza 8: Tenant Management API | GOTOVO | Profile, settings, locations, users |
| Faza 9: Supplier API | GOTOVO | Auth, listings, orders |
| Faza 15: Platform Admin API | GOTOVO | Tenants, KYC, Dashboard |
| Railway Deployment | GOTOVO | GitHub + PostgreSQL + 18 tabela |

---

## API STATISTIKA

| API | Broj ruta | Opis |
|-----|-----------|------|
| V1 API | 65 | B2B za servise (tenante) |
| Admin API | 21 | Platform administracija |
| Supplier API | 22 | Za dobavljace |
| **UKUPNO** | **108** | |

---

## V1 API ENDPOINTS (/api/v1/*)

### Auth
- POST /auth/register - Registracija novog servisa
- POST /auth/login - Login
- POST /auth/refresh - Refresh token
- POST /auth/logout - Logout
- GET /auth/me - Trenutni korisnik
- POST /auth/change-password - Promena lozinke

### Tenant
- GET /tenant/profile - Profil servisa
- PUT /tenant/profile - Azuriranje profila
- GET /tenant/settings - Podesavanja
- PUT /tenant/settings - Azuriranje podesavanja
- GET /tenant/subscription - Status pretplate
- GET /tenant/kyc - KYC status
- POST /tenant/kyc - Slanje KYC

### Locations
- GET /locations - Lista lokacija
- POST /locations - Kreiranje lokacije
- GET /locations/:id - Detalji lokacije
- PUT /locations/:id - Azuriranje
- DELETE /locations/:id - Brisanje
- POST /locations/:id/set-primary - Postavi primarnu
- POST /locations/:id/users - Dodeli korisnika
- DELETE /locations/:id/users/:user_id - Ukloni korisnika

### Users
- GET /users - Lista korisnika
- POST /users - Kreiranje korisnika
- GET /users/:id - Detalji
- PUT /users/:id - Azuriranje
- DELETE /users/:id - Brisanje
- GET /users/me - Trenutni korisnik
- PUT /users/me/password - Promena lozinke
- POST /users/:id/reset-password - Reset lozinke
- GET /users/roles - Lista uloga

### Tickets
- GET /tickets - Lista naloga
- POST /tickets - Kreiranje naloga
- GET /tickets/:id - Detalji
- PUT /tickets/:id - Azuriranje
- PUT /tickets/:id/status - Promena statusa
- POST /tickets/:id/pay - Naplata
- GET /tickets/public/:token - Javni pregled (QR)

### Inventory
- GET /inventory/phones - Lista telefona
- POST /inventory/phones - Dodavanje
- GET /inventory/phones/:id - Detalji
- PUT /inventory/phones/:id - Azuriranje
- POST /inventory/phones/:id/sell - Prodaja
- POST /inventory/phones/:id/collect - Naplata
- GET /inventory/parts - Lista delova
- POST /inventory/parts - Dodavanje
- GET /inventory/parts/:id - Detalji
- PUT /inventory/parts/:id - Azuriranje
- POST /inventory/parts/:id/adjust - Korekcija stanja

### Marketplace
- GET /marketplace/parts - Pretraga delova
- GET /marketplace/parts/:source/:id - Detalji dela
- GET /marketplace/suppliers - Lista dobavljaca
- GET /marketplace/suppliers/:id - Detalji dobavljaca
- GET /marketplace/categories - Liste kategorija
- GET /marketplace/brands - Lista brendova

### Orders
- GET /orders - Lista narudzbina
- POST /orders - Kreiranje narudzbine
- GET /orders/:id - Detalji
- POST /orders/:id/send - Slanje dobavljacu
- POST /orders/:id/cancel - Otkazivanje
- POST /orders/:id/confirm-delivery - Potvrda isporuke
- POST /orders/:id/complete - Zavrsavanje
- GET /orders/:id/messages - Poruke
- POST /orders/:id/messages - Slanje poruke
- GET /orders/statuses - Lista statusa

---

## ADMIN API ENDPOINTS (/api/admin/*)

- POST /auth/login - Admin login
- POST /auth/refresh - Refresh token
- POST /auth/logout - Logout
- GET /auth/me - Trenutni admin
- GET /tenants - Lista servisa
- GET /tenants/:id - Detalji servisa
- POST /tenants/:id/activate - Aktivacija
- POST /tenants/:id/suspend - Suspenzija
- POST /tenants/:id/extend-trial - Produzenje triala
- GET /kyc/pending - KYC na cekanju
- POST /kyc/:id/approve - Odobrenje KYC
- POST /kyc/:id/reject - Odbijanje KYC
- POST /kyc/:id/request-resubmit - Zahtev za ponovno slanje
- GET /kyc/stats - KYC statistika
- GET /dashboard/stats - Dashboard statistika
- GET /dashboard/revenue-chart - Grafikon prihoda
- GET /dashboard/tenant-chart - Grafikon servisa
- GET /dashboard/recent-activity - Poslednje aktivnosti

---

## SUPPLIER API ENDPOINTS (/api/supplier/*)

### Auth
- POST /auth/register - Registracija dobavljaca
- POST /auth/login - Login
- POST /auth/refresh - Refresh token
- POST /auth/logout - Logout
- GET /auth/me - Trenutni dobavljac

### Listings
- GET /listings - Lista proizvoda
- POST /listings - Dodavanje proizvoda
- GET /listings/:id - Detalji
- PUT /listings/:id - Azuriranje
- DELETE /listings/:id - Brisanje
- PUT /listings/bulk-stock - Bulk azuriranje stanja
- GET /listings/stats - Statistika
- POST /listings/import - Import proizvoda

### Orders
- GET /orders - Lista narudzbina
- GET /orders/pending - Narudzbine na cekanju
- GET /orders/:id - Detalji
- POST /orders/:id/confirm - Potvrda
- POST /orders/:id/reject - Odbijanje
- POST /orders/:id/ship - Slanje
- GET /orders/:id/messages - Poruke
- POST /orders/:id/messages - Slanje poruke
- GET /orders/stats - Statistika

---

## BAZA PODATAKA (Railway PostgreSQL)

**18 tabela:**
- alembic_version, tenant, service_location, tenant_user
- user_location, platform_admin, service_ticket
- phone_listing, spare_part, supplier, supplier_listing
- supplier_user, part_order, part_order_item
- part_order_message, service_representative
- subscription_payment, audit_log

**Platform Admin:**
- Email: admin@servishub.rs
- Password: Admin123! (PROMENITI!)

---

## STA PREOSTAJE

1. ~~V1 API (tenant, locations, users, marketplace, orders)~~ DONE
2. ~~Supplier API~~ DONE
3. Public API (B2C) - za krajnje kupce
4. Frontend (Tailwind + Alpine.js)
5. Email notifikacije
6. SMS integracija

---

Status azuriran: 2026-01-12
