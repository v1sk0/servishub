# ServisHub - OAuth i Sigurnosna Dokumentacija

Verzija: 1.0
Datum: 16.01.2026
Autor: Claude Code

---

## Pregled

Ovaj dokument opisuje implementaciju Google OAuth autentifikacije u ServisHub platformi, uključujući sigurnosne mere i best practices.

---

## 1. Google OAuth Flow

### 1.1 Arhitektura

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│                 │     │                 │     │                 │
│     Korisnik    │────▶│   ServisHub     │────▶│     Google      │
│    (Browser)    │◀────│    Backend      │◀────│    OAuth API    │
│                 │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

### 1.2 Kompletni Flow

#### A) Login postojećeg korisnika

```
1. Korisnik klikne "Nastavi sa Google" na /login
2. Frontend poziva GET /api/v1/auth/google
3. Backend:
   - Generiše CSRF state token (secrets.token_urlsafe(32))
   - Čuva state u Flask session
   - Vraća Google OAuth URL sa state parametrom
4. Frontend redirectuje na Google consent screen
5. Korisnik odobrava pristup
6. Google redirectuje na /api/v1/auth/google/callback?code=xxx&state=yyy
7. Backend:
   - Verifikuje state == session['oauth_state'] (CSRF zaštita)
   - Razmenjuje code za access_token sa Google-om
   - Dohvata korisničke podatke (email, ime, prezime, google_id)
   - Pronalazi korisnika u bazi po google_id ili email
   - Generiše JWT tokene
   - Čuva tokene u session['oauth_tokens']
   - Redirectuje na /dashboard?auth=oauth
8. Frontend (tenant layout):
   - Detektuje auth=oauth parametar
   - Poziva GET /api/v1/auth/google/tokens
   - Backend vraća tokene i briše ih iz sesije (one-time use)
   - Frontend čuva tokene u localStorage
   - Čisti URL parametre
   - Učitava korisničke podatke
```

#### B) Registracija novog korisnika

```
1. Korisnik popuni korak 1 registracije (podaci o firmi)
2. Na koraku 2, klikne "Verifikuj preko Google naloga"
3. Frontend čuva podatke koraka 1 u localStorage
4. Isti OAuth flow kao gore (koraci 2-7)
5. Backend detektuje da korisnik ne postoji:
   - Enkodira Google podatke u base64
   - Čuva ih i u session kao fallback
   - Redirectuje na /register?oauth=google&gdata=xxx
6. Frontend:
   - Detektuje oauth=google parametar
   - Vraća podatke koraka 1 iz localStorage
   - Dekodira gdata i popunjava formu
   - Označi email kao verifikovan
   - Preskače na korak 2
7. Korisnik nastavlja registraciju (bez potrebe za lozinkom)
```

---

## 2. Sigurnosne Mere

### 2.1 CSRF Zaštita (State Parameter)

**Problem:** Bez state parametra, napadač može da izvrši CSRF napad i poveže svoj Google nalog sa tuđom sesijom.

**Rešenje:**
```python
# Generisanje state tokena (auth.py, linija 566)
state = secrets.token_urlsafe(32)
session['oauth_state'] = state

# Verifikacija u callback-u (auth.py, linija 648-653)
state = request.args.get('state')
stored_state = session.pop('oauth_state', None)

if not state or not stored_state or state != stored_state:
    return redirect(f'/login?error=csrf_invalid')
```

**Karakteristike:**
- 32 bajta (256 bita) entropije
- URL-safe enkodiranje
- Jednokratna upotreba (briše se iz sesije nakon provere)

### 2.2 Siguran Transfer Tokena

**Problem:** Prenošenje JWT tokena kroz URL parametar je nesigurno jer:
- Token se pojavljuje u browser history-ju
- Može biti zabeležen u server logovima
- Može procureti kroz Referer header

**Prethodni (nesigurni) pristup:**
```python
# LOŠE - token u URL-u
return redirect(f'/dashboard?token={tokens["access_token"]}')
```

**Novi (sigurni) pristup:**
```python
# DOBRO - token u HTTP sesiji (auth.py, linija 722-728)
session['oauth_tokens'] = {
    'access_token': tokens['access_token'],
    'refresh_token': tokens['refresh_token']
}
return redirect(f'/dashboard?auth=oauth')
```

