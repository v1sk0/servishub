# ServisHub

SaaS platforma za servise mobilnih telefona i računara.

## Funkcionalnosti

### B2B (Servisi)
- Upravljanje servisnim nalozima sa garancijama
- Inventar telefona i rezervnih delova
- Multi-lokacijska podrška
- Automatsko praćenje garancija

### B2C (Kupci)
- Javni portal za praćenje popravki putem QR koda
- Pregled ponuda telefona

### Dobavljači (Suppliers)
- Katalog rezervnih delova
- Narudžbine sa 5% komisijom platforme

### Platform Admin
- Upravljanje tenantima
- KYC verifikacija
- Dashboard sa prihodima

## Tech Stack

- **Backend**: Python 3.11 + Flask 3.x + SQLAlchemy 2.0
- **Database**: PostgreSQL 15
- **Auth**: JWT (access + refresh tokens)
- **Queue**: Celery + Redis
- **Hosting**: Railway

## Lokalni razvoj

```bash
# Kloniraj repo
git clone https://github.com/YOUR_USERNAME/servishub.git
cd servishub

# Kreiraj virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Instaliraj zavisnosti
pip install -r requirements.txt

# Kopiraj i podesi environment
cp .env.example .env
# Uredi .env sa pravim vrednostima

# Pokreni migracije
flask db upgrade

# Kreiraj admin korisnika
flask create-admin

# Pokreni server
python run.py
```

## Railway Deployment

### 1. Kreiraj novi projekat na Railway

1. Idi na [railway.app](https://railway.app)
2. Klikni "New Project"
3. Izaberi "Deploy from GitHub repo"
4. Poveži sa ovim repozitorijumom

### 2. Dodaj PostgreSQL

1. U Railway projektu klikni "+ Add Service"
2. Izaberi "Database" → "PostgreSQL"
3. Railway će automatski dodati DATABASE_URL variable

### 3. Postavi Environment Variables

U Railway dashboard-u dodaj sledeće varijable:

```
SECRET_KEY=<generisi-jak-kljuc>
JWT_SECRET_KEY=<generisi-drugi-jak-kljuc>
JWT_ADMIN_SECRET_KEY=<generisi-treci-jak-kljuc>
FLASK_ENV=production
```

Opciono:
```
CLOUDINARY_URL=cloudinary://...
REDIS_URL=redis://...
MAIL_SERVER=smtp.gmail.com
MAIL_USERNAME=...
MAIL_PASSWORD=...
```

### 4. Deploy

Railway će automatski deployovati kod svaki put kad pushuješ na main branch.

### 5. Pokreni migracije

U Railway konzoli:
```bash
flask db upgrade
flask create-admin
```

## API Endpoints

### Zdravlje
- `GET /health` - Health check

### Auth (Tenant)
- `POST /api/v1/auth/register` - Registracija novog servisa
- `POST /api/v1/auth/login` - Login
- `POST /api/v1/auth/refresh` - Refresh token
- `GET /api/v1/auth/me` - Trenutni korisnik

### Tiketi
- `GET /api/v1/tickets` - Lista tiketa
- `POST /api/v1/tickets` - Novi tiket
- `PUT /api/v1/tickets/<id>` - Ažuriraj tiket
- `PUT /api/v1/tickets/<id>/status` - Promeni status
- `GET /api/v1/tickets/public/<token>` - Javni pregled (QR)

### Inventar
- `GET /api/v1/inventory/phones` - Lista telefona
- `POST /api/v1/inventory/phones` - Novi telefon
- `GET /api/v1/inventory/parts` - Lista delova
- `POST /api/v1/inventory/parts` - Novi deo

### Admin API
- `POST /api/admin/auth/login` - Admin login
- `GET /api/admin/tenants` - Lista servisa
- `POST /api/admin/tenants/<id>/activate` - Aktiviraj servis
- `GET /api/admin/kyc/pending` - Pending KYC zahtevi
- `GET /api/admin/dashboard/stats` - Dashboard statistike

## Pretplata

- **Trial**: 3 meseca besplatno
- **Base**: 3,600 RSD/mesec
- **Dodatna lokacija**: +1,800 RSD/mesec
- **Supplier komisija**: 5%

## License

Proprietary - Dolce Vita
