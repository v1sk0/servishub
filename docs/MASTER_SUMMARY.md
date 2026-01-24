# ServisHub - Master Summary

> Poslednje ažuriranje: 24. Januar 2026 (v300.6)

---

## 1. Pregled Projekta

**ServisHub** je multi-tenant SaaS platforma za servisna preduzeća (servisi telefona, računara, bele tehnike, itd.). Omogućava:

- Upravljanje servisnim nalozima sa garancijama
- Multi-lokacijski rad (više poslovnica)
- Inventar delova i telefona
- KYC verifikacija vlasnika servisa
- Billing sistem sa pretplatama
- Admin panel za platformu

---

## 2. Tehnički Stack

### Backend
| Komponenta | Tehnologija |
|------------|-------------|
| Framework | Flask (Python 3.x) |
| ORM | SQLAlchemy 2.x |
| Baza | PostgreSQL (Heroku) |
| Migracije | Flask-Migrate / Alembic |
| Auth | JWT (PyJWT) + bcrypt |
| OAuth | Google OAuth 2.0 sa PKCE |

### Frontend (Tenant App)
- Alpine.js za reaktivnost
- Tailwind CSS za stilizovanje
- Chart.js 4.4.0 za grafike na dashboardu
- CDN resursi (cloudflare, jsdelivr)
- Glass theme (glassmorphism) opcija

### Deployment
- Heroku (produkcija)
- Gunicorn WSGI server

---

## 3. Arhitektura Foldera

```
servishub/
├── app/
│   ├── __init__.py           # Flask app factory
│   ├── extensions.py         # db, migrate, bcrypt init
│   ├── models/               # SQLAlchemy modeli
│   │   ├── tenant.py         # Tenant, ServiceLocation, TenantStatus
│   │   ├── user.py           # TenantUser, UserRole
│   │   ├── admin.py          # PlatformAdmin, AdminRole
│   │   ├── representative.py # ServiceRepresentative, SubscriptionPayment
│   │   ├── tenant_message.py # TenantMessage
│   │   └── audit.py          # AuditLog, AuditAction
│   │
│   ├── api/                  # API Blueprints
│   │   ├── v1/               # Tenant API (servisi)
│   │   │   ├── auth.py       # Login, register, OAuth
│   │   │   └── ...
│   │   ├── admin/            # Platform Admin API
│   │   │   ├── auth.py       # Admin login sa 2FA
│   │   │   ├── scheduler.py  # Scheduler monitoring i kontrola
│   │   │   └── ...
│   │   └── middleware/
│   │       ├── jwt_utils.py  # JWT kreiranje/verifikacija
│   │       └── decorators.py # @tenant_required, @admin_required
│   │
│   ├── services/             # Business logic
│   │   ├── auth_service.py   # AuthService klasa
│   │   ├── security_service.py # Rate limiting
│   │   ├── billing_tasks.py  # BillingTasksService - scheduled billing operacije
│   │   ├── scheduler_service.py # APScheduler - automatsko pokretanje taskova
│   │   └── typing_service.py # Real-time typing indicators (in-memory, 3s TTL)
│   │
│   └── middleware/
│       └── security_headers.py # CSP, HSTS, X-Frame-Options
│
├── migrations/               # Alembic migracije
├── docs/                     # Dokumentacija
└── config.py                 # Konfiguracija
```

---

## 4. Modeli Podataka

### 4.1 Tenant (Preduzeće)

```python
class TenantStatus(enum.Enum):
    TRIAL = 'TRIAL'         # 60 dana FREE automatski nakon registracije
    ACTIVE = 'ACTIVE'       # Aktivna pretplata
    EXPIRED = 'EXPIRED'     # Istekla (grace period 7 dana)
    SUSPENDED = 'SUSPENDED' # Suspendovan (neplaćanje)
    CANCELLED = 'CANCELLED' # Otkazan nalog
    # DEMO - UKINUT (v102) - sada se odmah ide na TRIAL
```

**Ključna polja Tenant modela:**

| Polje | Tip | Opis |
|-------|-----|------|
| `id` | Integer | PK |
| `slug` | String(100) | Jedinstveni URL slug |
| `name` | String(200) | Naziv preduzeća |
| `pib` | String(20) | PIB (unique) |
| `email` | String(100) | Kontakt email |
| `status` | Enum | TenantStatus (default: TRIAL) |
| `trial_ends_at` | DateTime | Istek TRIAL perioda (60 dana od registracije) |
| `subscription_ends_at` | DateTime | Istek pretplate |

**Billing polja:**

| Polje | Tip | Opis |
|-------|-----|------|
| `current_debt` | Numeric(10,2) | Trenutno dugovanje (RSD) |
| `last_payment_at` | DateTime | Poslednja uplata |
| `days_overdue` | Integer | Broj dana kašnjenja |
| `blocked_at` | DateTime | Kada je blokiran |
| `block_reason` | String(200) | Razlog blokade |

**Trust Score sistem:**

| Polje | Tip | Opis |
|-------|-----|------|
| `trust_score` | Integer | 0-100 (viši = bolji) |
| `trust_activated_at` | DateTime | Kada aktivirao "na reč" |
| `trust_activation_count` | Integer | Ukupan broj aktivacija |
| `last_trust_activation_period` | String(7) | "2026-01" format |
| `consecutive_on_time_payments` | Integer | Uzastopne uplate na vreme |

**Trust nivoi:**
- 80-100: EXCELLENT
- 60-79: GOOD
- 40-59: WARNING
- 20-39: RISKY
- 0-19: CRITICAL

