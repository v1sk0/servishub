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

### 2.2 PKCE (Proof Key for Code Exchange)

**Problem:** Čak i sa CSRF zaštitom, napadač može presresti authorization code (npr. kroz maliciozni redirect ili browser extension) i iskoristiti ga pre legitimnog korisnika.

**Rešenje - PKCE S256:**
```python
# Generisanje code_verifier i code_challenge (auth.py)
import hashlib
import base64

# 1. Generiši random code_verifier (64 bajta = 86 karaktera)
code_verifier = secrets.token_urlsafe(64)
session['oauth_code_verifier'] = code_verifier

# 2. Kreiraj code_challenge = BASE64URL(SHA256(code_verifier))
code_challenge_bytes = hashlib.sha256(code_verifier.encode('ascii')).digest()
code_challenge = base64.urlsafe_b64encode(code_challenge_bytes).rstrip(b'=').decode('ascii')

# 3. Pošalji code_challenge u authorization request
params = {
    ...
    'code_challenge': code_challenge,
    'code_challenge_method': 'S256'
}

# 4. U callback-u, pošalji code_verifier pri razmeni koda
token_response = http_requests.post(
    'https://oauth2.googleapis.com/token',
    data={
        ...
        'code_verifier': code_verifier  # Google verifikuje SHA256(verifier) == challenge
    }
)
```

**Kako PKCE štiti:**
- Napadač koji presretne authorization code NE MOŽE ga iskoristiti
- Nema `code_verifier` koji je sačuvan samo u sesiji legitimnog korisnika
- Google odbija razmenu koda bez validnog `code_verifier`

### 2.3 Nonce (Replay Protection)

**Problem:** Napadač može pokušati replay napad koristeći stari authorization response.

**Rešenje:**
```python
# Generiši nonce i sačuvaj u sesiju
nonce = secrets.token_urlsafe(32)
session['oauth_nonce'] = nonce

# Pošalji u authorization request
params = {
    ...
    'nonce': nonce
}
```

**Karakteristike:**
- Jednokratna vrednost (number used once)
- Vraća se u ID tokenu od Google-a
- Može se verifikovati da odgovara originalnom zahtevu

### 2.4 Siguran Transfer Tokena

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

**Frontend preuzimanje - SINHRONO (tenant.html, `<head>` sekcija):**

> **KRITIČNO (v241):** Koristi se **sinhroni XMLHttpRequest** umesto async fetch.
> Ovo blokira SVE učitavanje stranice dok se tokeni ne preuzmu,
> sprečavajući race condition sa Alpine.js komponentama.

```javascript
// U <head> - izvršava se PRE Alpine.js
(function() {
    'use strict';
    const urlParams = new URLSearchParams(window.location.search);
    const authMethod = urlParams.get('auth');

    if (authMethod === 'oauth') {
        console.log('[OAuth] Detected auth=oauth, fetching tokens synchronously...');
        try {
            const xhr = new XMLHttpRequest();
            xhr.open('GET', '/api/v1/auth/google/tokens', false);  // false = SINHRONO
            xhr.withCredentials = true;
            xhr.send();

            if (xhr.status === 200) {
                const data = JSON.parse(xhr.responseText);
                localStorage.setItem('access_token', data.access_token);
                if (data.refresh_token) {
                    localStorage.setItem('refresh_token', data.refresh_token);
                }
                console.log('[OAuth] Tokens saved, redirecting...');
                window.location.replace(window.location.pathname);
            } else {
                console.error('[OAuth] Failed to get tokens:', xhr.status);
                window.location.replace('/login?error=oauth_token_' + xhr.status);
            }
        } catch (e) {
            console.error('[OAuth] Exception:', e);
            window.location.replace('/login?error=oauth_exception');
        }
    }
})();
```

**Karakteristike:**
- Tokeni se nikad ne pojavljuju u URL-u
- Endpoint `/api/v1/auth/google/tokens` je one-time use
- URL se čisti nakon preuzimanja tokena

