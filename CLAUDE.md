# CLAUDE.md - ServisHub SaaS Platform

## Pregled Projekta

ServisHub je SaaS platforma za servise mobilnih telefona i racunara.
Izdvojen iz Dolce Vita ERP sistema kao standalone proizvod.

### Kljucne Funkcionalnosti
- **B2B:** Servisni nalozi, garancije, inventar, marketplace za delove
- **B2C:** Javni portal za krajnje kupce, licitacije, zahtevi za servisom
- **Dobavljaci:** Katalog delova sa 5% provizijom
- **Platform Admin:** Upravljanje celim ekosistemom

### Tech Stack
- Backend: Python 3.11 + Flask 3.x + SQLAlchemy 2.0
- Database: PostgreSQL 15 (Railway managed)
- Cache/Queue: Redis + Celery
- Frontend: Tailwind CSS + Alpine.js + Jinja2
- Auth: JWT (PyJWT) + Refresh tokens
- Hosting: Railway

---

## Arhitektura

### Multi-Tenancy
- Row-level security sa `tenant_id` na svim tabelama
- Automatski filter u middleware-u (`g.current_tenant`)
- Tenant = jedan servis (firma)

### Modeli
- `Tenant` - servisna radnja (preduzece)
- `ServiceLocation` - lokacija servisa (preduzece moze imati vise)
- `TenantUser` - korisnik (pripada tenantu)
- `ServiceTicket` - servisni nalog sa garancijom
- `PhoneListing` - telefon na lageru
- `SparePart` - rezervni deo (visibility: PRIVATE/PARTNER/PUBLIC)
- `Supplier` - dobavljac delova
- `SupplierListing` - artikl dobavljaca
- `ServiceRepresentative` - KYC predstavnik servisa
- `AuditLog` - sve promene
- `PartOrder` - narudzbina od dobavljaca/partnera
- `PartOrderMessage` - komunikacija oko narudzbine

### API Struktura
- `/api/v1/*` - B2B API (JWT required, tenant-scoped)
- `/api/public/*` - B2C API (bez auth, za kupce)
- `/api/admin/*` - Platform Admin API (admin JWT, full access)

### Domeni
- `servishub.rs` - Landing page
- `app.servishub.rs` - Tenant panel (servisi)
- `admin.servishub.rs` - Platform Admin panel (mi)
- `supplier.servishub.rs` - Supplier panel (dobavljaci)

---

## Komande

### Lokalni razvoj
```bash
cd C:\servishub
python -m venv venv
venv\Scripts\activate
pip install -r requirements-dev.txt
flask db upgrade
flask run --debug
```

### Migracije
```bash
flask db migrate -m "Opis izmene"
flask db upgrade
```

### Testovi
```bash
pytest tests/ -v
pytest tests/unit/ -v --cov=app
```

### Celery worker (lokalno)
```bash
celery -A app.tasks.celery_app worker --loglevel=info
```

---

## Environment Variables (.env)

```
FLASK_ENV=development
SECRET_KEY=your-secret-key
JWT_SECRET_KEY=your-jwt-secret
JWT_ACCESS_TOKEN_EXPIRES=900
JWT_REFRESH_TOKEN_EXPIRES=2592000

DATABASE_URL=postgresql://user:pass@localhost:5432/servishub
REDIS_URL=redis://localhost:6379/0

CLOUDINARY_URL=cloudinary://api_key:api_secret@cloud_name

# Railway production
RAILWAY_ENVIRONMENT=production
```

---

## Coding Standards

### Komentarisanje Koda

**Pravilo:** Svaki fajl, klasa, funkcija i kompleksna logika MORA imati kratak, koncizan komentar na SRPSKOM jeziku (latinica).

#### Primer - Model
```python
"""
Servisni nalog - glavni entitet za pracenje popravki.
Sadrzi podatke o kupcu, uredjaju, statusu i garanciji.
"""
class ServiceTicket(db.Model):
    __tablename__ = 'service_ticket'

    # Primarni kljuc - globalno jedinstven
    id = db.Column(db.BigInteger, primary_key=True)

    # Veza sa preduzecem - obavezno za multi-tenant izolaciju
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
```

#### Primer - API Endpoint
```python
@bp.route('/tickets', methods=['GET'])
@jwt_required
@tenant_required
def list_tickets():
    """
    Lista servisnih naloga za trenutno preduzece.
    Filtrira po lokacijama koje korisnik ima pravo da vidi.
    """
    # Dohvati lokacije koje korisnik sme da vidi
    allowed_locations = get_user_locations(g.current_user)
    ...
```

### Opsta Pravila

1. **Jezik komentara:** SRPSKI (latinica)
2. **Docstring:** Svaka funkcija ima docstring sa opisom, parametrima i return
3. **Inline komentari:** Za kompleksnu logiku, kratko objasnjenje STA i ZASTO
4. **Imenovanje:** Opisna imena varijabli i funkcija na engleskom
5. **TODO:** Oznaci sa `# TODO:` stvari koje treba doraditi

---

## Vazne Napomene

### Garancije
- Default warranty_days iz `tenant.settings_json`
- Moze se menjati po nalogu
- warranty_expires_at = closed_at + warranty_days
- Property `warranty_remaining_days` za prikaz

### Audit Log
- SVE promene se loguju automatski
- SQLAlchemy event listeners
- Particioniranje po mesecu za performanse

### B2C Portal
- Servisi se prikazuju kao FIZICKA LICA (predstavnici)
- Min 1 verified predstavnik za B2C funkcije
- Zahtevi isticu posle 7 dana bez ponuda

### Tenant Isolation
- NIKAD direktan query bez tenant filtera
- Koristi `g.current_tenant.id` uvek
- Repositories automatski filtriraju

### Smart Part Matching
- Agregacija iz 3 izvora: moj lager, partneri, dobavljaci
- Matching po brand + model + part_type
- Redis cache za ceste pretrage

### Order System
- Status workflow: DRAFT -> SENT -> CONFIRMED -> SHIPPED -> DELIVERED -> COMPLETED
- Provizija 5% za dobavljace, 0% za partnere
- Sve transakcije se loguju u transaction_audit

---

## Subscription Model

| Stavka | Cena | Opis |
|--------|------|------|
| **Bazni paket** | **3.600 RSD/mesec** | 1 preduzece + 1 lokacija |
| **Dodatna lokacija** | **1.800 RSD/mesec** | Po lokaciji |

**Trial:** 3 meseca besplatno (bazni paket, 1 lokacija)

---

## Povezani Resursi

- Plan: `C:\Users\darko\.claude\plans\dynamic-stirring-ullman.md`
- Dolce Vita (referenca): `C:\dolcevita\`
- Railway Dashboard: https://railway.app/project/servishub
- GitHub: https://github.com/v1sk0/servishub

---

## Folder Struktura

```
servishub/
├── app/
│   ├── __init__.py              # App factory
│   ├── config.py                # Environment config
│   ├── extensions.py            # Flask extensions (db, migrate, jwt)
│   ├── models/                  # SQLAlchemy models
│   ├── api/                     # API layer (v1, public, admin)
│   ├── services/                # Business logic
│   ├── repositories/            # Data access
│   ├── tasks/                   # Celery background jobs
│   └── templates/               # Email templates
├── frontend/                    # Tailwind + Alpine.js + Jinja2
├── migrations/                  # Alembic
├── tests/                       # Pytest
├── scripts/                     # Utility scripts
├── docs/                        # Dokumentacija
├── requirements.txt
├── requirements-dev.txt
├── Procfile
├── railway.json
└── .env.example
```