**Custom cene:**

| Polje | Tip | Opis |
|-------|-----|------|
| `custom_base_price` | Numeric(10,2) | NULL = platforma cena |
| `custom_location_price` | Numeric(10,2) | Cena dodatne lokacije |
| `custom_price_reason` | String(200) | Razlog za popust |

### 4.2 TenantUser (Korisnik servisa)

```python
class UserRole(enum.Enum):
    OWNER = 'OWNER'       # Vlasnik - pun pristup
    ADMIN = 'ADMIN'       # Admin - skoro pun pristup
    MANAGER = 'MANAGER'   # Menadžer lokacije
    TECHNICIAN = 'TECHNICIAN'  # Serviser
    RECEPTIONIST = 'RECEPTIONIST'  # Prijem
```

**Ključna polja:**
- `email` - unique globalno
- `password_hash` - bcrypt hash
- `google_id` - za OAuth korisnike
- `auth_provider` - 'email' ili 'google'
- `phone_verified` - SMS verifikacija

### 4.3 ServiceLocation (Lokacija)

- Preduzeće može imati više lokacija
- `is_primary` - prva lokacija (uključena u bazni paket)
- `has_separate_inventory` - poseban inventar po lokaciji
- `coverage_radius_km` - za B2C matching

### 4.4 SubscriptionPayment (Faktura)

```python
class PaymentStatus(enum.Enum):
    PENDING = 'PENDING'     # Čeka plaćanje
    PAID = 'PAID'           # Plaćeno
    OVERDUE = 'OVERDUE'     # Prekoračen rok
    CANCELLED = 'CANCELLED' # Stornirano
    REFUNDED = 'REFUNDED'   # Refundirano
```

**Ključna polja:**
- `invoice_number` - unique (format: SH-2026-00001)
- `period_start/end` - period pretplate
- `items_json` - JSON lista stavki
- `subtotal/total_amount` - iznosi
- `due_date` - rok plaćanja
- `paid_at` - kada plaćeno
- `payment_method` - BANK_TRANSFER, CARD, itd.
- `verified_by/at` - admin verifikacija

### 4.5 PlatformAdmin

```python
class AdminRole(enum.Enum):
    SUPER_ADMIN = 'SUPER_ADMIN'  # Sve privilegije
    ADMIN = 'ADMIN'              # Standardni admin
    SUPPORT = 'SUPPORT'          # Podrška
    BILLING = 'BILLING'          # Samo finansije
```

- Ima 2FA (`totp_secret`, `is_2fa_enabled`)
- `last_login_at`, `last_login_ip`

### 4.6 ServiceRepresentative (KYC)

- JMBG, broj lične karte
- Slike lične karte (front/back URL)
- Status: PENDING, VERIFIED, REJECTED
- Admin koji je verifikovao

### 4.7 AuditLog

- Loguje sve važne akcije
- `entity_type`, `entity_id`, `action`
- `changes` - JSON sa old/new vrednostima
- `ip_address`, `user_agent`

---

## 5. Autentifikacija

### 5.1 JWT Tokeni

**Access Token (15 min):**
```json
{
  "sub": 123,           // user_id
  "tenant_id": 1,
  "role": "OWNER",
  "type": "access",
  "iat": 1234567890,
  "exp": 1234568790
}
```

**Refresh Token (7 dana):**
```json
{
  "sub": 123,
  "tenant_id": 1,
  "type": "refresh",
  "iat": 1234567890,
  "exp": 1235172690
}
```

**Admin tokeni** imaju dodatno `is_admin: true`.

### 5.2 Login Flow (Tenant)

1. POST `/api/v1/auth/login` sa email/password
2. Provera korisnika u bazi
3. bcrypt.checkpw() verifikacija
4. Provera tenant statusa (SUSPENDED/CANCELLED blokira)
5. Generisanje access + refresh tokena
6. Audit log

### 5.3 OAuth Flow (Google)

1. Frontend dobija Google authorization code
2. POST `/api/v1/auth/google` sa code + state + code_verifier
3. Backend verifikuje sa Google API
4. Traži ili kreira TenantUser sa google_id
5. Generisanje tokena

**PKCE parametri:**
- `state` - CSRF zaštita
- `code_challenge` - SHA256 hash
- `code_verifier` - originalni random string
- `nonce` - replay attack zaštita

### 5.4 Admin Login sa 2FA

1. POST `/api/admin/auth/login` - email/password
2. Ako 2FA enabled: vraća `requires_2fa: true`
3. POST `/api/admin/auth/verify-2fa` - TOTP kod
4. Generisanje admin tokena

---

## 6. Sigurnosne Mere

### 6.1 Security Headers

```python
headers = {
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'SAMEORIGIN',
    'X-XSS-Protection': '1; mode=block',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'Permissions-Policy': 'camera=(), microphone=(), ...',
    'Content-Security-Policy': '...',  # Detaljno dole
    'Strict-Transport-Security': 'max-age=31536000; includeSubDomains'
}
```

**CSP Policy:**
- `default-src 'self'`
- `script-src 'self' 'unsafe-inline' 'unsafe-eval' googleapis, cloudflare, jsdelivr`
- `style-src 'self' 'unsafe-inline' fonts.googleapis`
- `img-src 'self' data: blob: cloudinary googleusercontent`
- `connect-src 'self' googleapis cloudinary`
- `frame-src 'self' accounts.google.com`

### 6.2 Rate Limiting