### 2.5 One-Time Token Endpoint

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

### 2.6 Session Cookie Security

Flask session koristi cookie za čuvanje OAuth podataka (state, code_verifier, nonce). Sledeća podešavanja obezbeđuju sigurnost:

**Konfiguracija (config.py):**
```python
# Bazna konfiguracija
SESSION_COOKIE_HTTPONLY = True   # JavaScript ne može pristupiti cookie-u
SESSION_COOKIE_SAMESITE = 'Lax'  # CSRF zaštita za cookies
PERMANENT_SESSION_LIFETIME = timedelta(hours=1)  # Sesija ističe nakon 1 sat

# Produkcija (dodatno)
SESSION_COOKIE_SECURE = True     # Cookie se šalje samo preko HTTPS
```

**Zaštite:**
| Flag | Vrednost | Zaštita |
|------|----------|---------|
| `HTTPONLY` | True | XSS napadi ne mogu ukrasti cookie |
| `SAMESITE` | Lax | CSRF napadi ne mogu koristiti cookie |
| `SECURE` | True (prod) | MitM napadi ne mogu presresti cookie |
| `LIFETIME` | 1 sat | Ograničen prozor za napade |

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
    "auth_url": "https://accounts.google.com/o/oauth2/v2/auth?client_id=xxx&redirect_uri=xxx&response_type=code&scope=openid%20email%20profile&access_type=offline&prompt=select_account&state=xxx&code_challenge=xxx&code_challenge_method=S256&nonce=xxx"
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
| `pkce_invalid` | Code verifier nije pronađen | "Sigurnosna verifikacija nije uspela. Pokušajte ponovo." |
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
- [ ] PKCE zaštita - pokušaj bez code_verifier
- [ ] Token nije vidljiv u URL-u nakon login-a
- [ ] Token endpoint vraća 404 pri drugom pozivu (one-time)
- [ ] OAuth korisnik može da se uloguje bez lozinke
- [ ] Povezivanje Google naloga sa postojećim email nalogom
- [ ] Error handling za sve error case-ove
- [ ] Session cookie ima HttpOnly flag
- [ ] Session cookie ima SameSite=Lax
- [ ] Session cookie ima Secure flag (samo HTTPS, produkcija)

### 8.2 Manuelno Testiranje Sigurnosti

```bash
# 1. Test CSRF zaštite - pokušaj callback sa lažnim state-om
curl "https://servicehubdolce-4c283dce32e9.herokuapp.com/api/v1/auth/google/callback?code=xxx&state=fake"
# Očekivani rezultat: Redirect na /login?error=csrf_invalid

# 2. Test PKCE zaštite - pokušaj callback bez aktivne sesije
# (code_verifier nije u sesiji jer je nova sesija)
curl "https://servicehubdolce-4c283dce32e9.herokuapp.com/api/v1/auth/google/callback?code=xxx&state=valid_but_no_session"
# Očekivani rezultat: Redirect na /login?error=pkce_invalid

# 3. Proveri session cookie flags
curl -I "https://servicehubdolce-4c283dce32e9.herokuapp.com/login"
# Očekivano u Set-Cookie: HttpOnly; SameSite=Lax; Secure
```

---

## 9. Poznati Problemi i Ograničenja

### 9.1 Session Storage

- Flask session koristi cookie-based storage
- Maksimalna veličina cookie-ja je ~4KB
- Za veće podatke, razmotriti server-side session (Redis)

### 9.2 Token Expiry

- OAuth state, code_verifier i nonce su u Flask sesiji
- ✅ `PERMANENT_SESSION_LIFETIME = 1 sat` je konfigurisan
- Svi OAuth podaci automatski ističu nakon 1 sat neaktivnosti

### 9.3 Multiple Tabs

- Ako korisnik otvori OAuth u više tabova, samo jedan će uspeti
- State se briše nakon prvog korišćenja

---

## 10. Buduća Poboljšanja

