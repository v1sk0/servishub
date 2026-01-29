# ServisHub Security Architecture

**Last Updated:** 2026-01-29
**Version:** 1.1

Ovaj dokument opisuje sigurnosnu arhitekturu ServisHub aplikacije.
Namenjen je developerima i AI asistentima (Claude) za razumevanje security mehanizama.

---

## CURRENT STATUS (VAŽNO!)

| Feature | Status | Napomena |
|---------|--------|----------|
| Token Blacklist | **ENABLED** | `TOKEN_BLACKLIST_ENABLED=true` |
| Redis | **CONFIGURED** | Heroku Redis Mini addon aktivan |
| JWT with jti | Implemented | Svi novi tokeni imaju jti claim |
| File Security | Implemented | MIME, executable, macro detection |
| Production Config | Implemented | SECRET_KEY/JWT_SECRET_KEY validacija |

**Security Features AKTIVNI:**
- ✅ Redis token blacklist - logout invalidira JWT tokene
- ✅ FAIL-CLOSED mode u produkciji (SECURITY_STRICT=True)
- ✅ User-wide blacklist za password change

---

## Quick Reference

| Komponenta | Lokacija | Opis |
|------------|----------|------|
| Token Blacklist | `app/services/token_blacklist_service.py` | Redis-based JWT revokacija |
| JWT Utils | `app/api/middleware/jwt_utils.py` | Kreiranje tokena sa jti claim |
| Auth Middleware | `app/api/middleware/auth.py` | Dekoratori + blacklist check |
| File Security | `app/utils/file_security.py` | Upload validacija |
| Config | `app/config.py` | SECURITY_STRICT flag |
| Security Service | `app/services/security_service.py` | Rate limiting, event logging |

---

## 1. Autentifikacija (JWT)

### 1.1 Token Struktura

Svi JWT tokeni sadrze sledece claims:

```python
{
    'sub': user_id,           # Subject - ID korisnika/admina
    'jti': uuid4(),           # JWT ID - OBAVEZNO za revokaciju
    'type': 'access|refresh', # Tip tokena
    'iat': timestamp,         # Issued at
    'exp': timestamp,         # Expiration
    # Za tenant korisnike:
    'tenant_id': tenant_id,
    'role': 'OWNER|ADMIN|...',
    # Za platform admine:
    'is_admin': True,
    'role': 'SUPER_ADMIN|ADMIN|SUPPORT'
}
```

**VAZNO:** `jti` claim je OBAVEZAN za sve nove tokene. Koristi se za preciznu revokaciju.

### 1.2 Token Lifetime

| Token Type | Default | Config Key |
|------------|---------|------------|
| Access Token | 8 sati | `JWT_ACCESS_TOKEN_EXPIRES` |
| Refresh Token | 30 dana | `JWT_REFRESH_TOKEN_EXPIRES` |

### 1.3 Token Blacklist (KRITIČNO)

**Lokacija:** `app/services/token_blacklist_service.py`

Token blacklist omogucava invalidaciju tokena PRE isteka. Koristi se za:
- Logout (pojedinacni token)
- Password change (svi tokeni korisnika)
- Force logout od strane admina
- Detekcija sumnjive aktivnosti

**Strategija:**
1. **Individual blacklist:** `blacklist:jti:{jti}` - TTL = preostalo vreme tokena
2. **User-wide blacklist:** `blacklist:user:{id}:{type}` - timestamp invalidacije

**Fail-Mode Politika:**
- `SECURITY_STRICT=True` (produkcija): FAIL-CLOSED - odbij sve tokene ako Redis nije dostupan
- `SECURITY_STRICT=False` (development): FAIL-OPEN - dozvoli tokene ako Redis nije dostupan

```python
# Primer koriscenja
from app.services.token_blacklist_service import token_blacklist

# Blacklist pojedinacni token
token_blacklist.blacklist_token(token_payload)

# Blacklist SVE tokene korisnika
token_blacklist.blacklist_all_user_tokens(user_id, is_admin=False)

# Provera da li je blacklisted
is_blocked = token_blacklist.is_blacklisted(token_payload)
```