```python
class RateLimits:
    LOGIN = {'requests': 5, 'window': 300}      # 5 req / 5 min
    REGISTER = {'requests': 3, 'window': 3600}  # 3 req / 1 sat
    API = {'requests': 100, 'window': 60}       # 100 req / 1 min
```

**⚠️ SECURITY GAP:**
- Admin login IMA rate limiting
- Tenant login NEMA rate limiting!

### 6.3 Password Hashing

```python
# Hashing
salt = bcrypt.gensalt()
password_hash = bcrypt.hashpw(password.encode(), salt)

# Verifikacija
bcrypt.checkpw(password.encode(), stored_hash)
```

### 6.4 Audit Logging

Sve važne akcije se loguju:
- LOGIN, LOGIN_FAILED
- CREATE, UPDATE, DELETE
- VERIFY, REJECT (KYC)
- BLOCK, UNBLOCK (tenant)

### 6.5 Security Event Logging (v239-v240)

**Lokacija:** `app/services/security_service.py`, `app/models/security_event.py`

Kompletan sistem za logovanje bezbednosnih dogadjaja sa tenant tracking-om:

```python
class SecurityEvent(db.Model):
    event_type = db.Column(db.String(50), index=True)   # login_success, oauth_failed...
    severity = db.Column(db.String(20))                  # info, warning, error, critical
    user_id = db.Column(db.Integer, nullable=True)
    tenant_id = db.Column(db.Integer, index=True)        # Multi-tenant tracking
    ip_address = db.Column(db.String(45), index=True)
    created_at = db.Column(db.DateTime(timezone=True))
```

**Svrha:**
- Detekcija brute-force napada
- Monitoring rate limit prekoracenja
- Analiza bezbednosti po tenantu (servisu)
- Pregled u Admin Panel (`/admin/security/events`)

**Eventi koji se loguju:**
| Event | Opis |
|-------|------|
| `login_success` | Uspesna prijava (email/OAuth) |
| `login_failed` | Neuspesna prijava |
| `logout` | Odjava korisnika |
| `oauth_*` | OAuth flow eventi |
| `rate_limit_exceeded` | Prekoracen rate limit |
| `brute_force_detected` | Detektovan napad |

**Admin Panel Features:**
- Filtriranje po IP, tenant_id, event_type, severity
- Statistike: top IP adrese, failed logins, rate limits
- Prikaz tenant imena pored ID-a

---

## 7. Billing Sistem

### 7.1 Lifecycle Tenanta (v102 - pojednostavljen)

```
[REGISTRACIJA]
      |
      v
   TRIAL (60 dana FREE) ◄── automatski, bez DEMO faze
      |
      v (uplata pre isteka)
   ACTIVE
      |
      v (istekla pretplata)
   EXPIRED (7 dana grace period)
      |
      v (neplaćanje)
   SUSPENDED
      |
      +---> "Na reč" (48h) ---> nazad na SUSPENDED (ako ne plati)
      |
      v (trajna blokada)
   CANCELLED
```

> **NAPOMENA (v102):** DEMO status je ukinut. Registracija odmah kreira TRIAL
> sa 60 dana besplatnog korišćenja. Postojeći DEMO tenanti su migrirani.

### 7.2 Trust Score Sistem

**Povećanje (+):**
- Plaćanje na vreme: +5
- Uzastopna plaćanja: +2 bonus
- Dugo aktivni: +1/mesec

**Smanjenje (-):**
- Kašnjenje 1-7 dana: -5
- Kašnjenje 8-14 dana: -10
- Kašnjenje 15-30 dana: -20
- Korišćenje "na reč": -15
- Neuspela "na reč": -25

### 7.3 "Na Reč" Aktivacija

- Dostupno SAMO iz SUSPENDED statusa
- Maksimum 1x mesečno
- Traje 48 sati
- Trust score se smanjuje za -15
- Ako ne plati u 48h: dodatnih -25

```python
# Provera
if tenant.can_activate_trust:
    tenant.activate_trust()
    # tenant.is_trust_active == True (48h)
```

### 7.4 Custom Cene

Admin može postaviti custom cene za određeni tenant:
- `custom_base_price` - umesto platformske
- `custom_location_price` - za dodatne lokacije
- `custom_price_reason` - dokumentacija
- `custom_price_valid_from` - od kog datuma

---

## 8. API Endpoints

### 8.1 Tenant Auth (`/api/v1/auth`)

| Method | Endpoint | Opis |
|--------|----------|------|
| POST | `/register` | Registracija novog servisa |
| POST | `/login` | Email/password login |
| POST | `/google` | Google OAuth login |
| POST | `/refresh` | Refresh tokena |
| POST | `/send-verification` | Slanje email verifikacije |
| POST | `/verify-email` | Potvrda email-a |
| POST | `/send-otp` | Slanje SMS OTP-a |
| POST | `/verify-otp` | Verifikacija SMS-a |

### 8.2 Admin Auth (`/api/admin/auth`)

| Method | Endpoint | Opis |
|--------|----------|------|
| POST | `/login` | Admin login |
| POST | `/verify-2fa` | 2FA verifikacija |
| POST | `/refresh` | Refresh admin tokena |
| POST | `/setup-2fa` | Inicijalizacija 2FA |
| POST | `/enable-2fa` | Aktivacija 2FA |

### 8.3 Subscription (planirati)