1. **Apple Sign In** - Dodati podršku za Apple OAuth
2. **2FA** - Dvofaktorska autentifikacija
3. **Session Management** - Pregled i revokacija aktivnih sesija
4. **Rate Limiting** - Ograničiti broj OAuth pokušaja po IP-u
5. **Token Binding** - Vezivanje tokena za specifični uređaj/browser

---

## 11. Reference

- [Google OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)
- [OAuth 2.0 Security Best Practices](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-security-topics)
- [PKCE RFC 7636](https://datatracker.ietf.org/doc/html/rfc7636)
- [Flask Session Documentation](https://flask.palletsprojects.com/en/3.0.x/api/#sessions)
- [OWASP OAuth Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth_Cheat_Sheet.html)

---

## 12. Changelog

### v1.3 (23.01.2026)

**Kritični fix: Synchronous OAuth Token Handling**

**Problem:**
- Google OAuth login nije radio - posle Google autentifikacije, stranica bi se učitala i odmah izašla
- Race condition: Alpine.js komponente (sidebar, navigation) pokretale API pozive (`/api/v1/auth/me`) pre nego što su OAuth tokeni sačuvani u localStorage
- Asinhroni fetch u `x-init` nije garantovao da će se završiti pre drugih komponenti

**Uzrok (Heroku logs):**
```
[OAuth] Tokens saved successfully
[x-init sidebar] Starting loadTenantName
[x-init sidebar] Calling /api/v1/auth/me
401 Unauthorized - Token not found
```

**Rešenje:**
- Implementiran **sinhroni XMLHttpRequest** u `<head>` sekciji tenant.html
- Izvršava se PRE bilo kakvog JavaScript-a (uključujući Alpine.js)
- Blokira renderovanje stranice dok se tokeni ne preuzmu
- Nakon uspešnog preuzimanja, redirect na čist URL (bez `?auth=oauth`)

**Zašto sinhroni XHR:**
- `XMLHttpRequest` sa `async=false` je jedini način da se blokira JavaScript execution
- `fetch()` je uvek asinhrona - ne može blokirati
- `await` u `<head>` ne radi jer nije u async funkciji
- Bez blokiranja, Alpine.js počinje inicijalizaciju pre nego što su tokeni spremni

**Karakteristike rešenja:**
- ✅ Tokeni su u localStorage PRE nego što Alpine.js počne
- ✅ Sve komponente dobijaju validne tokene od starta
- ✅ Nema race condition-a
- ✅ Clean URL nakon redirect-a (bez `?auth=oauth` u history-ju)

---

### v1.2 (21.01.2026)
- ✅ Dodat Security Event Logging za OAuth tokove
- ✅ Implementiran tenant_id tracking za multi-tenant security
- ✅ OAuth login/logout se sada loguje sa tenant_id u security_event tabeli
- ✅ Admin panel podržava filtriranje OAuth eventova po tenantu

**Novi eventi koji se loguju:**
| Event | Opis |
|-------|------|
| `oauth_started` | Pokrenut OAuth flow |
| `oauth_success` | Uspešna OAuth prijava (sa tenant_id) |
| `oauth_failed` | Neuspešna OAuth prijava |
| `oauth_csrf_invalid` | Nevažeći CSRF state |
| `oauth_pkce_invalid` | Nevažeći PKCE verifier |

### v1.1 (16.01.2026)
- ✅ Dodat PKCE (Proof Key for Code Exchange) - SHA256 metod
- ✅ Dodat nonce parametar za replay protection
- ✅ Konfigurisani session cookie security flags:
  - HttpOnly (sprečava XSS krađu)
  - SameSite=Lax (CSRF zaštita)
  - Secure (samo HTTPS u produkciji)
- ✅ Postavljen PERMANENT_SESSION_LIFETIME = 1 sat
- Ažurirana dokumentacija

### v1.0 (16.01.2026)
- Inicijalna implementacija Google OAuth
- Dodana CSRF zaštita (state parameter)
- Implementiran siguran transfer tokena preko sesije
- Dodata podrška za OAuth korisnike bez lozinke
- Kreirana dokumentacija