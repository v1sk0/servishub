# Javna Stranica - API Referenca

## Pregled

Ovaj dokument opisuje sve API endpointe vezane za Javnu Stranicu tenanta.

---

## Autentifikovani Endpointi (Tenant Admin)

Ovi endpointi zahtevaju JWT token u `Authorization` header-u.

### GET `/api/v1/tenant/public-profile`

Dohvata public profile trenutnog tenanta.

**Headers:**
```
Authorization: Bearer {jwt_token}
```

**Response 200:**
```json
{
  "id": 1,
  "tenant_id": 5,
  "is_public": true,
  "display_name": "Moj Servis",
  "tagline": "Profesionalna popravka telefona",
  "about_content": "<p>Opis firme...</p>",
  "phone": "+381 11 123 4567",
  "email": "info@mojservis.rs",
  "address": "Beogradska 123",
  "city": "Beograd",
  "maps_url": "https://maps.google.com/...",
  "working_hours": {
    "mon": {"open": "09:00", "close": "18:00", "closed": false},
    "tue": {"open": "09:00", "close": "18:00", "closed": false},
    "wed": {"open": "09:00", "close": "18:00", "closed": false},
    "thu": {"open": "09:00", "close": "18:00", "closed": false},
    "fri": {"open": "09:00", "close": "17:00", "closed": false},
    "sat": {"open": "09:00", "close": "14:00", "closed": false},
    "sun": {"open": null, "close": null, "closed": true}
  },
  "logo_url": "https://res.cloudinary.com/.../logo.png",
  "cover_image_url": "https://res.cloudinary.com/.../cover.jpg",
  "primary_color": "#3b82f6",
  "secondary_color": "#1e40af",
  "facebook_url": "https://facebook.com/mojservis",
  "instagram_url": "https://instagram.com/mojservis",
  "twitter_url": null,
  "linkedin_url": null,
  "youtube_url": null,
  "website_url": "https://mojservis.rs",
  "show_prices": true,
  "price_disclaimer": "Cene su okvirne i podlozne promenama nakon dijagnostike.",
  "meta_title": "Moj Servis - Popravka telefona",
  "meta_description": "Profesionalna popravka mobilnih telefona u Beogradu.",
  "custom_domain": "mojservis.rs",
  "custom_domain_verified": true,
  "created_at": "2026-01-15T10:30:00Z",
  "updated_at": "2026-01-18T14:22:00Z",
  "public_url": "https://mojservis.servishub.rs",
  "custom_url": "https://mojservis.rs"
}
```

**Response 404:**
```json
{
  "error": "Public profile not found"
}
```

---

### PUT `/api/v1/tenant/public-profile`

Azurira public profile.

**Headers:**
```
Authorization: Bearer {jwt_token}
Content-Type: application/json
```

**Request Body:**
```json
{
  "is_public": true,
  "display_name": "Moj Servis",
  "tagline": "Profesionalna popravka telefona",
  "about_content": "<p>Opis firme...</p>",
  "phone": "+381 11 123 4567",
  "email": "info@mojservis.rs",
  "address": "Beogradska 123",
  "city": "Beograd",
  "maps_url": "https://maps.google.com/...",
  "working_hours": {
    "mon": {"open": "09:00", "close": "18:00", "closed": false}
  },
  "logo_url": "https://res.cloudinary.com/.../logo.png",
  "cover_image_url": "https://res.cloudinary.com/.../cover.jpg",
  "primary_color": "#3b82f6",
  "secondary_color": "#1e40af",
  "facebook_url": "https://facebook.com/mojservis",
  "instagram_url": "https://instagram.com/mojservis",
  "website_url": "https://mojservis.rs",
  "show_prices": true,
  "price_disclaimer": "Cene su okvirne...",
  "meta_title": "Moj Servis - Popravka telefona",
  "meta_description": "Profesionalna popravka..."
}
```

**Validacija i Sanitizacija:**

| Polje | Tip | Sanitizacija |
|-------|-----|--------------|
| about_content | HTML | `sanitize_html()` - uklanja opasne tagove |
| *_url | URL | `sanitize_url()` - samo http/https |
| primary_color | Hex | `validate_hex_color()` - #RRGGBB format |
| secondary_color | Hex | `validate_hex_color()` - #RRGGBB format |