| Method | Endpoint | Opis |
|--------|----------|------|
| GET | `/api/v1/subscription` | Trenutna pretplata |
| GET | `/api/v1/subscription/invoices` | Lista faktura |
| GET | `/api/v1/subscription/invoice/:id` | Detalji fakture |
| POST | `/api/v1/subscription/activate-trust` | "Na reč" aktivacija |

### 8.4 Dashboard Stats (`/api/v1`)

| Method | Endpoint | Opis |
|--------|----------|------|
| GET | `/tickets/stats/trend` | Trend servisnih naloga (primljeno, završeno, naplaćeno) |
| GET | `/inventory/phones/stats/trend` | Trend telefona (dodato, prodato, zarada) |

**Query parametri:**
- `days` - Broj dana (7, 30, 90, 365). Default: 30

**Response format:**
```json
{
  "dates": ["01.01", "02.01", ...],
  "day_names": ["Pon", "Uto", ...],
  "received": [1, 2, ...],
  "completed": [1, 0, ...],
  "collected": [0, 1, ...]
}
```

### 8.5 Admin Payments (planirati)

| Method | Endpoint | Opis |
|--------|----------|------|
| GET | `/api/admin/payments` | Lista svih uplata |
| POST | `/api/admin/payments/:id/verify` | Verifikuj uplatu |
| POST | `/api/admin/tenants/:id/block` | Blokiraj tenant |
| POST | `/api/admin/tenants/:id/unblock` | Odblokiraj |

---

## 9. Tenant Metode

```python
# Properties
tenant.is_active          # TRIAL/ACTIVE
tenant.days_remaining     # Preostalo dana
tenant.has_debt           # current_debt > 0
tenant.is_blocked         # SUSPENDED + has_debt
tenant.trust_level        # EXCELLENT/GOOD/WARNING/RISKY/CRITICAL
tenant.can_activate_trust # Da li može "na reč"
tenant.is_trust_active    # Da li je u 48h periodu
tenant.trust_hours_remaining  # Preostalo sati

# Metode
tenant.set_trial(trial_days=60)    # Postavlja TRIAL status
tenant.activate_subscription(months=1)
tenant.activate_trust()
tenant.update_trust_score(change, reason)
tenant.block(reason)
tenant.unblock()
tenant.get_subscription_info()  # Dict za API

# DEPRECATED (v102)
tenant.set_demo()  # -> poziva set_trial() interno
```

---

## 10. Poznati Problemi / TODO

### ✅ Rešeni Sigurnosni Problemi

1. **Rate Limiting na Auth Endpoints** - REŠENO
   - `/api/v1/auth/login` - 5 req/60s, block 300s
   - `/api/v1/auth/register` - 3 req/sat, block 1h
   - `/api/v1/auth/send-otp` - 3 req/10min, block 30min (SMS!)
   - `/api/v1/auth/send-verification-email` - 5 req/5min, block 10min
   - `/api/v1/auth/resend-verification-email` - 3 req/5min, block 10min

### ✅ Billing Sistem - KOMPLETNO

1. ✅ Tenant model - billing polja
2. ✅ SubscriptionPayment model
3. ✅ TenantMessage model
4. ✅ API endpoints za subscription (`/api/v1/tenant/subscription`)
5. ✅ Admin payments endpoints (`/api/admin/payments`)
6. ✅ Tenant UI - subscription stranica (debt, trust score, "na reč")
7. ✅ Tenant sidebar - status badge
8. ✅ Rate limiting na sve auth endpointe
9. ✅ Cron job za proveru isteklih pretplata
10. ✅ Email notifikacije za dugovanja

### 🤖 In-App Scheduler (APScheduler) - NOVO v102

Billing taskovi se sada pokreću **automatski** unutar aplikacije pomoću APScheduler-a.
Nema potrebe za Heroku Scheduler addon-om.

**Scheduler Jobs:**

| Job ID | Raspored | Opis |
|--------|----------|------|
| `billing_daily` | Svaki dan u 06:00 UTC | Proverava pretplate, grace periode, dugovanja |
| `generate_invoices` | 1. u mesecu u 00:00 UTC | Generiše mesečne fakture |
| `send_reminders` | Svaki dan u 10:00 UTC | Šalje email podsetnice (3, 7, 14 dana) |

**Admin API Endpoints:**

```
GET  /api/admin/scheduler/status      # Status schedulera i svih jobova
POST /api/admin/scheduler/run/<job_id> # Manuelno pokretanje joba
```

**Primer response-a:**
```json
{
  "running": true,
  "jobs": [
    {
      "id": "billing_daily",
      "name": "Dnevne billing provere",
      "next_run": "2026-01-18T06:00:00",
      "trigger": "cron[hour='6', minute='0']"
    }
  ]
}
```

### 🔧 CLI Komande za Billing (backup/debug)

CLI komande i dalje postoje za manuelno pokretanje i debugging:

```bash
# Dnevni task - pokrece sve billing provere
flask billing-daily

# Individualne komande
flask check-subscriptions     # Proverava istekle pretplate
flask process-trust-expiry    # Procesira "na rec" periode
flask generate-invoices       # Generise mesecne fakture (1. u mesecu)
flask mark-overdue           # Oznacava prekoracene fakture
flask update-overdue-days    # Azurira dane kasnjenja

# Email notifikacije
flask send-billing-emails --type=reminders  # Podsecanja (3, 7, 14 dana)
flask send-billing-emails --type=warnings   # Upozorenja o suspenziji

# Migracija starih DEMO tenanta (jednokratno)
flask migrate-demo-to-trial   # Prebacuje DEMO -> TRIAL (60 dana)
```

