# Cloudinary Upload System

Dokumentacija za sistem upload-a slika na Cloudinary servis u ServisHub platformi.

---

## Pregled

ServisHub koristi **Cloudinary** kao cloud servis za skladištenje slika. Sve slike su organizovane po tenant-ima radi izolacije i lakšeg upravljanja.

### Folder Struktura

```
servishub/
└── tenant_{id}/
    ├── logos/
    │   └── logo          # Glavni logo servisa
    ├── locations/        # Slike lokacija (buduća implementacija)
    │   └── {location_id}
    └── documents/        # Dokumenti (buduća implementacija)
        └── {filename}
```

**Primer:**
- Logo za tenant ID 42: `servishub/tenant_42/logos/logo`
- Slika lokacije: `servishub/tenant_42/locations/loc_1` (budući feature)

---

## Konfiguracija

### Environment Varijable

Cloudinary se konfiguriše preko environment varijabli. Postoje dva načina:

#### Opcija 1: CLOUDINARY_URL (preporučeno)

```bash
CLOUDINARY_URL=cloudinary://{api_key}:{api_secret}@{cloud_name}
```

Primer:
```bash
heroku config:set CLOUDINARY_URL=cloudinary://553153862213115:iuHr0atL5FIfS2Z1P0z_zYz_RJg@da8wf6esj
```

#### Opcija 2: Pojedinačne varijable

```bash
CLOUDINARY_CLOUD_NAME=da8wf6esj
CLOUDINARY_API_KEY=553153862213115
CLOUDINARY_API_SECRET=iuHr0atL5FIfS2Z1P0z_zYz_RJg
```

### Heroku Setup

```bash
# Postavi Cloudinary URL
heroku config:set CLOUDINARY_URL=cloudinary://API_KEY:API_SECRET@CLOUD_NAME

# Proveri konfiguraciju
heroku config | grep CLOUDINARY
```

---

## Utility Modul

**Fajl:** `app/utils/cloudinary_upload.py`

### Konstante

```python
# Dozvoljeni formati slika
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# Maksimalna veličina fajla (5MB)
MAX_FILE_SIZE = 5 * 1024 * 1024
```

### Funkcije

#### `init_cloudinary()`

Inicijalizuje Cloudinary konekciju iz environment varijabli.

```python
def init_cloudinary() -> bool:
    """
    Initialize Cloudinary from environment variables.

    Returns:
        True ako je konfiguracija uspešna, False inače
    """
```

#### `allowed_file(filename)`

Proverava da li je ekstenzija fajla dozvoljena.

```python
def allowed_file(filename: str) -> bool:
    """
    Check if the file extension is allowed.

    Args:
        filename: Ime fajla sa ekstenzijom

    Returns:
        True ako je format dozvoljen
    """
```

#### `validate_file(file)`

Validira uploadovani fajl (format i veličina).

```python
def validate_file(file) -> tuple[bool, str | None]:
    """
    Validate uploaded file.

    Args:
        file: FileStorage objekt iz request.files

    Returns:
        tuple (is_valid, error_message)
        - (True, None) ako je fajl validan
        - (False, "Poruka greške") ako nije
    """
```

#### `upload_image(file, tenant_id, subfolder, filename='image')`

Glavna funkcija za upload slike na Cloudinary.

```python
def upload_image(file, tenant_id: int, subfolder: str, filename: str = 'image') -> dict:
    """
    Upload an image to Cloudinary in tenant's folder structure.

    Folder struktura: servishub/tenant_{id}/{subfolder}/{filename}

    Args:
        file: FileStorage objekt iz request.files
        tenant_id: ID tenanta za organizaciju uploada
        subfolder: Naziv podfoldera ('logos', 'locations', 'documents')
        filename: Ime fajla (bez ekstenzije)

    Returns:
        dict sa ključevima:
        - success: True/False
        - url: Cloudinary secure URL (ako uspešno)
        - public_id: Cloudinary public ID (ako uspešno)
        - width: Širina slike u pikselima
        - height: Visina slike u pikselima
        - error: Poruka greške (ako neuspešno)
    """
```