---

## 2. Autorizacija

### 2.1 Dekoratori

**Lokacija:** `app/api/middleware/auth.py`

| Dekorator | Opis | Redosled |
|-----------|------|----------|
| `@jwt_required` | Validira JWT, postavlja `g.token_payload` | 1 |
| `@tenant_required` | Ucitava tenant, proverava status | 2 (posle jwt_required) |
| `@admin_required` | Zahteva platform admin | 2 (posle jwt_required) |
| `@platform_admin_required` | Kombinovani (jwt + admin) | Standalone |
| `@role_required(...)` | Proverava korisnikovu rolu | 3 (posle tenant_required) |

**Primer:**
```python
@bp.route('/admin-only')
@jwt_required
@admin_required
def admin_route():
    admin = g.current_admin
    ...
```

### 2.2 Frontend Auth (Session-based)

Za admin panel postoji dodatna session-based autentifikacija:

**Lokacija:** `app/frontend/admin.py`

```python
@admin_frontend_required
def admin_dashboard():
    # Zahteva session['admin_authenticated'] = True
    ...
```

Session se postavlja na uspesnom login-u i brise na logout-u.

---

## 3. Rate Limiting

**Lokacija:** `app/services/security_service.py`

### 3.1 Preseti

| Preset | Max Requests | Window | Block |
|--------|--------------|--------|-------|
| `LOGIN` | 5 | 60s | 300s |
| `API` | 100 | 60s | 60s |
| `SENSITIVE` | 10 | 60s | 300s |

### 3.2 Trenutna Implementacija

Trenutno koristi `InMemoryRateLimiter`:
- Radi samo za jedan dyno/process
- Ne perzistentno preko restarta

### 3.3 Redis Rate Limiter (TODO - NIJE IMPLEMENTIRANO)

Planirano za produkciju sa vise dynos-a - `RedisRateLimiter` sa atomskim Lua skriptom.
Vidi SECURITY_HARDENING_PLAN.md za detalje.

---

## 4. File Upload Security

**Lokacija:** `app/utils/file_security.py`

### 4.1 Validacije

1. **MIME Type** - Magic bytes provera (python-magic ili filetype)
2. **Executable Detection** - Blokira PE, ELF, PHP, shell scripts
3. **Office Macro Detection** - Blokira VBA macro-e u xlsx/docx
4. **Size Limit** - Default 10MB
5. **Filename Sanitization** - Uklanja path traversal karaktere

### 4.2 Primer

```python
from app.utils.file_security import validate_upload

is_valid, error, safe_name = validate_upload(
    file_content=content,
    filename=original_name,
    allowed_extensions=['csv', 'xlsx'],
    max_size_mb=10
)

if not is_valid:
    return jsonify({'error': error}), 400
```

---

## 5. 2FA (Two-Factor Authentication)

**Lokacija:** `app/api/admin/auth.py`, `app/models/admin.py`

### 5.1 TOTP Implementacija

- Koristi `pyotp` library
- `valid_window=1` (trenutni + prethodni 30-sekundni interval)
- QR kod generisan sa `qrcode` library

### 5.2 Lockout Politika (TODO - NIJE IMPLEMENTIRANO)

Planirano ali nije implementirano:

| Failed Attempts | Lockout Duration |
|----------------|------------------|
| 5 | 30 minuta |
| 10 | 2 sata |
| 15 | 24 sata |

### 5.3 Anti-DoS Per-IP Tracking (TODO - NIJE IMPLEMENTIRANO)

Planirano ali nije implementirano:
- Per-IP tracking za sprečavanje DoS napada na 2FA
- Vidi SECURITY_HARDENING_PLAN.md za detalje implementacije

---

## 6. Security Events & Audit

**Lokacija:** `app/services/security_service.py`

### 6.1 Event Types