### 📧 Billing Email Tipovi

| Email | Kada se šalje |
|-------|---------------|
| Nova faktura | Generisanje fakture |
| Podsetnik | 3, 7, 14 dana kasnjenja |
| Upozorenje o suspenziji | 2 dana pre suspenzije |
| Obavestenje o suspenziji | Kada se suspenduje |
| Potvrda uplate | Kada admin verifikuje uplatu |

---

## 11. Konfiguracija

### Environment Variables

```bash
DATABASE_URL=postgresql://...
SECRET_KEY=...
JWT_SECRET_KEY=...

# Google OAuth
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...

# Cloudinary (LK slike)
CLOUDINARY_URL=...

# Email
MAIL_SERVER=...
MAIL_USERNAME=...
MAIL_PASSWORD=...

# SMS (Twilio/Infobip)
SMS_API_KEY=...
```

### JWT Config

```python
JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)
JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=7)
```

---

## 12. Migracije

Kad dodaješ nova polja:

```bash
# Kreiraj migraciju
flask db migrate -m "Add billing fields to tenant"

# Primeni lokalno
flask db upgrade

# Na Heroku
heroku run flask db upgrade
```

---

## 13. Quick Reference

### Kreiranje Tenant-a (registracija)

```python
auth_service.register_tenant(
    company_name="Moj Servis",
    company_email="info@mojservis.rs",
    pib="123456789",
    owner_email="vlasnik@mojservis.rs",
    owner_password="securepass",
    owner_ime="Petar",
    owner_prezime="Petrović",
    location_name="Glavna radnja",
    location_city="Beograd"
)
# Rezultat: (tenant, owner) - TRIAL status, 60 dana FREE
```

### Login

```python
user, tenant, tokens = auth_service.login(email, password)
# tokens = {access_token, refresh_token, expires_in}
```

### Blokiranje Tenanta

```python
tenant.block("Neplaćena faktura SH-2026-00015")
db.session.commit()
```

### Aktivacija "Na Reč"

```python
if tenant.can_activate_trust:
    tenant.activate_trust()
    db.session.commit()
    # 48 sati pristupa
```

---

## 14. Changelog

### v243 (Planirano) - Messaging & Networking System v2.1

**Status:** PLANIRANO - Čeka implementaciju

**Enterprise-grade implementacija sa:**
- Race-safe verzioniranje (`create_with_version()` sa retry)
- Per-tenant delivery tracking (`PackageChangeDelivery`)
- UTC storage + Europe/Belgrade za prikaz
- Threaded conversations sa SLA tracking
- SYSTEM threads read-only (API enforced)
- Secure invite sistem (hashed tokens + token_hint)
- 2-step approval za networking
- BLOCKED auto-blocks sve komunikacije
- Granularne dozvole (can_message/share/order)
- Full audit trail (edited_by_type, hidden_by_type)
- Fixed mutable default bugs

**Novi modeli:**
| Model | Opis |
|-------|------|
| `PackageChangeHistory` | Verzioniranje promena cena + idempotency |
| `PackageChangeDelivery` | Per-tenant tracking dostave notifikacija |
| `MessageThread` | Threaded conversations (SYSTEM/SUPPORT/NETWORK) |
| `ThreadParticipant` | Učesnici sa last_read_at (unread kao cache) |
| `Message` | Poruke sa edit/hide audit trail |
| `Invite` | Secure invite tokens (SHA-256 hash + hint) |
| `TenantConnection` | T2T veze sa granularnim dozvolama |

**Kritični fajlovi (planirani):**
- `app/models/package_change_history.py` - NOVI
- `app/models/message_thread.py` - NOVI
- `app/models/invite.py` - NOVI
- `app/models/tenant_connection.py` - NOVI
- `app/api/v1/threads.py` - NOVI
- `app/api/v1/connections.py` - NOVI
- `app/templates/tenant/messages/` - NOVI (2 taba UI)
- `app/templates/tenant/network/` - NOVI

**Plan fajl:** `C:\Users\darko\.claude\plans\nested-giggling-wall.md`

---

### v300.6 (24. Januar 2026)

**Sidebar Optimization - SessionStorage Caching + Skeleton Loader:**

**Problem:** Sidebar učitava podatke sa API-ja na svakoj promeni stranice, što uzrokuje:
- Flickering license widget-a (pojavi se posle sekunde)
- "Tim" menu item "iskače" (FOUC - Flash of Unstyled Content)
- Nepotrebni API pozivi pri navigaciji

**Rešenja:**

1. **SessionStorage Caching (5min TTL)**
   - Cache key: `servishub_sidebar_cache`
   - Keširani podaci: tenantName, userRole, subscriptionStatus, daysRemaining, locationCount, totalDays
   - Na page load: prvo učita iz cache-a (instant), zatim osvežava iz API-ja ako je cache istekao
   - TTL: 5 minuta - balans između svežih podataka i performansi

2. **Skeleton Loader za License Widget**
   - Prikazuje se dok se podaci ne učitaju
   - Pulsing animacija (`skeleton-pulse`)
   - `subscriptionLoaded` flag kontroliše skeleton/widget vidljivost

3. **FOUC Fix za Tim Menu**
   - `roleLoaded` flag - čeka da API vrati userRole
   - `isAdmin()` vraća `false` dok `roleLoaded` nije `true`
   - Kombinacija sa `x-cloak` sprečava "pop-in" efekat

**Loading Flow:**
```
First visit:     Skeleton → API → Cache → Widget
Subsequent:      Cache → Widget instantly → (API refresh if >5min)
```