**Response 200:**
```json
{
  "message": "Profile updated successfully",
  "profile": { ... }
}
```

**Response 400:**
```json
{
  "error": "Invalid data",
  "details": {
    "email": "Invalid email format"
  }
}
```

---

### POST `/api/v1/tenant/public-profile/logo`

Upload logo slike na Cloudinary.

**Headers:**
```
Authorization: Bearer {jwt_token}
Content-Type: multipart/form-data
```

**Request Body:**
```
file: [binary image data]
```

**Response 200:**
```json
{
  "url": "https://res.cloudinary.com/servishub/image/upload/v1234567890/logos/tenant_5_abc123.png",
  "public_id": "logos/tenant_5_abc123"
}
```

**Response 400:**
```json
{
  "error": "Invalid file type. Allowed: jpg, jpeg, png, gif, webp"
}
```

---

### POST `/api/v1/tenant/public-profile/cover`

Upload cover slike na Cloudinary.

**Headers:**
```
Authorization: Bearer {jwt_token}
Content-Type: multipart/form-data
```

**Request Body:**
```
file: [binary image data]
```

**Response 200:**
```json
{
  "url": "https://res.cloudinary.com/servishub/image/upload/v1234567890/covers/tenant_5_xyz789.jpg",
  "public_id": "covers/tenant_5_xyz789"
}
```

---

### GET `/api/v1/tenant/public-profile/qrcode`

Generiše QR kod za javnu stranicu.

**Headers:**
```
Authorization: Bearer {jwt_token}
```

**Query Parameters:**
| Param | Tip | Default | Opis |
|-------|-----|---------|------|
| size | int | 200 | Velicina u pikselima |
| format | string | png | Format: png, svg |

**Response 200 (image/png):**
```
[binary PNG data]
```

**Response 200 (format=svg):**
```xml
<svg xmlns="http://www.w3.org/2000/svg" ...>
  ...
</svg>
```

---

### POST `/api/v1/tenant/public-profile/domain/setup`

Postavlja custom domen za verifikaciju.

**Headers:**
```
Authorization: Bearer {jwt_token}
Content-Type: application/json
```

**Request Body:**
```json
{
  "domain": "mojservis.rs"
}
```

**Validacija:**
- Domen mora biti validan format (a-z, 0-9, -, .)
- Ne sme biti vec u upotrebi od strane drugog tenanta
- Ne sme biti servishub.* domen

**Response 200:**
```json
{
  "message": "Domain setup initiated",
  "domain": "mojservis.rs",
  "verification_token": "abc123def456...",
  "verification_instructions": {
    "txt_record": {
      "host": "_servishub-verify.mojservis.rs",
      "type": "TXT",
      "value": "servishub-verify=abc123def456..."
    },
    "cname_record": {
      "host": "_servishub-verify.mojservis.rs",
      "type": "CNAME",
      "value": "abc123def456.verify.servishub.rs"
    },
    "routing_record": {
      "host": "mojservis.rs",
      "type": "CNAME",
      "value": "proxy.servishub.rs"
    }
  }
}
```

**Response 400:**
```json
{
  "error": "Invalid domain format"
}
```

**Response 409:**
```json
{
  "error": "Domain already in use by another tenant"
}
```

---

### POST `/api/v1/tenant/public-profile/domain/verify`

Verifikuje DNS postavke za custom domen.

**Headers:**
```
Authorization: Bearer {jwt_token}
```

**Response 200:**
```json
{
  "verified": true,
  "verification_record": true,
  "routing_record": true,
  "message": "Domain verified successfully"
}
```

**Response 200 (neuspesno):**
```json
{
  "verified": false,
  "verification_record": false,
  "routing_record": true,
  "errors": [
    "Verifikacioni DNS record nije pronadjen ili nije ispravan"
  ]
}
```

---

### DELETE `/api/v1/tenant/public-profile/domain`

Uklanja custom domen.

**Headers:**
```
Authorization: Bearer {jwt_token}
```