```python
class SecurityEventType(Enum):
    ADMIN_LOGIN_SUCCESS = 'admin_login_success'
    ADMIN_LOGIN_FAILED = 'admin_login_failed'
    TWO_FA_ENABLED = '2fa_enabled'
    TWO_FA_FAILED = '2fa_failed'
    RATE_LIMIT_EXCEEDED = 'rate_limit_exceeded'
    SUSPICIOUS_IP = 'suspicious_ip'
    # ...
```

### 6.2 Logovanje

```python
SecurityEventLogger.log_event(
    SecurityEventType.ADMIN_LOGIN_FAILED,
    details={'reason': 'wrong_password'},
    email='admin@example.com',
    level='warning'
)
```

---

## 7. Konfiguracija

### 7.1 Environment Variables

| Variable | Description | Required in Prod | Current |
|----------|-------------|------------------|---------|
| `SECRET_KEY` | Flask session secret | YES (32+ chars) | ✓ Set |
| `JWT_SECRET_KEY` | JWT signing key | YES (32+ chars) | ✓ Set |
| `REDIS_URL` | Redis connection | For blacklist | ✗ NOT SET |
| `SECURITY_STRICT` | Fail-closed mode | Auto (True in prod) | ✓ True |
| `TOKEN_BLACKLIST_ENABLED` | Blacklist on/off | Default: True | ✗ false |
| `CORS_ORIGINS` | Allowed origins | Auto-whitelist in prod | ✓ Auto |

### 7.2 Production Config

U `ProductionConfig` klasi:
- `SECURITY_STRICT = True` (uvek)
- SECRET_KEY/JWT_SECRET_KEY moraju biti setovani (app nece startovati bez njih)
- CORS nikad nije `*`

---

## 8. Security Checklist

### Pre-Deploy

- [ ] `SECRET_KEY` je random 32+ karaktera
- [ ] `JWT_SECRET_KEY` je random 32+ karaktera
- [ ] `REDIS_URL` je konfigurisan
- [ ] `CORS_ORIGINS` nije `*`
- [ ] `FLASK_ENV=production`

### Posle Login Implementacije

- [ ] Token ima `jti` claim
- [ ] Logout blacklist-uje token
- [ ] Password change blacklist-uje SVE tokene
- [ ] 2FA je omogucen za admine

### Za File Upload

- [ ] MIME type provera
- [ ] Size limit
- [ ] Filename sanitization
- [ ] Executable detection

---

## 9. Incident Response

### Kompromitovan Admin Nalog

1. Blacklist sve tokene korisnika:
   ```python
   token_blacklist.blacklist_all_user_tokens(admin_id, is_admin=True)
   ```

2. Onemoguciti nalog u bazi:
   ```python
   admin.is_active = False
   db.session.commit()
   ```

3. Pregledati audit log za aktivnost

### Kompromitovan JWT Secret

1. Promeniti `JWT_SECRET_KEY` u environment
2. Restart aplikacije (svi tokeni automatski postaju nevazeci)
3. Korisnici moraju ponovo da se uloguju

### Redis Nedostupan

- U produkciji (`SECURITY_STRICT=True`): Auth ce fail-ati (downtime)
- Popraviti Redis sto pre
- Rollback: `TOKEN_BLACKLIST_ENABLED=false` (privremeno)

---

## 10. Dalje Unapredjenje (TODO)

Vidi `SECURITY_HARDENING_PLAN.md` za detaljan plan sa 4 faze:

1. **Phase 1 (CRITICAL):** Token blacklist, Redis rate limiter, 2FA protection
2. **Phase 2 (HIGH):** TOTP window, JWT secret validation, password invalidation
3. **Phase 3 (MEDIUM):** Refresh token, CORS, CSP, file validation
4. **Phase 4 (LOW):** Alerts, mandatory 2FA, geo-IP, session limits

---

## Reference

- [OWASP JWT Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html)
- [Flask Security](https://flask.palletsprojects.com/en/2.0.x/security/)
- [pyotp Documentation](https://pyauth.github.io/pyotp/)