**Transformacije pri uploadu:**
- Maksimalne dimenzije: 500x500 px (`crop: limit`)
- Kvalitet: `auto:good`
- Format: `auto` (WebP za moderne browsere)

#### `upload_logo(file, tenant_id)`

Wrapper za upload logo slike.

```python
def upload_logo(file, tenant_id: int) -> dict:
    """
    Upload a logo image to Cloudinary.

    Putanja: servishub/tenant_{id}/logos/logo
    """
    return upload_image(file, tenant_id, 'logos', 'logo')
```

#### `delete_image(tenant_id, subfolder, filename)`

Briše sliku sa Cloudinary-ja.

```python
def delete_image(tenant_id: int, subfolder: str, filename: str) -> dict:
    """
    Delete an image from Cloudinary.

    Returns:
        dict sa ključevima:
        - success: True/False
        - result: Cloudinary rezultat ('ok', 'not found')
        - error: Poruka greške (ako neuspešno)
    """
```

#### `delete_logo(tenant_id)`

Wrapper za brisanje logo slike.

```python
def delete_logo(tenant_id: int) -> dict:
    """
    Delete a logo from Cloudinary.

    Briše: servishub/tenant_{id}/logos/logo
    """
    return delete_image(tenant_id, 'logos', 'logo')
```

---

## API Endpoints

### Upload Logo

```
POST /api/v1/tenant/upload/logo
```

**Headers:**
```
Authorization: Bearer {access_token}
Content-Type: multipart/form-data
```

**Body:**
```
logo: [File] - Slika loga (PNG, JPG, JPEG, GIF, WEBP; max 5MB)
```

**Response (200):**
```json
{
  "message": "Logo uspešno uploadovan",
  "url": "https://res.cloudinary.com/da8wf6esj/image/upload/v123/servishub/tenant_42/logos/logo.webp",
  "width": 500,
  "height": 300
}
```

**Response (400):**
```json
{
  "error": "Dozvoljeni formati: png, jpg, jpeg, gif, webp"
}
```

**Response (403):**
```json
{
  "error": "Admin access required"
}
```

**Pristup:** Samo OWNER i ADMIN

### Delete Logo

```
DELETE /api/v1/tenant/upload/logo
```

**Headers:**
```
Authorization: Bearer {access_token}
```

**Response (200):**
```json
{
  "message": "Logo obrisan"
}
```

**Response (400):**
```json
{
  "error": "Logo ne postoji"
}
```

**Pristup:** Samo OWNER i ADMIN

---

## Upotreba u Bazi

### Tenant Model

```python
class Tenant(db.Model):
    # ... ostala polja ...

    # Logo servisa (Cloudinary URL)
    logo_url = db.Column(db.String(500))
```

**Migracija:** `v306_tenant_logo_url.py`

---

## Frontend Integracija

### Settings UI (Profil Tab)

Komponenta za upload loga se nalazi na Settings → Profil tabu.

**Features:**
- Drag & drop upload
- Preview trenutnog loga
- Validacija formata i veličine pre slanja
- Progress indikator tokom uploada
- Dugme za brisanje loga

**Alpine.js State:**
```javascript
{
  uploadingLogo: false,
  // ... ostali state ...
}
```

**Metode:**
```javascript
async uploadLogo(event) {
  // Validacija i upload na /api/v1/tenant/upload/logo
}

async deleteLogo() {
  // Brisanje na DELETE /api/v1/tenant/upload/logo
}
```

### Print Ticket

Logo se prikazuje na print stranici umesto tekstualnog imena servisa.

**CSS Stilovi:**
```css
.company-logo img {
  display: block;
  margin: 0 auto;
  width: 75px;
  height: auto;
  filter: grayscale(100%);  /* Crno-belo za štampu */
}
```