**Response 200:**
```json
{
  "message": "Domain removed successfully"
}
```

---

## Javni Endpointi (Bez Autentifikacije)

Ovi endpointi su dostupni na subdomen/custom domen URL-ovima.
Imaju rate limit: **60 zahteva po minutu po IP adresi**.

### GET `/api/info`

Dohvata javne informacije o tenantu.

**URL:**
```
https://mojservis.servishub.rs/api/info
https://mojservis.rs/api/info (ako je custom domen verifikovan)
```

**Response 200:**
```json
{
  "name": "Moj Servis",
  "slug": "mojservis",
  "url": "https://mojservis.servishub.rs",
  "tagline": "Profesionalna popravka telefona",
  "about_content": "<p>Opis firme...</p>",
  "contact": {
    "phone": "+381 11 123 4567",
    "email": "info@mojservis.rs",
    "address": "Beogradska 123",
    "city": "Beograd",
    "maps_url": "https://maps.google.com/..."
  },
  "working_hours": {
    "mon": {"open": "09:00", "close": "18:00", "closed": false},
    "tue": {"open": "09:00", "close": "18:00", "closed": false},
    "wed": {"open": "09:00", "close": "18:00", "closed": false},
    "thu": {"open": "09:00", "close": "18:00", "closed": false},
    "fri": {"open": "09:00", "close": "17:00", "closed": false},
    "sat": {"open": "09:00", "close": "14:00", "closed": false},
    "sun": {"open": null, "close": null, "closed": true}
  },
  "branding": {
    "logo_url": "https://res.cloudinary.com/.../logo.png",
    "cover_image_url": "https://res.cloudinary.com/.../cover.jpg",
    "primary_color": "#3b82f6",
    "secondary_color": "#1e40af"
  },
  "social": {
    "facebook": "https://facebook.com/mojservis",
    "instagram": "https://instagram.com/mojservis",
    "twitter": null,
    "linkedin": null,
    "youtube": null,
    "website": "https://mojservis.rs"
  },
  "services": [
    {
      "id": 1,
      "name": "Zamena ekrana",
      "description": "Profesionalna zamena ekrana za sve modele telefona",
      "category": "ZAMENA_EKRANA",
      "price": 3000.00,
      "currency": "RSD",
      "price_note": "od"
    },
    {
      "id": 2,
      "name": "Zamena baterije",
      "description": "Zamena originalne baterije",
      "category": "ZAMENA_BATERIJE",
      "price": 1500.00,
      "currency": "RSD",
      "price_note": null
    }
  ],
  "price_disclaimer": "Cene su okvirne i podlozne promenama nakon dijagnostike."
}
```

**Response 404:**
```json
{
  "error": "Not Found"
}
```

**Response 429:**
```json
{
  "error": "Too many requests. Please try again later."
}
```

---

### GET `/api/services`

Dohvata listu aktivnih usluga.

**URL:**
```
https://mojservis.servishub.rs/api/services
```

**Query Parameters:**
| Param | Tip | Default | Opis |
|-------|-----|---------|------|
| category | string | null | Filter po kategoriji |
| limit | int | 50 | Max broj rezultata |
| offset | int | 0 | Paginacija offset |

**Response 200:**
```json
{
  "services": [
    {
      "id": 1,
      "name": "Zamena ekrana",
      "description": "Profesionalna zamena ekrana za sve modele telefona",
      "category": "ZAMENA_EKRANA",
      "category_display": "Zamena ekrana",
      "price": 3000.00,
      "currency": "RSD",
      "price_note": "od",
      "price_display": "od 3.000 RSD"
    }
  ],
  "total": 15,
  "limit": 50,
  "offset": 0,
  "show_prices": true,
  "price_disclaimer": "Cene su okvirne..."
}
```

---

## Error Responses

### Standardni Format Greske

```json
{
  "error": "Kratki opis greske",
  "details": {
    "field_name": "Detaljna poruka za polje"
  },
  "code": "ERROR_CODE"
}
```

### HTTP Status Kodovi