**Frontend preuzimanje (tenant.html, linija 116-131):**
```javascript
if (authMethod === 'oauth') {
    const response = await fetch('/api/v1/auth/google/tokens');
    if (response.ok) {
        const data = await response.json();
        localStorage.setItem('access_token', data.access_token);
        if (data.refresh_token) {
            localStorage.setItem('refresh_token', data.refresh_token);
        }
    }
    window.history.replaceState({}, document.title, window.location.pathname);
}
```

**Karakteristike:**
- Tokeni se nikad ne pojavljuju u URL-u
- Endpoint `/api/v1/auth/google/tokens` je one-time use
- URL se čisti nakon preuzimanja tokena

### 2.3 One-Time Token Endpoint

```python
# auth.py, linija 617-644
@bp.route('/google/tokens', methods=['GET'])
def google_tokens():
    """
    Sigurno preuzima OAuth tokene iz sesije.
    One-time use - briše tokene nakon čitanja.
    """
    from flask import session

    # Preuzmi i obriši tokene
    tokens = session.pop('oauth_tokens', None)

    if not tokens:
        return jsonify({
            'error': 'No Tokens',
            'message': 'Nema OAuth tokena u sesiji'
        }), 404

    return jsonify({
        'access_token': tokens.get('access_token'),
        'refresh_token': tokens.get('refresh_token')
    }), 200
```

---

## 3. API Endpoints

### 3.1 OAuth Endpoints

| Endpoint | Metod | Opis |
|----------|-------|------|
| `/api/v1/auth/google` | GET | Pokreće OAuth flow, vraća Google auth URL |
| `/api/v1/auth/google/callback` | GET | Google callback, obrađuje autentifikaciju |
| `/api/v1/auth/google/tokens` | GET | Preuzima tokene iz sesije (one-time) |
| `/api/v1/auth/google/session` | GET | Vraća Google user data iz sesije |

### 3.2 Request/Response Primeri

#### GET /api/v1/auth/google

**Response (200):**
```json
{
    "auth_url": "https://accounts.google.com/o/oauth2/v2/auth?client_id=xxx&redirect_uri=xxx&response_type=code&scope=openid%20email%20profile&access_type=offline&prompt=select_account&state=xxx"
}
```

#### GET /api/v1/auth/google/tokens

**Response (200):**
```json
{
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response (404):**
```json
{
    "error": "No Tokens",
    "message": "Nema OAuth tokena u sesiji"
}
```

---

## 4. Baza Podataka

### 4.1 TenantUser Model - OAuth Polja

```python
# models/user.py
class TenantUser(db.Model):
    # ... postojeća polja ...

    # OAuth polja
    google_id = db.Column(db.String(100), unique=True, nullable=True)
    auth_provider = db.Column(db.String(20), default='email')  # 'email' ili 'google'

    # Password može biti NULL za OAuth korisnike
    password_hash = db.Column(db.String(200), nullable=True)
```

### 4.2 Migracija

```python
# migrations/versions/g8h9i0j1k2l3_make_password_hash_nullable.py
def upgrade():
    op.alter_column('tenant_user', 'password_hash',
                    existing_type=sa.String(200),
                    nullable=True)

def downgrade():
    # UPOZORENJE: Ovo će propasti ako postoje OAuth korisnici
    op.alter_column('tenant_user', 'password_hash',
                    existing_type=sa.String(200),
                    nullable=False)
```

---

## 5. Validacija Lozinke za OAuth

### 5.1 Pydantic Schema

```python
# api/schemas/auth.py
class RegisterRequest(BaseModel):
    owner_password: Optional[str] = Field(None, max_length=100)

    @field_validator('owner_password', mode='before')
    @classmethod
    def validate_password(cls, v, info):
        """Lozinka je opciona za OAuth korisnike."""
        # Prazan string ili None → vrati None (OAuth)
        if v is None or v == '':
            return None
        # Standardna validacija za email registraciju
        if len(v) < 8:
            raise ValueError('Lozinka mora imati najmanje 8 karaktera')
        if not re.search(r'[A-Za-z]', v):
            raise ValueError('Lozinka mora sadrzati bar jedno slovo')
        if not re.search(r'\d', v):
            raise ValueError('Lozinka mora sadrzati bar jedan broj')
        return v
```

**Važno:** `mode='before'` je ključan jer se izvršava pre Field validacije.

---

## 6. Environment Varijable

```env
# Google OAuth (obavezno za produkciju)
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=xxx
GOOGLE_REDIRECT_URI=https://servicehubdolce-4c283dce32e9.herokuapp.com/api/v1/auth/google/callback