**JavaScript Fallback:**
```javascript
if (tenant?.logo_url) {
  logoImg.src = tenant.logo_url;
  logoImg.style.display = 'block';
  logoText.style.display = 'none';
} else {
  // Fallback na tekstualni naziv
  logoImg.style.display = 'none';
  logoText.style.display = 'block';
  logoText.textContent = tenant?.name || 'Servis';
}
```

---

## Validacija

### Server-side Validacija

1. **Format fajla:** Samo `png`, `jpg`, `jpeg`, `gif`, `webp`
2. **Veličina fajla:** Maksimalno 5MB
3. **Autorizacija:** Samo OWNER i ADMIN role

### Client-side Validacija (preporučena)

```javascript
const file = event.target.files[0];

// Proveri format
const allowedTypes = ['image/png', 'image/jpeg', 'image/gif', 'image/webp'];
if (!allowedTypes.includes(file.type)) {
  alert('Dozvoljeni formati: PNG, JPG, GIF, WEBP');
  return;
}

// Proveri veličinu (5MB)
if (file.size > 5 * 1024 * 1024) {
  alert('Maksimalna veličina fajla je 5MB');
  return;
}
```

---

## Greške i Troubleshooting

### "Cloudinary nije konfigurisan"

**Uzrok:** Environment varijable nisu postavljene.

**Rešenje:**
```bash
heroku config:set CLOUDINARY_URL=cloudinary://API_KEY:API_SECRET@CLOUD_NAME
```

### "Fajl je prevelik (max 5MB)"

**Uzrok:** Uploadovani fajl je veći od 5MB.

**Rešenje:** Kompresuj sliku pre uploada ili koristi manji fajl.

### "Dozvoljeni formati: png, jpg, jpeg, gif, webp"

**Uzrok:** Pokušaj uploada nedozvoljenog formata.

**Rešenje:** Konvertuj sliku u jedan od dozvoljenih formata.

### Logo se ne prikazuje na print stranici

**Mogući uzroci:**
1. `tenant.logo_url` nije sačuvan u bazi
2. Cloudinary URL je neispravan
3. CORS problemi

**Provera:**
```bash
# Proveri da li je logo_url sačuvan
heroku run flask shell
>>> from app.models import Tenant
>>> t = Tenant.query.get(1)
>>> print(t.logo_url)
```

---

## Buduća Proširenja

### Planirani Subfolderi

1. **`locations/`** - Slike lokacija za prezentaciju
   - Format: `servishub/tenant_{id}/locations/{location_id}`
   - Koristi se na javnoj stranici

2. **`documents/`** - Dokumenta (fakture, ugovori)
   - Format: `servishub/tenant_{id}/documents/{filename}`
   - Privatni pristup

3. **`gallery/`** - Galerija slika za javnu stranicu
   - Format: `servishub/tenant_{id}/gallery/{image_id}`

### Primer Implementacije za Lokacije

```python
def upload_location_image(file, tenant_id, location_id):
    """Upload slike lokacije."""
    return upload_image(file, tenant_id, 'locations', f'loc_{location_id}')

def delete_location_image(tenant_id, location_id):
    """Brisanje slike lokacije."""
    return delete_image(tenant_id, 'locations', f'loc_{location_id}')
```

---

## Sigurnost

1. **Autorizacija:** Svi upload/delete endpoint-i zahtevaju OWNER ili ADMIN rolu
2. **Validacija:** Server-side validacija formata i veličine
3. **Izolacija:** Svaki tenant ima svoj folder - ne može pristupiti tuđim slikama
4. **HTTPS:** Cloudinary secure URL (HTTPS) se uvek koristi
5. **Overwrite:** Logo se prepisuje pri novom uploadu (nema gomilanja fajlova)

---

## Reference

- [Cloudinary Upload API](https://cloudinary.com/documentation/image_upload_api_reference)
- [Cloudinary Transformations](https://cloudinary.com/documentation/image_transformations)
- `app/utils/cloudinary_upload.py` - Utility modul
- `app/api/v1/tenant.py` - API endpoints (linije 212-291)
- `app/templates/tenant/settings/index.html` - Frontend UI
- `app/templates/tenant/tickets/print.html` - Print template