| Status | Opis |
|--------|------|
| 200 | Uspesno |
| 201 | Kreirano |
| 400 | Lose formiran zahtev / Validaciona greska |
| 401 | Neautorizovano (nedostaje/neispravan token) |
| 403 | Zabranjeno (nema dozvolu) |
| 404 | Nije pronadjeno |
| 409 | Konflikt (npr. domen vec postoji) |
| 429 | Previse zahteva (rate limit) |
| 500 | Serverska greska |

---

## Rate Limiting

### Pravila

| Endpoint Tip | Limit | Window |
|--------------|-------|--------|
| Public API | 60 req | 60 sec |
| Auth API | 120 req | 60 sec |
| Upload | 10 req | 60 sec |

### Headers u Response-u

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1705592400
```

---

## Pydantic Schema Definicije

### PublicProfileUpdateSchema

```python
class WorkingHoursDay(BaseModel):
    open: Optional[str] = Field(None, pattern=r'^\d{2}:\d{2}$')
    close: Optional[str] = Field(None, pattern=r'^\d{2}:\d{2}$')
    closed: bool = False

class PublicProfileUpdateSchema(BaseModel):
    is_public: Optional[bool] = None
    display_name: Optional[str] = Field(None, max_length=200)
    tagline: Optional[str] = Field(None, max_length=300)
    about_content: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[EmailStr] = None
    address: Optional[str] = Field(None, max_length=300)
    city: Optional[str] = Field(None, max_length=100)
    maps_url: Optional[HttpUrl] = None
    working_hours: Optional[Dict[str, WorkingHoursDay]] = None
    logo_url: Optional[HttpUrl] = None
    cover_image_url: Optional[HttpUrl] = None
    primary_color: Optional[str] = Field(None, pattern=r'^#[0-9a-fA-F]{6}$')
    secondary_color: Optional[str] = Field(None, pattern=r'^#[0-9a-fA-F]{6}$')
    facebook_url: Optional[HttpUrl] = None
    instagram_url: Optional[HttpUrl] = None
    twitter_url: Optional[HttpUrl] = None
    linkedin_url: Optional[HttpUrl] = None
    youtube_url: Optional[HttpUrl] = None
    website_url: Optional[HttpUrl] = None
    show_prices: Optional[bool] = None
    price_disclaimer: Optional[str] = Field(None, max_length=500)
    meta_title: Optional[str] = Field(None, max_length=100)
    meta_description: Optional[str] = Field(None, max_length=300)

    class Config:
        extra = 'forbid'
```

### DomainSetupSchema

```python
class DomainSetupSchema(BaseModel):
    domain: str = Field(..., min_length=4, max_length=255)

    @validator('domain')
    def validate_domain(cls, v):
        import re
        pattern = r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*\.[a-z]{2,}$'
        if not re.match(pattern, v.lower()):
            raise ValueError('Invalid domain format')
        if 'servishub' in v.lower():
            raise ValueError('Cannot use servishub domain')
        return v.lower()
```

---

## Primer Integracije

### JavaScript/Fetch

```javascript
// Dohvati public profile
const response = await fetch('/api/v1/tenant/public-profile', {
  headers: {
    'Authorization': `Bearer ${token}`
  }
});
const profile = await response.json();

// Azuriraj profile
const updateResponse = await fetch('/api/v1/tenant/public-profile', {
  method: 'PUT',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    is_public: true,
    display_name: 'Novi Naziv'
  })
});
```

### Python/Requests

```python
import requests

# Dohvati public profile
headers = {'Authorization': f'Bearer {token}'}
response = requests.get(
    'https://app.servishub.rs/api/v1/tenant/public-profile',
    headers=headers
)
profile = response.json()

# Azuriraj profile
update_data = {
    'is_public': True,
    'display_name': 'Novi Naziv'
}
response = requests.put(
    'https://app.servishub.rs/api/v1/tenant/public-profile',
    headers=headers,
    json=update_data
)
```

---

## Verzionisanje API-ja

Trenutna verzija: **v1**

Base URL: `/api/v1/`

Buduće verzije će koristiti `/api/v2/`, `/api/v3/`, itd.
Stare verzije će biti podržane minimum 12 meseci nakon izlaska nove verzije.