**Izmenjeni fajlovi:**
- `app/templates/components/tenant_sidebar.html` - caching + skeleton

---

### v297 (24. Januar 2026)

**Real-Time Messaging System - Typing Indicators + Fast Polling:**

**Problem:** Kad admin odgovori na poruku, tenant mora da refreshuje stranicu da vidi odgovor. Nema indikacije da neko kuca.

**Rešenja:**

1. **Typing Service** (`app/services/typing_service.py`):
   - In-memory storage za typing status
   - Automatsko istekanje posle 3 sekunde
   - Shared između admin i tenant API-ja
   - Format: `{thread_id: {user_key: {'name': 'Ime', 'type': 'admin'|'tenant', 'expires': timestamp}}}`

2. **API Endpoints (oba panela):**
   - `POST /threads/{id}/typing` - šalje typing status (`{typing: true/false}`)
   - `GET /threads/{id}/typing` - dohvata ko kuca (exclude self)
   - `after_id` param na messages endpoint za efikasan polling

3. **Admin Support UI** (`/admin/support`):
   - Nova stranica za admin chat sa tenantima
   - Listing svih SUPPORT threadova
   - Real-time chat sa typing indikatorom
   - Sidebar link "Podrška" u admin panelu

4. **Frontend Real-Time Features:**
   - Polling novih poruka svake 3 sekunde (koristi `after_id`)
   - Polling typing statusa svake 2 sekunde
   - Animirani typing dots (`.typing-dots span` sa bounce animacijom)
   - Auto-scroll na nove poruke
   - `@input="onTyping()"` na textarea za detekciju kucanja

**Kako radi flow:**
```
┌─────────────────────────────────────────────────────────────┐
│  TENANT KUCA                          ADMIN VIDI            │
│  ──────────────                       ─────────────         │
│  1. Korisnik kuca u textarea          1. pollTyping() svakih│
│  2. onTyping() detektuje              2. GET /typing vraća  │
│  3. POST /typing {typing:true}           [{name:'Petar',    │
│  4. typing_service čuva 3s               type:'tenant'}]    │
│  5. Timeout nakon 2s neaktivnosti     3. Prikazuje animaciju│
│     šalje {typing:false}                 "Petar kuca..."    │
└─────────────────────────────────────────────────────────────┘
```

**Izmenjeni fajlovi:**
- `app/services/typing_service.py` - NOVO
- `app/api/v1/threads.py` - typing endpoints, `after_id`
- `app/api/admin/threads.py` - typing endpoints, `after_id`
- `app/templates/admin/support/list.html` - NOVO (admin chat UI)
- `app/templates/admin/_sidebar.html` - dodat "Podrška" link
- `app/frontend/admin.py` - dodata `/admin/support` ruta
- `app/templates/tenant/messages/inbox.html` - real-time polling

**Typing Indicator CSS:**
```css
.typing-dots span {
    width: 6px; height: 6px;
    background: #94a3b8;
    border-radius: 50%;
    animation: typingBounce 1.4s infinite ease-in-out;
}
@keyframes typingBounce {
    0%, 60%, 100% { transform: translateY(0); }
    30% { transform: translateY(-4px); }
}
```

---

### v241 (23. Januar 2026)

**Role-Based Access Control za Tim:**

**Problem:** Korisnici sa ulogom TECHNICIAN i RECEPTIONIST mogli su da vide "Tim" u sidebar-u i pristupe team management funkcijama.

**Rešenja:**

1. **Sidebar - Sakrivanje "Tim" linka:**
   - Dodat `x-show="isAdmin()"` na "Tim" link u sidebar-u
   - Nova `isAdmin()` metoda proverava da li je uloga OWNER, ADMIN ili MANAGER
   - Dodato `userRole` state polje u `sidebarData()`

2. **API Zaštita (users.py):**
   - `GET /users` - Samo OWNER/ADMIN/MANAGER mogu videti listu
   - `GET /users/:id` - Non-admin može videti samo svoj profil
   - `PUT /users/:id` - Samo OWNER/ADMIN/MANAGER mogu menjati profile

**Synchronous OAuth Token Handling (kritični fix):**

**Problem:** Google OAuth login nije radio - posle Google autentifikacije, aplikacija je odmah izlazila. Race condition: Alpine.js komponente su pokretale API pozive pre nego što su OAuth tokeni sačuvani u localStorage.

**Rešenje:**
- Implementiran **sinhroni XMLHttpRequest** u `<head>` sekciji tenant.html
- Blokira SVE učitavanje stranice dok se tokeni ne preuzmu
- Izvršava se PRE nego što se Alpine.js inicijalizuje
- Nakon uspešnog preuzimanja tokena, redirect na čist URL (bez ?auth=oauth)

**Kod (tenant.html <head>):**
```javascript
(function() {
    'use strict';
    const urlParams = new URLSearchParams(window.location.search);
    const authMethod = urlParams.get('auth');

    if (authMethod === 'oauth') {
        const xhr = new XMLHttpRequest();
        xhr.open('GET', '/api/v1/auth/google/tokens', false);  // false = sinhrono
        xhr.withCredentials = true;
        xhr.send();

        if (xhr.status === 200) {
            const data = JSON.parse(xhr.responseText);
            localStorage.setItem('access_token', data.access_token);
            if (data.refresh_token) {
                localStorage.setItem('refresh_token', data.refresh_token);
            }
            window.location.replace(window.location.pathname);
        } else {
            window.location.replace('/login?error=oauth_token_' + xhr.status);
        }
    }
})();
```