# Flask Session (obavezno za CSRF zaštitu)
SECRET_KEY=your-secret-key-min-32-chars
```

### 6.1 Google Cloud Console Konfiguracija

1. Idi na https://console.cloud.google.com/apis/credentials
2. Kreiraj OAuth 2.0 Client ID
3. Dodaj Authorized redirect URI:
   - Produkcija: `https://servicehubdolce-4c283dce32e9.herokuapp.com/api/v1/auth/google/callback`
   - Development: `http://localhost:5000/api/v1/auth/google/callback`
4. Kopiraj Client ID i Client Secret u env varijable

---

## 7. Error Handling

### 7.1 OAuth Greške

| Error Code | Opis | Korisnička Poruka |
|------------|------|-------------------|
| `google_denied` | Korisnik odbio pristup | "Google prijava je odbijena." |
| `no_code` | Google nije vratio code | "Greška pri Google prijavi. Pokušajte ponovo." |
| `config` | OAuth nije konfigurisan | "Google prijava nije konfigurisana." |
| `csrf_invalid` | State se ne poklapa | "Sesija je istekla. Pokušajte ponovo." |
| `token_exchange` | Greška pri razmeni tokena | "Greška u komunikaciji sa Google servisom." |
| `userinfo` | Greška pri dohvatanju podataka | "Greška u komunikaciji sa Google servisom." |
| `network` | Mrežna greška | "Greška u komunikaciji sa Google servisom." |

### 7.2 Frontend Error Handling

```javascript
// login.html
if (error) {
    switch(error) {
        case 'google_denied':
            this.error = 'Google prijava je odbijena.';
            break;
        case 'csrf_invalid':
            this.error = 'Sesija je istekla. Pokušajte ponovo.';
            break;
        // ... ostali slučajevi
    }
    window.history.replaceState({}, document.title, window.location.pathname);
}
```

---

## 8. Testiranje

### 8.1 Test Checklist

- [ ] Login postojećeg korisnika preko Google-a
- [ ] Registracija novog korisnika preko Google-a
- [ ] CSRF zaštita - pokušaj sa pogrešnim state
- [ ] Token nije vidljiv u URL-u nakon login-a
- [ ] Token endpoint vraća 404 pri drugom pozivu (one-time)
- [ ] OAuth korisnik može da se uloguje bez lozinke
- [ ] Povezivanje Google naloga sa postojećim email nalogom
- [ ] Error handling za sve error case-ove

### 8.2 Manuelno Testiranje CSRF Zaštite

```bash
# 1. Dobij OAuth URL bez validnog state-a
curl "https://servicehubdolce-4c283dce32e9.herokuapp.com/api/v1/auth/google"

# 2. Pokušaj callback sa lažnim state-om
curl "https://servicehubdolce-4c283dce32e9.herokuapp.com/api/v1/auth/google/callback?code=xxx&state=fake"
# Očekivani rezultat: Redirect na /login?error=csrf_invalid
```

---

## 9. Poznati Problemi i Ograničenja

### 9.1 Session Storage

- Flask session koristi cookie-based storage
- Maksimalna veličina cookie-ja je ~4KB
- Za veće podatke, razmotriti server-side session (Redis)

### 9.2 Token Expiry

- OAuth state token nema eksplicitni TTL
- Zavisi od Flask session lifetime
- Preporuka: Postaviti `PERMANENT_SESSION_LIFETIME`

### 9.3 Multiple Tabs

- Ako korisnik otvori OAuth u više tabova, samo jedan će uspeti
- State se briše nakon prvog korišćenja

---

## 10. Buduća Poboljšanja

1. **Refresh Token za Google** - Čuvanje Google refresh tokena za dugoročni pristup
2. **Apple Sign In** - Dodati podršku za Apple OAuth
3. **2FA** - Dvofaktorska autentifikacija
4. **Session Management** - Pregled i revokacija aktivnih sesija
5. **Rate Limiting** - Ograničiti broj OAuth pokušaja po IP-u

---

## 11. Reference

- [Google OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)
- [OAuth 2.0 Security Best Practices](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-security-topics)
- [Flask Session Documentation](https://flask.palletsprojects.com/en/3.0.x/api/#sessions)
- [OWASP OAuth Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth_Cheat_Sheet.html)

---

## 12. Changelog

### v1.0 (16.01.2026)
- Inicijalna implementacija Google OAuth
- Dodana CSRF zaštita (state parameter)
- Implementiran siguran transfer tokena preko sesije
- Dodata podrška za OAuth korisnike bez lozinke
- Kreirana dokumentacija