**Izmenjeni fajlovi:**
- `app/templates/components/tenant_sidebar.html` - role-based Tim visibility
- `app/api/v1/users.py` - admin role checks za team management
- `app/templates/layouts/tenant.html` - synchronous OAuth token handler

---

### v173 (19. Januar 2026)

**Wildcard Subdomain - Kompletna infrastruktura:**

**Heroku Configuration:**
- Dodata wildcard domena `*.servishub.rs` na Heroku app `servicehubdolce`
- Komanda: `heroku domains:add "*.servishub.rs" -a servicehubdolce`
- DNS Target: `shallow-chinchilla-m9h0ogbc3nyistsb36tddywe.herokudns.com`
- ACM automatski generise SSL sertifikate za sve subdomene

**Cloudflare DNS:**
- Dodat CNAME zapis: `*` → herokudns target
- Proxy status: OFF (gray cloud) - obavezno za Heroku ACM

**Kompletna DNS tabela:**
| Domain | Type | Target | SSL |
|--------|------|--------|-----|
| `servishub.rs` | ALIAS | systematic-bean-...herokudns.com | ✅ ACM |
| `www.servishub.rs` | CNAME | calm-mamenchisaurus-...herokudns.com | ✅ ACM |
| `*.servishub.rs` | CNAME | shallow-chinchilla-...herokudns.com | ✅ ACM |

**Bug Fix - savePublicProfile():**
- Problem: Pydantic validation error `working_hours.mon_closed Input should be a valid string`
- Uzrok: `working_hours` se slao u form formatu umesto API formata
- Resenje: Eksplicitna konverzija u `savePublicProfile()` PRE sanitizacije
- `sanitizePublicProfile()` sada proverava da li je vec konvertovano

**Izmenjeni fajlovi:**
- `app/templates/tenant/settings/index.html` - savePublicProfile() fix

**Azurirana dokumentacija:**
- `CLAUDE.md` - v0.6.1
- `docs/PUBLIC_SITE_DOCUMENTATION.md` - v1.2.0 changelog, DNS tabela
- `docs/MASTER_SUMMARY.md` - v173 changelog

---

### v172 (19. Januar 2026)

**Public Site Routing Fix - kritične popravke:**

**Route Deduplication:**
- Objedinjena `/` ruta u `frontend/public.py`
- Landing funkcija sada detektuje `g.is_public_site` i prikazuje odgovarajući template
- Uklonjena duplikat ruta iz `tenant_public.py`

**Working Hours Format Fix:**
- Dodata `formatWorkingHoursForApi()` funkcija u settings JS
- Konvertuje form format (`mon_open`, `mon_close`, `mon_closed`) u API format (`mon: "09:00-17:00"`)
- Ažurirana `sanitizePublicProfile()` da poziva konverziju

**SQLAlchemy JSON Fields:**
- Dodat `flag_modified()` za JSON polja u API
- Polja: `working_hours`, `why_us_items`, `gallery_images`, `testimonials`
- Osigurava da SQLAlchemy pravilno detektuje promene u JSON vrednostima

**Izmenjeni fajlovi:**
- `app/frontend/public.py` - objedinjena landing logika
- `app/frontend/tenant_public.py` - uklonjena duplikat `/` ruta
- `app/templates/tenant/settings/index.html` - `formatWorkingHoursForApi()`, `sanitizePublicProfile()`
- `app/api/v1/tenant.py` - `flag_modified()` za JSON

**Ažurirana dokumentacija:**
- `docs/PUBLIC_SITE_DOCUMENTATION.md` - v1.1.0 changelog, Working Hours Format sekcija

---

### v163-v164 (18. Januar 2026)

**UI/UX Performance Optimizacije - eliminacija trzanja:**

**FOUC Prevention (v163):**
- Promenjeno sa `visibility: hidden` na `opacity: 0` sa smooth transition
- Uklonjen `translateY(-10px)` iz fadeIn animacije (uzrokovao layout shift)
- Dodat `prefers-reduced-motion` media query za accessibility
- Shimmer animacija optimizovana: sa infinite 5s na one-time 1.5s
- Dodat `content-visibility: auto` CSS class za performance

**Alpine.js Optimizacije (v163):**
- Dodat `x-cloak` na root element u tenant.html
- Dodat `x-cloak` na settings page root
- Dodati `x-transition:enter` na sve glavne tabove u settings (7 tabova)
- Dodati `x-transition:enter` na sve pod-tabove u "Javna Stranica" (8 tabova)

**Loading Skeletons (v164):**
- Dashboard: skeleton loading za sve 4 stat kartice
- Tickets: skeleton loading za tabelu (5 skeleton redova)
- Dodat skeleton CSS sa glass theme podrškom

**Chart.js Theming (v164):**
- Tooltips sada koriste theme-aware boje
- Glass tema: tamna pozadina tooltipa sa svetlim tekstom
- Light tema: bela pozadina sa tamnim tekstom

**Nova dokumentacija:**
- Kreiran `docs/UI_UX_PERFORMANCE.md` - kompletan vodič za UI/UX optimizacije

**Izmenjeni fajlovi:**
- `app/templates/layouts/base.html` - FOUC, animations, reduced motion
- `app/templates/layouts/tenant.html` - x-cloak
- `app/templates/tenant/settings/index.html` - tab transitions
- `app/templates/tenant/dashboard.html` - skeletons, chart tooltips
- `app/templates/tenant/tickets/list.html` - skeletons

---

### v156-v158 (18. Januar 2026)

**Dashboard Charts - Kompletna implementacija:**
- Dodata Chart.js 4.4.0 biblioteka za grafike
- Novi API endpoint: `GET /api/v1/tickets/stats/trend` - trend servisnih naloga
- Novi API endpoint: `GET /api/v1/inventory/phones/stats/trend` - trend telefona
- Line chart za servisne naloge: Primljeno, Završeno, Naplaćeno
- Line chart za telefone: Dodato, Prodato
- Srpska imena dana ispod datuma (Pon, Uto, Sre, Čet, Pet, Sub, Ned)
- Period selektor za oba charta: 7 dana, 30 dana, Kvartal (90), Godina (365)
- Podrška za Light i Glass teme

**Izmenjeni fajlovi:**
- `app/templates/tenant/dashboard.html` - dodati chartovi sa selektorima
- `app/api/v1/tickets.py` - dodat `/stats/trend` endpoint
- `app/api/v1/inventory.py` - dodat `/phones/stats/trend` endpoint

---

### v139-v149 (17-18. Januar 2026)

**Subscription Widget u Sidebar-u:**
- License-style widget sa guilloche pattern pozadinom
- Shimmer animacija (45 stepeni, 5s interval)
- Prikaz statusa: Trial/Standard/Na reč
- Prikaz broja lokacija
- Preostali dani sa progress barom
- Poseban stil za GRACE period (žuta boja)

**Izmenjeni fajlovi:**
- `app/templates/components/tenant_sidebar.html` - dodat subscription widget
- `app/templates/layouts/base.html` - dodati CSS stilovi za widget

---

### v136-v138 (17. Januar 2026)

**UI/UX poboljšanja:**
- Fix FOUC (Flash of Unstyled Content) - `theme-ready` CSS klasa
- Settings stranica - preuređeni tabovi, tema na prvom mestu
- Sidebar dropdown perzistencija
- Google OAuth timing fix

**Izmenjeni fajlovi:**
- `app/templates/layouts/base.html` - FOUC fix
- `app/templates/tenant/settings/index.html` - tab reorder
- `app/templates/components/tenant_sidebar.html` - dropdown fix

---

### v130-v135 (16-17. Januar 2026)

**Theme sistem:**
- Light/Dark tema toggle u settings
- Glass theme (glassmorphism) opcija
- CSS varijable za teme (`--glass-bg`, `--glass-card`, itd.)
- Poboljšan modal za servisne naloge

**JWT fix:**
- Ispravljen problem sa tenant podacima - dodat `g.tenant_id` i `g.user_id`

**Tickets fix:**
- Ispravljen bug: API vraća `items`, frontend očekivao `tickets`

**Izmenjeni fajlovi:**
- `app/templates/layouts/base.html` - glass theme CSS
- `app/templates/tenant/settings/index.html` - theme toggle
- `app/api/middleware/jwt_utils.py` - JWT fix
- `app/templates/tenant/tickets/list.html` - data.items fix

---

### v103 (17. Januar 2026)

**Admin Paketi stranica - redizajn:**
- Kompletno redizajnirana `/admin/paketi` stranica
- Uklonjen DEMO period input i sve reference
- Dodat vizuelni Lifecycle Flow dijagram (Registracija → TRIAL → ACTIVE → EXPIRED → SUSPENDED)
- Nove pricing kartice sa hover efektima i ikonama
- Dodat Price Calculator (automatski računa cene za 1-5 lokacija)
- Poboljšan Periodi sekcija (samo Trial i Grace period)
- Marketplace provizija sekcija sa ljubičastim dizajnom

**API izmene:**
- `GET /api/admin/settings/packages` - uklonjen `demo_days` iz response-a
- Default `trial_days` promenjen na 60 (umesto 90)
- `UpdateSettingsRequest` - uklonjen `demo_days` parametar

**Izmenjeni fajlovi:**
- `app/templates/admin/packages/index.html` - kompletno redizajniran
- `app/api/admin/settings.py` - uklonjen demo_days

---

### v102 (17. Januar 2026)

**Ukinut DEMO status - pojednostavljen lifecycle:**
- Registracija sada direktno kreira TRIAL status (60 dana FREE)
- DEMO faza potpuno uklonjena
- Migrirana 2 postojeća DEMO tenanta (Tritel, TEST SERVIS)
- Nova CLI komanda: `flask migrate-demo-to-trial`

**In-App Scheduler (APScheduler):**
- Novi fajl: `app/services/scheduler_service.py`
- Automatsko pokretanje billing taskova bez Heroku Scheduler-a
- 3 scheduled joba: billing_daily (06:00), generate_invoices (1. u mesecu), send_reminders (10:00)
- Admin API za monitoring: `GET /api/admin/scheduler/status`
- Admin API za manuelno pokretanje: `POST /api/admin/scheduler/run/<job_id>`

**Izmenjeni fajlovi:**
- `app/models/tenant.py` - default status TRIAL, set_trial() metoda
- `app/services/auth_service.py` - registracija kreira TRIAL
- `app/services/billing_tasks.py` - uklonjena DEMO logika
- `app/__init__.py` - scheduler inicijalizacija, migrate-demo-to-trial CLI
- `app/api/admin/__init__.py` - dodato scheduler
- `app/api/admin/scheduler.py` - NOVO: admin endpoints za scheduler
- `requirements.txt` - dodat APScheduler==3.10.4

---

*Generisano: 19. Januar 2026*