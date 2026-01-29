# Pentagon-Level Security Hardening Plan
## ServisHub Admin Panel

**Datum:** 2026-01-29
**Verzija:** 1.2
**Autor:** Security Audit
**Status:** Draft - Red-team review COMPLETED
**Last Updated:** 2026-01-29 - All red-team findings addressed

---

## Executive Summary

ServisHub ima solidan sigurnosni temelj (bcrypt, JWT, 2FA, audit logging), ali postoje **kritične rupe** koje omogućavaju:

---

## ⚠️ Red-Team Review Findings

### CRITICAL Issues (must fix before implementation)

| # | Issue | Impact | Resolution |
|---|-------|--------|------------|
| 1 | **Redis fail-mode undefined** | Ako Redis padne, auth može fail-open (security bypass) ili fail-closed (DoS) | Eksplicitni feature flags + fail-closed politika |
| 2 | **Rate-limit race condition** | ZSET zcard+zadd nije atomsko; paralelni requests prolaze više nego treba | Atomic Lua script umesto ZSET |
| 3 | **Token blacklist bez jti** | sub+iat ne može precizno opozvati jedan token | Dodati jti claim u JWT |
| 4 | **2FA lockout = DoS vektor** | Napadač može namerno zaključati admin nalog | Per-IP limit + admin unlock flow |
| 5 | **Production detection krhka** | ENV/debug flag može pogrešno tretirati staging kao prod | Eksplicitna SECURITY_STRICT zastavica |

### MEDIUM Issues

| # | Issue | Resolution |
|---|-------|------------|
| 6 | python-magic na Windows može puknuti | Pure-python fallback (filetype lib) |
| 7 | ZIP detekcija blokira XLSX/ODS | Whitelist office formata |
| 8 | CSP report endpoint = spam vektor | Rate limit + auth |

### Open Questions (zahtevaju odluku)

- [ ] **Q1:** Da li logout invalidira i access i refresh token? → **Odluka: DA, oba**
- [ ] **Q2:** Fail-closed za admin auth ako Redis nije dostupan? → **Odluka: DA, fail-closed**
- [ ] **Q3:** Default unlock politika? → **Odluka: TTL 30min + admin manual unlock**
- [ ] **Q4:** TOTP valid_window=0 UX kompromis? → **Odluka: DA, uz sync upozorenje u UI**

### Implementation Notes from Red-Team

#### 2FA Lockout Anti-DoS Protection

**Problem:** Napadač može namerno uneti pogrešne 2FA kodove da zaključa admin nalog (DoS).

**Rešenje:** Per-IP tracking, ne samo per-user:

```python
# U record_2fa_failure(), dodaj IP tracking:
def record_2fa_failure(self, ip_address: str) -> tuple:
    """
    Zabeleži neuspeli 2FA pokušaj.

    Returns:
        (is_locked: bool, is_ip_blocked: bool)
    """
    # Per-user lockout (postojeće)
    self.totp_failed_attempts += 1

    # Per-IP tracking u Redis - sprečava DoS
    # Ako ista IP pravi 10+ neuspelih pokušaja za BILO KOJI nalog
    # blokira se IP, ne nalog
    ip_key = f"2fa_failures:{ip_address}"
    ip_failures = redis.incr(ip_key)
    redis.expire(ip_key, 3600)  # 1 sat

    if ip_failures >= 10:
        # Blokiraj IP, ne nalog
        redis.setex(f"2fa_blocked_ip:{ip_address}", 3600, "1")
        return False, True  # Nalog nije locked, IP jeste

    # Normalni per-user lockout
    if self.totp_failed_attempts >= 5:
        self.totp_locked_until = datetime.utcnow() + timedelta(minutes=30)
        return True, False

    return False, False
```

#### python-magic Windows Fallback

```python
# U file_security.py
def validate_file_mime(file_content: bytes, expected_extension: str) -> tuple:
    try:
        import magic
        detected_mime = magic.from_buffer(file_content, mime=True)
    except (ImportError, Exception):
        # Fallback za Windows ili ako python-magic nije instaliran
        try:
            import filetype
            kind = filetype.guess(file_content)
            detected_mime = kind.mime if kind else 'application/octet-stream'
        except ImportError:
            # Poslednji fallback - samo proveri ekstenziju
            import logging
            logging.warning("No MIME detection library available")
            return True, 'unknown'

    allowed = ALLOWED_MIMES.get(expected_extension.lower(), [])
    is_valid = detected_mime in allowed
    return is_valid, detected_mime
```

#### XLSX/ODS Whitelist (Office formati koriste ZIP)

```python
# U DANGEROUS_SIGNATURES, zameni ZIP detekciju:
DANGEROUS_SIGNATURES = [
    b'\x4d\x5a',           # MZ - Windows PE executable
    b'\x7f\x45\x4c\x46',   # ELF - Linux executable
    b'#!/',                # Shebang (shell script)
    b'<%',                 # ASP/JSP
    b'<?php',              # PHP
    b'<script',            # JavaScript in HTML
    # ZIP uklonjen - XLSX/ODS ga koriste legitimno
]

# Dodaj dozvoljene MIME tipove:
ALLOWED_MIMES = {
    # ... existing ...
    'xlsx': ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/zip'],
    'xls': ['application/vnd.ms-excel'],
    'ods': ['application/vnd.oasis.opendocument.spreadsheet', 'application/zip'],
}
```

#### CSP Report Endpoint Rate Limiting

```python
# U security.py
@bp.route('/csp-report', methods=['POST'])
@rate_limit(max_requests=10, window_seconds=60, block_seconds=300, endpoint_name='csp_report')
def csp_report():
    """Primi CSP violation report. Rate limited da spreči spam."""
    # ... existing code ...
```

#### Explicit SECURITY_STRICT Flag

```python
# U config.py
class Config:
    # Default: relaksiran u development-u
    SECURITY_STRICT = os.getenv('SECURITY_STRICT', 'false').lower() == 'true'

class ProductionConfig(Config):
    # Uvek strict u produkciji
    SECURITY_STRICT = True
```

---
- Korišćenje tokena posle logout-a
- Zaobilaženje rate limiting-a na više dynos
- Brute force napad na 2FA kodove

Ovaj plan definiše 15 sigurnosnih poboljšanja u 4 faze.

---

## Table of Contents

1. [Pronađene Ranjivosti](#pronađene-ranjivosti)
2. [Phase 1: Critical](#phase-1-critical-nedelja-1-2)
3. [Phase 2: High](#phase-2-high-nedelja-2-3)
4. [Phase 3: Medium](#phase-3-medium-nedelja-3-5)
5. [Phase 4: Enhancements](#phase-4-enhancements-nedelja-5-8)
6. [Potrebne Zavisnosti](#potrebne-zavisnosti)
7. [Verifikacija i Testiranje](#verifikacija-i-testiranje)
8. [Rollback Procedure](#rollback-procedure)

---

## Pronađene Ranjivosti

| # | Problem | Severity | Lokacija | Opis |
|---|---------|----------|----------|------|
| 1 | No Token Blacklist | CRITICAL | `auth.py` | Logout ne invalidira JWT - token radi do isteka |
| 2 | In-Memory Rate Limiter | CRITICAL | `security_service.py` | Gubi se na restart, ne radi na više dynos |
| 3 | No 2FA Brute Force Protection | CRITICAL | `auth.py` | 6 cifara = 1M kombinacija, nema rate limit |
| 4 | TOTP Window 90s | HIGH | `admin.py:151` | `valid_window=1` prihvata 3 intervala |
| 5 | Hardcoded JWT Secret | HIGH | `config.py:44` | Fallback 'jwt-secret-key-change-in-production' |
| 6 | No Password Change Invalidation | HIGH | `auth_service.py` | Stari tokeni nastavljaju da rade |
| 7 | 30-Day Refresh Token | MEDIUM | `config.py:48` | Predugo - treba 7 dana max |
| 8 | CORS Wildcard Default | MEDIUM | `config.py:82` | `'*'` može procureti u produkciju |
| 9 | CSP unsafe-inline/eval | MEDIUM | `security_headers.py` | Poništava XSS zaštitu |
| 10 | No File MIME Validation | MEDIUM | `bank_import.py` | Samo ekstenzija, ne stvarni tip |
| 11 | No Real-Time Alerts | LOW | N/A | Admin mora ručno proveravati logove |
| 12 | 2FA Optional for Admins | LOW | `admin.py:66` | Treba biti obavezno |
| 13 | No Geo-IP Detection | LOW | N/A | Impossible travel nije detektovan |
| 14 | No Concurrent Session Limits | LOW | N/A | Neograničen broj uređaja |
| 15 | No Password Change Token Rotation | LOW | `auth_service.py` | Postojeće sesije preživljavaju |

---

## Phase 1: CRITICAL (Nedelja 1-2)

### 1.1 Redis Token Blacklist

**Problem:** Kada se korisnik izloguje, njegov JWT token i dalje radi do isteka (8 sati za access, 30 dana za refresh).

**Rešenje:** Redis-based blacklist koji prati invalidirane tokene.

**Novi fajl:** `app/services/token_blacklist_service.py`

```python
"""
Token Blacklist Service - Redis-based JWT invalidation.

Koristi se za:
- Invalidaciju tokena na logout
- Invalidaciju SVIH tokena korisnika na password change
- Force logout od strane admina
"""
import redis
import hashlib
from flask import current_app
from datetime import datetime, timezone


class TokenBlacklistService:
    """
    Redis-based token blacklist.

    FAIL-MODE POLITIKA:
    - Ako Redis nije dostupan → FAIL-CLOSED (odbij sve tokene)
    - Ovo sprečava security bypass ali može izazvati kratki downtime
    - Feature flag: TOKEN_BLACKLIST_ENABLED (default: True u produkciji)

    Strategija:
    1. Individual token blacklist: blacklist:jti:{jti} -> TTL = token expiry
    2. User-wide blacklist: blacklist:user:{user_id} -> timestamp kada su svi invalidirani
    """

    def __init__(self):
        self._redis = None
        self._redis_available = None  # Cache connection status

    def _is_enabled(self) -> bool:
        """Proveri da li je blacklist uključen."""
        return current_app.config.get('TOKEN_BLACKLIST_ENABLED', True)

    def _check_redis_health(self) -> bool:
        """Proveri da li je Redis dostupan."""
        try:
            self.redis.ping()
            self._redis_available = True
            return True
        except Exception:
            self._redis_available = False
            return False

    @property
    def redis(self):
        """Lazy Redis connection."""
        if self._redis is None:
            redis_url = current_app.config.get('REDIS_URL', 'redis://localhost:6379/0')
            self._redis = redis.from_url(redis_url, decode_responses=True)
        return self._redis

    def _get_jti(self, token_payload: dict) -> str:
        """
        Dohvati JTI (JWT ID) iz tokena.

        VAŽNO: Token MORA imati jti claim. Ako nema, to je greška u generisanju tokena.
        """
        jti = token_payload.get('jti')
        if not jti:
            # FALLBACK za stare tokene bez jti - koristimo hash
            # Ovo treba ukloniti nakon što svi stari tokeni isteknu
            unique = f"{token_payload.get('sub')}:{token_payload.get('iat')}:{token_payload.get('type')}"
            return hashlib.sha256(unique.encode()).hexdigest()[:32]
        return jti

    def blacklist_token(self, token_payload: dict) -> bool:
        """
        Dodaj pojedinačni token u blacklist.
        TTL = preostalo vreme do isteka tokena.

        Args:
            token_payload: Dekodirani JWT payload

        Returns:
            True ako uspešno dodat
        """
        jti_hash = self._get_jti_hash(token_payload)
        exp = token_payload.get('exp', 0)
        now = datetime.now(timezone.utc).timestamp()
        ttl = max(int(exp - now), 0)

        if ttl > 0:
            self.redis.setex(f"blacklist:{jti_hash}", ttl, "1")
            return True
        return False

    def blacklist_all_user_tokens(self, user_id: int, is_admin: bool = False) -> bool:
        """
        Invalidiraj SVE tokene za korisnika.

        Koristi se kada:
        - Korisnik promeni lozinku
        - Admin force logout-uje korisnika
        - Detektovana sumnjiva aktivnost

        Args:
            user_id: ID korisnika
            is_admin: Da li je platform admin

        Returns:
            True ako uspešno
        """
        user_type = 'admin' if is_admin else 'tenant'
        key = f"blacklist:user:{user_id}:{user_type}"

        # Postavi marker sa timestampom - svi tokeni izdati PRE ovog vremena su nevažeći
        # TTL = max token lifetime (30 dana za refresh token)
        now = datetime.now(timezone.utc).timestamp()
        self.redis.setex(key, 2592000, str(now))
        return True

    def is_blacklisted(self, token_payload: dict) -> bool:
        """
        Proveri da li je token blacklisted.

        FAIL-MODE: FAIL-CLOSED
        - Ako Redis nije dostupan → vraća True (token se tretira kao blacklisted)
        - Ovo sprečava security bypass ali može izazvati auth failures

        Proverava:
        1. Redis dostupnost (fail-closed ako nije)
        2. Individual token blacklist (po jti)
        3. User-wide blacklist (token izdat pre invalidacije)

        Args:
            token_payload: Dekodirani JWT payload

        Returns:
            True ako je token blacklisted ILI ako Redis nije dostupan
        """
        # Feature flag check
        if not self._is_enabled():
            return False  # Blacklist disabled, sve prolazi

        # FAIL-CLOSED: Ako Redis nije dostupan, odbij token
        try:
            self.redis.ping()
        except Exception as e:
            import logging
            logging.error(f"Redis unavailable, FAIL-CLOSED active: {e}")
            # U produkciji: fail-closed (odbij sve)
            # U development-u: fail-open (propusti sve) za lakši dev
            if current_app.config.get('SECURITY_STRICT', True):
                return True  # FAIL-CLOSED
            return False  # FAIL-OPEN (samo development)

        # 1. Proveri individual blacklist po JTI
        jti = self._get_jti(token_payload)
        if self.redis.exists(f"blacklist:jti:{jti}"):
            return True

        # 2. Proveri user-wide blacklist
        user_id = token_payload.get('sub')
        is_admin = token_payload.get('is_admin', False)
        user_type = 'admin' if is_admin else 'tenant'
        key = f"blacklist:user:{user_id}:{user_type}"

        blacklist_time = self.redis.get(key)
        if blacklist_time:
            token_iat = token_payload.get('iat', 0)
            if token_iat < float(blacklist_time):
                return True

        return False

    def clear_user_blacklist(self, user_id: int, is_admin: bool = False) -> bool:
        """
        Obriši user-wide blacklist (npr. nakon što isteknu svi stari tokeni).
        Obično nije potrebno - TTL se brine za čišćenje.
        """
        user_type = 'admin' if is_admin else 'tenant'
        key = f"blacklist:user:{user_id}:{user_type}"
        self.redis.delete(key)
        return True


# Singleton instance
token_blacklist = TokenBlacklistService()
```

**KRITIČNO - Dodaj JTI claim u JWT generisanje:** `app/services/auth_service.py`

```python
import uuid

def generate_admin_tokens(self, admin: PlatformAdmin) -> dict:
    """Generiši access i refresh tokene za admina."""
    now = datetime.now(timezone.utc)

    # Access token
    access_payload = {
        'sub': admin.id,
        'jti': str(uuid.uuid4()),  # NOVO: Unique token ID
        'type': 'access',
        'is_admin': True,
        'email': admin.email,
        'iat': now.timestamp(),
        'exp': (now + current_app.config['JWT_ACCESS_TOKEN_EXPIRES']).timestamp()
    }

    # Refresh token
    refresh_payload = {
        'sub': admin.id,
        'jti': str(uuid.uuid4()),  # NOVO: Unique token ID
        'type': 'refresh',
        'is_admin': True,
        'iat': now.timestamp(),
        'exp': (now + current_app.config['JWT_REFRESH_TOKEN_EXPIRES']).timestamp()
    }

    # ... rest of token generation ...
```

**Modifikacija:** `app/api/middleware/auth.py`

```python
# Dodaj import na vrhu
from ...services.token_blacklist_service import token_blacklist

# U jwt_required dekoratoru, POSLE decode_token:
def jwt_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # ... existing token extraction and decode ...

        payload, error = decode_token(token)
        if error:
            return jsonify({'error': 'Unauthorized', 'message': error}), 401

        # NOVO: Proveri blacklist
        if token_blacklist.is_blacklisted(payload):
            return jsonify({
                'error': 'Unauthorized',
                'message': 'Token je poništen. Prijavite se ponovo.'
            }), 401

        # ... rest of decorator ...
```

**Modifikacija:** `app/api/admin/auth.py` - logout endpoint

```python
from ...services.token_blacklist_service import token_blacklist

@bp.route('/logout', methods=['POST'])
@jwt_required
@admin_required
def admin_logout():
    admin = g.current_admin

    # NOVO: Blacklist current token
    token_blacklist.blacklist_token(g.token_payload)

    # Obrisi session flag
    session.pop('admin_authenticated', None)
    session.pop('admin_id', None)

    AuditLog.log(
        entity_type='admin_auth',
        entity_id=admin.id,
        action=AuditAction.LOGOUT,
        changes={'token_blacklisted': True}
    )
    db.session.commit()

    return jsonify({'message': 'Uspesna odjava'}), 200
```

**Test:**
```bash
# 1. Login i dobij token
curl -X POST /api/admin/auth/login -d '{"email":"admin@test.com","password":"xxx"}'
# Response: {"tokens": {"access_token": "eyJ..."}}

# 2. Logout
curl -X POST /api/admin/auth/logout -H "Authorization: Bearer eyJ..."
# Response: {"message": "Uspesna odjava"}

# 3. Pokušaj koristiti stari token
curl -X GET /api/admin/dashboard -H "Authorization: Bearer eyJ..."
# Response: 401 {"error": "Token je poništen"}
```

---

### 1.2 Redis Rate Limiter

**Problem:** Trenutni `InMemoryRateLimiter` čuva podatke u memoriji procesa:
- Gubi se na restart dynoa
- Svaki dyno ima svoju kopiju - napadač može da pošalje 5 req × N dynos

**Rešenje:** Redis-based rate limiter sa sliding window algoritmom.

**Modifikacija:** `app/services/security_service.py`

```python
# Dodaj novu klasu (zadrži InMemoryRateLimiter kao fallback)

class RedisRateLimiter:
    """
    Redis-based rate limiter using sliding window algorithm with ATOMIC Lua script.

    Prednosti:
    - Radi na više procesa/dynos
    - Perzistentno preko restarta
    - Tačniji sliding window (vs fixed window)
    - ATOMSKI: Lua script sprečava race conditions

    FAIL-MODE: FAIL-OPEN (dozvoli request ako Redis nije dostupan)
    - Rate limiting nije kritično za security kao token blacklist
    - Bolje je dozvoliti malo više requestova nego potpuno blokirati servis
    """

    # Lua script za atomsko rate limiting
    # Izvršava cleanup + count + add u jednoj atomskoj operaciji
    RATE_LIMIT_SCRIPT = """
    local key = KEYS[1]
    local block_key = KEYS[2]
    local now = tonumber(ARGV[1])
    local window = tonumber(ARGV[2])
    local max_requests = tonumber(ARGV[3])
    local request_id = ARGV[4]

    -- Proveri block status
    if redis.call('EXISTS', block_key) == 1 then
        return {1, 0}  -- blocked, 0 remaining
    end

    -- Atomski: cleanup starih + count + add novog
    local cutoff = now - window
    redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)

    local count = redis.call('ZCARD', key)

    if count >= max_requests then
        return {1, 0}  -- rate limited, 0 remaining
    end

    -- Dodaj request sa unique ID (sprečava duplicate entries)
    redis.call('ZADD', key, now, request_id)
    redis.call('EXPIRE', key, window + 1)

    local remaining = max_requests - count - 1
    return {0, remaining}  -- not limited, remaining count
    """

    def __init__(self):
        self._redis = None
        self._script_sha = None

    @property
    def redis(self):
        if self._redis is None:
            from flask import current_app
            redis_url = current_app.config.get('REDIS_URL')
            if redis_url:
                import redis
                self._redis = redis.from_url(redis_url, decode_responses=True)
        return self._redis

    def _get_script_sha(self):
        """Učitaj Lua script u Redis i vrati SHA za EVALSHA."""
        if self._script_sha is None:
            self._script_sha = self.redis.script_load(self.RATE_LIMIT_SCRIPT)
        return self._script_sha

    def _get_key(self, ip: str, endpoint: str) -> str:
        """Redis key za tracking requests."""
        return f"ratelimit:{endpoint}:{ip}"

    def _get_block_key(self, ip: str, endpoint: str) -> str:
        """Redis key za block status."""
        return f"ratelimit:block:{endpoint}:{ip}"

    def is_rate_limited(
        self,
        ip: str,
        endpoint: str,
        max_requests: int,
        window_seconds: int
    ) -> tuple:
        """
        Proveri da li je IP rate limited.

        Koristi ATOMSKI Lua script za sliding window.
        Unique request ID sprečava race condition duplikata.

        Returns:
            (is_limited: bool, remaining: int)
        """
        import uuid

        key = self._get_key(ip, endpoint)
        block_key = self._get_block_key(ip, endpoint)
        now = datetime.now(timezone.utc).timestamp()
        request_id = f"{now}:{uuid.uuid4().hex[:8]}"  # Unique per request

        try:
            # Izvrši atomski Lua script
            result = self.redis.evalsha(
                self._get_script_sha(),
                2,  # broj KEYS
                key, block_key,  # KEYS
                now, window_seconds, max_requests, request_id  # ARGV
            )

            is_limited = bool(result[0])
            remaining = int(result[1])
            return is_limited, remaining

        except Exception as e:
            # FAIL-OPEN: Ako Redis nije dostupan, dozvoli request
            import logging
            logging.warning(f"Redis rate limiter failed, FAIL-OPEN: {e}")
            return False, max_requests

    def block_ip(self, ip: str, endpoint: str, block_seconds: int) -> None:
        """Blokiraj IP za određeno vreme."""
        block_key = self._get_block_key(ip, endpoint)
        self.redis.setex(block_key, block_seconds, "1")

    def get_block_remaining(self, ip: str, endpoint: str) -> int:
        """Vrati preostalo vreme blokade u sekundama."""
        block_key = self._get_block_key(ip, endpoint)
        ttl = self.redis.ttl(block_key)
        return max(0, ttl)

    def unblock_ip(self, ip: str, endpoint: str) -> bool:
        """Ručno deblokiraj IP (admin action)."""
        block_key = self._get_block_key(ip, endpoint)
        return self.redis.delete(block_key) > 0


def get_rate_limiter():
    """
    Factory function - vraća odgovarajući rate limiter.

    Prioritet:
    1. Redis (ako je REDIS_URL konfigurisan)
    2. In-Memory fallback (development)
    """
    try:
        from flask import current_app
        if current_app.config.get('REDIS_URL'):
            limiter = RedisRateLimiter()
            if limiter.redis:  # Test connection
                limiter.redis.ping()
                return limiter
    except Exception as e:
        import logging
        logging.warning(f"Redis rate limiter unavailable: {e}, falling back to in-memory")

    return InMemoryRateLimiter()


# Modifikuj rate_limit dekorator da koristi factory
def rate_limit(max_requests: int, window_seconds: int, block_seconds: int,
               endpoint_name: str = None, save_to_db: bool = True):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            limiter = get_rate_limiter()  # NOVO: koristi factory
            ip = SecurityEventLogger._get_client_ip()
            endpoint = endpoint_name or request.endpoint or 'unknown'

            # ... rest of decorator stays the same ...
```

**Test za multi-dyno:**
```bash
# Na Heroku sa 2 dynos:

# Dyno 1: 5 requests
for i in {1..5}; do curl -X POST /api/admin/auth/login; done
# Dyno 2: Sledeći request treba da bude blokiran
curl -X POST /api/admin/auth/login
# Response: 429 Too Many Requests
```

---

### 1.3 2FA Brute Force Protection

**Problem:** 6-cifreni TOTP kod ima samo 1,000,000 kombinacija. Bez rate limiting-a, napadač može probati sve u minutima.

**Rešenje:**
1. Per-user failure counter sa lockout
2. Strožiji rate limit na 2FA endpoint
3. Exponential backoff

**Modifikacija:** `app/models/admin.py` - dodaj polja

```python
class PlatformAdmin(db.Model):
    # ... existing fields ...

    # 2FA Lockout Tracking
    totp_failed_attempts = db.Column(db.Integer, default=0, nullable=False)
    totp_locked_until = db.Column(db.DateTime, nullable=True)
    totp_last_failed_at = db.Column(db.DateTime, nullable=True)

    def is_2fa_locked(self) -> bool:
        """
        Proveri da li je 2FA zaključan zbog previše pokušaja.

        Returns:
            True ako je locked
        """
        if self.totp_locked_until:
            if datetime.utcnow() < self.totp_locked_until:
                return True
            # Lock istekao - resetuj
            self.totp_locked_until = None
            self.totp_failed_attempts = 0
        return False

    def record_2fa_failure(self) -> bool:
        """
        Zabeleži neuspeli 2FA pokušaj.

        Lockout pravila:
        - 5 neuspelih pokušaja = 30 min lock
        - 10 neuspelih = 2 sata lock
        - 15 neuspelih = 24 sata lock

        Returns:
            True ako je sada locked
        """
        self.totp_failed_attempts += 1
        self.totp_last_failed_at = datetime.utcnow()

        # Progresivni lockout
        if self.totp_failed_attempts >= 15:
            self.totp_locked_until = datetime.utcnow() + timedelta(hours=24)
            return True
        elif self.totp_failed_attempts >= 10:
            self.totp_locked_until = datetime.utcnow() + timedelta(hours=2)
            return True
        elif self.totp_failed_attempts >= 5:
            self.totp_locked_until = datetime.utcnow() + timedelta(minutes=30)
            return True

        return False

    def reset_2fa_failures(self) -> None:
        """Resetuj failure counter na uspešan login."""
        self.totp_failed_attempts = 0
        self.totp_locked_until = None
        self.totp_last_failed_at = None

    def get_2fa_lock_remaining(self) -> int:
        """Vrati preostalo vreme lockout-a u sekundama."""
        if self.totp_locked_until:
            remaining = (self.totp_locked_until - datetime.utcnow()).total_seconds()
            return max(0, int(remaining))
        return 0
```

**Dodaj novi rate limit preset:** `app/services/security_service.py`

```python
class RateLimits:
    # Existing presets...
    LOGIN = {'max_requests': 5, 'window_seconds': 60, 'block_seconds': 300}

    # NOVO: 2FA - strožiji limit
    TWO_FA = {
        'max_requests': 3,      # Samo 3 pokušaja
        'window_seconds': 300,  # U 5 minuta
        'block_seconds': 900    # 15 min block
    }
```

**Modifikacija:** `app/api/admin/auth.py` - 2FA endpoint

```python
@bp.route('/login/2fa', methods=['POST'])
@rate_limit(**RateLimits.TWO_FA, endpoint_name='admin_2fa_verify')
def admin_login_2fa():
    """
    Login platform admina (Step 2 - 2FA verifikacija).

    SECURITY:
    - Rate limited: 3 pokušaja / 5 min
    - Per-user lockout: 5 failures = 30min, 10 = 2h, 15 = 24h
    """
    try:
        data = TwoFactorVerifyRequest(**request.get_json())
    except ValidationError as e:
        return jsonify({'error': 'Validation Error', 'details': e.errors()}), 400

    # Verifikuj session
    pending_email = session.pop('pending_2fa_admin_email', None)
    if not pending_email or pending_email != data.email:
        return jsonify({
            'error': 'Session Error',
            'message': 'Sesija je istekla. Prijavite se ponovo.'
        }), 401

    # Pronađi admina
    admin = PlatformAdmin.query.filter_by(email=data.email, is_active=True).first()
    if not admin:
        return jsonify({'error': 'Login Error', 'message': 'Admin nije pronadjen'}), 401

    # NOVO: Proveri 2FA lockout
    if admin.is_2fa_locked():
        remaining = admin.get_2fa_lock_remaining()
        minutes = remaining // 60

        SecurityEventLogger.log_event(
            SecurityEventType.TWO_FA_FAILED,
            details={
                'reason': '2fa_locked',
                'locked_until': admin.totp_locked_until.isoformat(),
                'attempts': admin.totp_failed_attempts
            },
            user_id=admin.id,
            email=admin.email,
            level='warning'
        )

        return jsonify({
            'error': '2FA Locked',
            'message': f'Previše neuspelih pokušaja. Pokušajte za {minutes} minuta.',
            'retry_after': remaining
        }), 429

    # Verifikuj kod
    code_valid = False
    if data.use_backup:
        code_valid = admin.use_backup_code(data.code)
    else:
        code_valid = admin.verify_totp(data.code)

    if not code_valid:
        # NOVO: Record failure
        is_locked = admin.record_2fa_failure()
        db.session.commit()

        remaining_attempts = max(0, 5 - admin.totp_failed_attempts)

        SecurityEventLogger.log_event(
            SecurityEventType.TWO_FA_FAILED,
            details={
                'reason': '2fa_code_invalid',
                'use_backup': data.use_backup,
                'attempts': admin.totp_failed_attempts,
                'locked': is_locked
            },
            user_id=admin.id,
            email=admin.email,
            level='warning' if not is_locked else 'error'
        )

        if is_locked:
            remaining = admin.get_2fa_lock_remaining()
            return jsonify({
                'error': '2FA Locked',
                'message': f'Previše neuspelih pokušaja. Nalog je zaključan.',
                'retry_after': remaining
            }), 429

        return jsonify({
            'error': '2FA Error',
            'message': f'Neispravan kod. Preostalo pokušaja: {remaining_attempts}'
        }), 401

    # USPEH - resetuj failures
    admin.reset_2fa_failures()
    admin.update_last_login()
    db.session.commit()

    # Generiši tokene
    tokens = auth_service.generate_admin_tokens(admin)

    # Postavi session
    session['admin_authenticated'] = True
    session['admin_id'] = admin.id

    SecurityEventLogger.log_event(
        SecurityEventType.ADMIN_LOGIN_SUCCESS,
        details={'step': '2/2', '2fa_verified': True, 'used_backup': data.use_backup},
        user_id=admin.id,
        email=admin.email
    )

    return jsonify({
        'admin': admin.to_dict(),
        'tokens': {
            'access_token': tokens['access_token'],
            'refresh_token': tokens['refresh_token'],
            'token_type': 'Bearer',
            'expires_in': tokens['expires_in']
        }
    }), 200
```

**Migracija baze:**
```bash
flask db migrate -m "Add 2FA lockout fields to PlatformAdmin"
flask db upgrade
```

---

## Phase 2: HIGH (Nedelja 2-3)

### 2.1 Smanji TOTP Window

**Problem:** `valid_window=1` znači da se prihvata trenutni + prethodni + sledeći 30-sekundni interval = 90 sekundi ukupno.

**Rešenje:** Smanji na `valid_window=0` (samo trenutnih 30 sekundi).

**Fajl:** `app/models/admin.py`

```python
def verify_totp(self, code: str) -> bool:
    """
    Verifikuj TOTP kod.

    SECURITY: valid_window=0 znači samo trenutni 30-sekundni interval.
    Zahteva tačno sinhronizovan sat na telefonu.
    """
    if not self.totp_secret:
        return False

    totp = pyotp.TOTP(self.totp_secret)
    # PROMENJENO: valid_window=0 (bilo valid_window=1)
    return totp.verify(code, valid_window=0)
```

**Napomena:** Korisnici sa loše sinhronizovanim satom mogu imati problema. Razmotri dodavanje instrukcije o sinhronizaciji sata u UI.

---

### 2.2 Eliminiši Hardcoded JWT Secret

**Problem:** U `config.py` postoji fallback vrednost za JWT secret:
```python
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'jwt-secret-key-change-in-production')
```

Ako neko zaboravi da postavi env var, koristi se slaba default vrednost.

**Rešenje:** Eksplicitna validacija u produkciji.

**Fajl:** `app/config.py`

```python
class Config:
    """Base configuration - development defaults."""

    # Development: dozvoljen fallback
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'jwt-secret-key-change-in-production')


class ProductionConfig(Config):
    """Production configuration - strict validation."""

    DEBUG = False
    TESTING = False

    @property
    def SECRET_KEY(self):
        """Flask SECRET_KEY - mora biti eksplicitno setovan."""
        key = os.getenv('SECRET_KEY')
        if not key:
            raise ValueError(
                "CRITICAL: SECRET_KEY environment variable must be set in production!\n"
                "Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        if len(key) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return key

    @property
    def JWT_SECRET_KEY(self):
        """JWT signing key - mora biti eksplicitno setovan."""
        key = os.getenv('JWT_SECRET_KEY')
        if not key:
            raise ValueError(
                "CRITICAL: JWT_SECRET_KEY environment variable must be set in production!\n"
                "Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        if len(key) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters")
        return key
```

**Fajl:** `app/__init__.py` - startup validacija

```python
def create_app(config_class=None):
    app = Flask(__name__)

    if config_class is None:
        config_class = get_config()

    app.config.from_object(config_class)

    # NOVO: Validacija sigurnosne konfiguracije
    _validate_security_config(app)

    # ... rest of create_app ...


def _validate_security_config(app):
    """
    Validacija kritičnih sigurnosnih postavki.
    Baca ValueError ako su detekovane nesigurne vrednosti u produkciji.
    """
    is_production = app.config.get('ENV') == 'production' or not app.debug

    if not is_production:
        return  # Skip validation u development-u

    # Lista poznatih nesigurnih default vrednosti
    INSECURE_DEFAULTS = [
        'jwt-secret-key-change-in-production',
        'dev-secret-key-change-in-production',
        'your-jwt-secret-key',
        'your-super-secret-key',
        'changeme',
        'secret',
        'password',
    ]

    jwt_key = app.config.get('JWT_SECRET_KEY', '')
    secret_key = app.config.get('SECRET_KEY', '')

    for insecure in INSECURE_DEFAULTS:
        if insecure.lower() in jwt_key.lower():
            app.logger.critical(
                f"SECURITY CRITICAL: JWT_SECRET_KEY contains insecure default value!"
            )
            raise ValueError("Insecure JWT_SECRET_KEY detected in production")

        if insecure.lower() in secret_key.lower():
            app.logger.critical(
                f"SECURITY CRITICAL: SECRET_KEY contains insecure default value!"
            )
            raise ValueError("Insecure SECRET_KEY detected in production")

    # Proveri minimalnu dužinu
    if len(jwt_key) < 32:
        raise ValueError("JWT_SECRET_KEY must be at least 32 characters in production")

    if len(secret_key) < 32:
        raise ValueError("SECRET_KEY must be at least 32 characters in production")

    app.logger.info("Security configuration validated successfully")
```

**Test:**
```bash
# Produkcija bez JWT_SECRET_KEY
FLASK_ENV=production flask run
# Error: CRITICAL: JWT_SECRET_KEY environment variable must be set in production!

# Produkcija sa slabim ključem
JWT_SECRET_KEY=short FLASK_ENV=production flask run
# Error: JWT_SECRET_KEY must be at least 32 characters
```

---

### 2.3 Invalidacija Tokena na Password Change

**Problem:** Kada korisnik promeni lozinku, stari tokeni nastavljaju da rade. Ako je napadač ukrao token, i dalje ima pristup.

**Rešenje:** Blacklist-uj sve korisnikove tokene na password change.

**Fajl:** `app/services/auth_service.py`

```python
from .token_blacklist_service import token_blacklist

class AuthService:
    # ... existing methods ...

    def change_admin_password(
        self,
        admin: PlatformAdmin,
        current_password: str,
        new_password: str
    ) -> bool:
        """
        Promeni lozinku admina.

        SECURITY:
        - Verifikuje trenutnu lozinku
        - Postavlja novu lozinku (bcrypt)
        - Invalidira SVE aktivne tokene
        - Loguje security event
        """
        # Verifikuj trenutnu lozinku
        if not admin.check_password(current_password):
            SecurityEventLogger.log_event(
                SecurityEventType.ADMIN_ACTION,
                details={'action': 'password_change_failed', 'reason': 'wrong_current'},
                user_id=admin.id,
                email=admin.email,
                level='warning'
            )
            raise AuthError('Trenutna lozinka nije ispravna', 400)

        # Postavi novu lozinku
        admin.set_password(new_password)

        # KRITIČNO: Invalidiraj sve tokene
        token_blacklist.blacklist_all_user_tokens(admin.id, is_admin=True)

        # Loguj
        SecurityEventLogger.log_event(
            SecurityEventType.ADMIN_ACTION,
            details={
                'action': 'password_changed',
                'tokens_invalidated': True,
                'affected_sessions': 'all'
            },
            user_id=admin.id,
            email=admin.email,
            level='info'
        )

        AuditLog.log(
            entity_type='platform_admin',
            entity_id=admin.id,
            action=AuditAction.UPDATE,
            changes={'password': {'old': '[REDACTED]', 'new': '[REDACTED]'}}
        )

        db.session.commit()
        return True

    def change_user_password(
        self,
        user: TenantUser,
        current_password: str,
        new_password: str
    ) -> bool:
        """
        Promeni lozinku tenant usera.

        SECURITY: Ista logika kao za admina.
        """
        if not user.check_password(current_password):
            raise AuthError('Trenutna lozinka nije ispravna', 400)

        user.set_password(new_password)

        # Invalidiraj sve tokene
        token_blacklist.blacklist_all_user_tokens(user.id, is_admin=False)

        SecurityEventLogger.log_event(
            SecurityEventType.ADMIN_ACTION,  # ili USER_ACTION ako postoji
            details={'action': 'password_changed', 'tokens_invalidated': True},
            user_id=user.id,
            tenant_id=user.tenant_id,
            level='info'
        )

        db.session.commit()
        return True
```

**Endpoint:** `app/api/admin/auth.py`

```python
@bp.route('/change-password', methods=['POST'])
@jwt_required
@admin_required
def change_password():
    """
    Promena lozinke admina.

    SECURITY: Invalidira sve postojeće sesije.
    Admin mora ponovo da se uloguje.
    """
    try:
        data = request.get_json()
        current_password = data.get('current_password')
        new_password = data.get('new_password')

        if not current_password or not new_password:
            return jsonify({'error': 'Nedostaju podaci'}), 400

        if len(new_password) < 8:
            return jsonify({'error': 'Nova lozinka mora imati minimum 8 karaktera'}), 400

        auth_service.change_admin_password(
            g.current_admin,
            current_password,
            new_password
        )

        return jsonify({
            'message': 'Lozinka uspešno promenjena. Sve sesije su poništene.',
            'require_relogin': True
        }), 200

    except AuthError as e:
        return jsonify({'error': e.message}), e.code
```

---

## Phase 3: MEDIUM (Nedelja 3-5)

### 3.1 Smanji Refresh Token Lifetime

**Fajl:** `app/config.py`

```python
# Staro:
JWT_REFRESH_TOKEN_EXPIRES = timedelta(seconds=int(os.getenv('JWT_REFRESH_TOKEN_EXPIRES', 2592000)))  # 30 dana

# Novo:
JWT_REFRESH_TOKEN_EXPIRES = timedelta(seconds=int(os.getenv('JWT_REFRESH_TOKEN_EXPIRES', 604800)))  # 7 dana
```

**Migracija:** Postojeći tokeni sa 30-dnevnim TTL-om će nastaviti da rade. Za force invalidaciju, koristi token blacklist.

---

### 3.2 CORS Whitelist

**Fajl:** `app/config.py`

```python
class Config:
    # Development: localhost origins
    CORS_ORIGINS = os.getenv(
        'CORS_ORIGINS',
        'http://localhost:3000,http://localhost:5000,http://127.0.0.1:5000'
    ).split(',')


class ProductionConfig(Config):
    @property
    def CORS_ORIGINS(self):
        """
        Production CORS - eksplicitan whitelist.
        Ne dozvoljava wildcard '*'.
        """
        origins = os.getenv('CORS_ORIGINS', '')

        # Ako nije setovano ili je wildcard, koristi default whitelist
        if not origins or origins.strip() == '*':
            return [
                'https://servishub.rs',
                'https://www.servishub.rs',
                'https://app.servishub.rs',
            ]

        # Parsiraj iz env var
        return [o.strip() for o in origins.split(',') if o.strip()]
```

---

### 3.3 CSP Improvements (Fazno)

**Faza 1:** Dodaj CSP violation reporting

```python
# security_headers.py
def _get_csp_policy(is_production: bool = False) -> str:
    directives = {
        # ... existing directives ...

        # NOVO: Report violations
        "report-uri": "/api/admin/security/csp-report",
    }
```

**Faza 2:** Implementiraj nonce-based inline scripts (zahteva frontend promene)

**Faza 3:** Ukloni unsafe-inline i unsafe-eval

---

### 3.4 File MIME Validation

**Novi fajl:** `app/utils/file_security.py`

```python
"""
File Security Utilities.

Validacija uploadovanih fajlova:
- MIME type checking (magic bytes)
- Executable detection
- Size limits
"""
import magic  # python-magic library

# Dozvoljeni MIME tipovi po ekstenziji
ALLOWED_MIMES = {
    'csv': ['text/csv', 'text/plain', 'application/csv'],
    'xml': ['text/xml', 'application/xml'],
    'txt': ['text/plain'],
    'pdf': ['application/pdf'],
    'png': ['image/png'],
    'jpg': ['image/jpeg'],
    'jpeg': ['image/jpeg'],
}

# Opasni magic bytes (executable signatures)
DANGEROUS_SIGNATURES = [
    b'\x4d\x5a',           # MZ - Windows PE executable
    b'\x7f\x45\x4c\x46',   # ELF - Linux executable
    b'#!/',                # Shebang (shell script)
    b'<%',                 # ASP/JSP
    b'<?php',              # PHP
    b'<script',            # JavaScript in HTML
    b'PK\x03\x04',         # ZIP (could contain malware)
]


def validate_file_mime(file_content: bytes, expected_extension: str) -> tuple:
    """
    Validira da MIME tip fajla odgovara očekivanoj ekstenziji.

    Args:
        file_content: Raw bytes sadržaja fajla
        expected_extension: Očekivana ekstenzija (bez tačke)

    Returns:
        (is_valid: bool, detected_mime: str)
    """
    try:
        detected_mime = magic.from_buffer(file_content, mime=True)
        allowed = ALLOWED_MIMES.get(expected_extension.lower(), [])
        is_valid = detected_mime in allowed
        return is_valid, detected_mime
    except Exception as e:
        return False, f"Error: {str(e)}"


def check_no_executable(file_content: bytes) -> bool:
    """
    Proveri da fajl ne sadrži executable signature.

    Args:
        file_content: Raw bytes

    Returns:
        True ako je fajl SIGURAN (nema executable)
    """
    header = file_content[:100]
    for sig in DANGEROUS_SIGNATURES:
        if sig in header:
            return False
    return True


def validate_file_size(file_content: bytes, max_size_mb: int = 10) -> bool:
    """
    Proveri da fajl nije prevelik.

    Args:
        file_content: Raw bytes
        max_size_mb: Maksimalna veličina u MB

    Returns:
        True ako je veličina OK
    """
    max_bytes = max_size_mb * 1024 * 1024
    return len(file_content) <= max_bytes


def sanitize_filename(filename: str) -> str:
    """
    Sanitizuj filename - ukloni opasne karaktere.

    Args:
        filename: Originalni filename

    Returns:
        Sanitizovani filename
    """
    import re
    # Ukloni path separatore
    filename = filename.replace('/', '_').replace('\\', '_')
    # Zadrži samo alphanumeric, tačku, minus, underscore
    filename = re.sub(r'[^\w\.\-]', '_', filename)
    # Spreči hidden files
    if filename.startswith('.'):
        filename = '_' + filename
    return filename
```

**Modifikacija:** `app/api/admin/bank_import.py`

```python
from app.utils.file_security import (
    validate_file_mime,
    check_no_executable,
    validate_file_size,
    sanitize_filename
)

@bp.route('', methods=['POST'])
@platform_admin_required
def upload_statement():
    """Upload bankovnog izvoda sa sigurnosnim proverama."""

    if 'file' not in request.files:
        return jsonify({'error': 'Fajl nije prosleđen'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Nije izabran fajl'}), 400

    # Sanitize filename
    safe_filename = sanitize_filename(file.filename)
    extension = safe_filename.rsplit('.', 1)[-1].lower() if '.' in safe_filename else ''

    # Proveri ekstenziju
    if extension not in ['csv', 'xml', 'txt']:
        return jsonify({'error': f'Nedozvoljena ekstenzija: .{extension}'}), 400

    # Čitaj sadržaj
    file_content = file.read()

    # SECURITY: Proveri veličinu
    if not validate_file_size(file_content, max_size_mb=10):
        return jsonify({'error': 'Fajl je prevelik (max 10MB)'}), 400

    # SECURITY: Proveri MIME tip
    is_valid_mime, detected_mime = validate_file_mime(file_content, extension)
    if not is_valid_mime:
        SecurityEventLogger.log_event(
            SecurityEventType.SUSPICIOUS_IP,
            details={
                'action': 'mime_mismatch_blocked',
                'filename': safe_filename,
                'expected': extension,
                'detected': detected_mime
            },
            level='warning'
        )
        return jsonify({
            'error': f'Tip fajla ({detected_mime}) ne odgovara ekstenziji (.{extension})'
        }), 400

    # SECURITY: Proveri za executable
    if not check_no_executable(file_content):
        SecurityEventLogger.log_event(
            SecurityEventType.SUSPICIOUS_IP,
            details={
                'action': 'executable_upload_blocked',
                'filename': safe_filename
            },
            level='error'
        )
        return jsonify({'error': 'Detektovan potencijalno opasan fajl'}), 400

    # Nastavi sa procesuiranjem...
```

---

## Phase 4: Enhancements (Nedelja 5-8)

### 4.1 Security Notifications Tab (Admin Panel)

**Lokacija:** `/admin/security` → novi tab "Notifications"

**Opis:** Admin može konfigurisati email notifikacije za različite tipove security events.

#### 4.1.1 Database Model

**Novi fajl:** `app/models/security_notification_settings.py`

```python
"""
Security Notification Settings Model.

Čuva konfiguraciju za email notifikacije security events-a.
"""
from app.extensions import db
from datetime import datetime


class SecurityNotificationSettings(db.Model):
    """
    Podešavanja za security notifikacije.

    Svaki admin može imati svoja podešavanja, ili može postojati
    globalna konfiguracija (admin_id = None).
    """
    __tablename__ = 'security_notification_settings'

    id = db.Column(db.Integer, primary_key=True)

    # Null = globalna podešavanja, inače per-admin
    admin_id = db.Column(db.Integer, db.ForeignKey('platform_admin.id'), nullable=True)

    # Email za notifikacije (može biti različit od admin email-a)
    notification_email = db.Column(db.String(255), nullable=False)

    # Koji severity nivoi triggeruju email
    notify_critical = db.Column(db.Boolean, default=True, nullable=False)
    notify_error = db.Column(db.Boolean, default=True, nullable=False)
    notify_warning = db.Column(db.Boolean, default=False, nullable=False)
    notify_info = db.Column(db.Boolean, default=False, nullable=False)

    # Specifični event tipovi (JSON array)
    # Npr: ["admin_login_failed", "2fa_lockout", "rate_limit_exceeded"]
    notify_event_types = db.Column(db.Text, nullable=True)  # JSON

    # Throttling - max emails po satu
    max_emails_per_hour = db.Column(db.Integer, default=10, nullable=False)

    # Digest mode - umesto pojedinačnih, šalje summary
    digest_mode = db.Column(db.Boolean, default=False, nullable=False)
    digest_interval_minutes = db.Column(db.Integer, default=60, nullable=False)

    # Status
    is_enabled = db.Column(db.Boolean, default=True, nullable=False)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Tracking
    last_notification_at = db.Column(db.DateTime, nullable=True)
    emails_sent_this_hour = db.Column(db.Integer, default=0, nullable=False)

    # Relationships
    admin = db.relationship('PlatformAdmin', backref='notification_settings')

    def to_dict(self):
        import json
        return {
            'id': self.id,
            'admin_id': self.admin_id,
            'notification_email': self.notification_email,
            'notify_critical': self.notify_critical,
            'notify_error': self.notify_error,
            'notify_warning': self.notify_warning,
            'notify_info': self.notify_info,
            'notify_event_types': json.loads(self.notify_event_types) if self.notify_event_types else [],
            'max_emails_per_hour': self.max_emails_per_hour,
            'digest_mode': self.digest_mode,
            'digest_interval_minutes': self.digest_interval_minutes,
            'is_enabled': self.is_enabled,
            'last_notification_at': self.last_notification_at.isoformat() if self.last_notification_at else None,
        }
```

#### 4.1.2 API Endpoints

**Fajl:** `app/api/admin/security.py` - dodaj endpoints

```python
from app.models.security_notification_settings import SecurityNotificationSettings

# ============== Notification Settings ==============

@bp.route('/notifications/settings', methods=['GET'])
@platform_admin_required
def get_notification_settings():
    """
    Dohvati notification settings za trenutnog admina.
    Ako nema personalnih, vraća globalna podešavanja.
    """
    admin = g.current_admin

    # Prvo probaj personalna podešavanja
    settings = SecurityNotificationSettings.query.filter_by(admin_id=admin.id).first()

    # Fallback na globalna
    if not settings:
        settings = SecurityNotificationSettings.query.filter_by(admin_id=None).first()

    if not settings:
        # Vrati default vrednosti
        return jsonify({
            'settings': None,
            'defaults': {
                'notification_email': admin.email,
                'notify_critical': True,
                'notify_error': True,
                'notify_warning': False,
                'notify_info': False,
                'max_emails_per_hour': 10,
                'digest_mode': False,
                'is_enabled': False,
            },
            'available_event_types': _get_available_event_types()
        }), 200

    return jsonify({
        'settings': settings.to_dict(),
        'available_event_types': _get_available_event_types()
    }), 200


@bp.route('/notifications/settings', methods=['PUT'])
@platform_admin_required
def update_notification_settings():
    """
    Ažuriraj notification settings.

    Body:
    {
        "notification_email": "security@example.com",
        "notify_critical": true,
        "notify_error": true,
        "notify_warning": false,
        "notify_info": false,
        "notify_event_types": ["admin_login_failed", "2fa_lockout"],
        "max_emails_per_hour": 10,
        "digest_mode": false,
        "is_enabled": true
    }
    """
    admin = g.current_admin
    data = request.get_json()

    # Validacija email-a
    email = data.get('notification_email', '').strip()
    if not email or '@' not in email:
        return jsonify({'error': 'Neispravan email'}), 400

    # Pronađi ili kreiraj settings
    settings = SecurityNotificationSettings.query.filter_by(admin_id=admin.id).first()
    if not settings:
        settings = SecurityNotificationSettings(admin_id=admin.id)
        db.session.add(settings)

    # Update polja
    settings.notification_email = email
    settings.notify_critical = data.get('notify_critical', True)
    settings.notify_error = data.get('notify_error', True)
    settings.notify_warning = data.get('notify_warning', False)
    settings.notify_info = data.get('notify_info', False)
    settings.max_emails_per_hour = min(data.get('max_emails_per_hour', 10), 50)  # Max 50
    settings.digest_mode = data.get('digest_mode', False)
    settings.digest_interval_minutes = data.get('digest_interval_minutes', 60)
    settings.is_enabled = data.get('is_enabled', True)

    # Event types kao JSON
    import json
    event_types = data.get('notify_event_types', [])
    if isinstance(event_types, list):
        settings.notify_event_types = json.dumps(event_types)

    db.session.commit()

    # Log
    SecurityEventLogger.log_event(
        SecurityEventType.ADMIN_ACTION,
        details={'action': 'notification_settings_updated'},
        user_id=admin.id,
        email=admin.email
    )

    return jsonify({
        'message': 'Podešavanja sačuvana',
        'settings': settings.to_dict()
    }), 200


@bp.route('/notifications/test', methods=['POST'])
@platform_admin_required
def test_notification():
    """
    Pošalji test email notifikaciju.
    """
    admin = g.current_admin
    settings = SecurityNotificationSettings.query.filter_by(admin_id=admin.id).first()

    if not settings or not settings.is_enabled:
        return jsonify({'error': 'Notifikacije nisu konfigurisane'}), 400

    # Pošalji test email
    from app.services.security_alert_service import security_alerts
    success = security_alerts.send_test_notification(settings.notification_email, admin.email)

    if success:
        return jsonify({'message': f'Test email poslat na {settings.notification_email}'}), 200
    else:
        return jsonify({'error': 'Greška pri slanju email-a'}), 500


def _get_available_event_types():
    """Lista svih event tipova koji mogu triggerovati notifikaciju."""
    return [
        {'value': 'admin_login_failed', 'label': 'Neuspešan admin login', 'severity': 'warning'},
        {'value': 'admin_login_success', 'label': 'Uspešan admin login', 'severity': 'info'},
        {'value': '2fa_failed', 'label': '2FA verifikacija neuspešna', 'severity': 'warning'},
        {'value': '2fa_lockout', 'label': '2FA lockout aktiviran', 'severity': 'error'},
        {'value': 'rate_limit_exceeded', 'label': 'Rate limit prekoračen', 'severity': 'warning'},
        {'value': 'brute_force_detected', 'label': 'Brute force napad detektovan', 'severity': 'critical'},
        {'value': 'suspicious_ip', 'label': 'Sumnjiva IP adresa', 'severity': 'warning'},
        {'value': 'password_changed', 'label': 'Lozinka promenjena', 'severity': 'info'},
        {'value': 'token_blacklisted', 'label': 'Token invalidiran', 'severity': 'info'},
        {'value': 'new_admin_created', 'label': 'Novi admin kreiran', 'severity': 'warning'},
        {'value': 'admin_role_changed', 'label': 'Admin uloga promenjena', 'severity': 'warning'},
    ]
```

#### 4.1.3 Security Alert Service

**Novi fajl:** `app/services/security_alert_service.py`

```python
"""
Security Alert Service.

Šalje email notifikacije za security events na osnovu konfiguracije.
"""
import json
from datetime import datetime, timedelta
from flask import current_app
from app.extensions import db
from app.models.security_notification_settings import SecurityNotificationSettings
from app.services.email_service import email_service


class SecurityAlertService:
    """
    Servis za slanje security alert notifikacija.

    Poštuje:
    - Throttling (max emails per hour)
    - Severity filtering
    - Event type filtering
    - Digest mode
    """

    SEVERITY_LEVELS = {
        'critical': 4,
        'error': 3,
        'warning': 2,
        'info': 1,
    }

    def check_and_notify(self, event_type: str, severity: str, details: dict) -> bool:
        """
        Proveri da li treba poslati notifikaciju i pošalji ako treba.

        Args:
            event_type: Tip eventa (npr. 'admin_login_failed')
            severity: Severity level ('critical', 'error', 'warning', 'info')
            details: Detalji eventa (dict)

        Returns:
            True ako je notifikacija poslata
        """
        # Dohvati sve aktivne notification settings
        settings_list = SecurityNotificationSettings.query.filter_by(
            is_enabled=True
        ).all()

        sent_count = 0
        for settings in settings_list:
            if self._should_notify(settings, event_type, severity):
                if self._can_send(settings):
                    if settings.digest_mode:
                        self._add_to_digest(settings, event_type, severity, details)
                    else:
                        self._send_immediate(settings, event_type, severity, details)
                        sent_count += 1

        return sent_count > 0

    def _should_notify(self, settings: SecurityNotificationSettings,
                       event_type: str, severity: str) -> bool:
        """Proveri da li ovaj event treba da triggeruje notifikaciju."""

        # Proveri severity
        if severity == 'critical' and not settings.notify_critical:
            return False
        if severity == 'error' and not settings.notify_error:
            return False
        if severity == 'warning' and not settings.notify_warning:
            return False
        if severity == 'info' and not settings.notify_info:
            return False

        # Proveri specifične event tipove (ako su definisani)
        if settings.notify_event_types:
            allowed_types = json.loads(settings.notify_event_types)
            if allowed_types and event_type not in allowed_types:
                return False

        return True

    def _can_send(self, settings: SecurityNotificationSettings) -> bool:
        """Proveri throttling - da li možemo poslati još email-ova."""
        now = datetime.utcnow()

        # Reset counter ako je prošao sat
        if settings.last_notification_at:
            if now - settings.last_notification_at > timedelta(hours=1):
                settings.emails_sent_this_hour = 0

        # Proveri limit
        if settings.emails_sent_this_hour >= settings.max_emails_per_hour:
            return False

        return True

    def _send_immediate(self, settings: SecurityNotificationSettings,
                        event_type: str, severity: str, details: dict) -> bool:
        """Pošalji email odmah."""

        subject = self._get_subject(event_type, severity)
        body = self._get_body(event_type, severity, details)

        success = email_service.send_email(
            to=settings.notification_email,
            subject=subject,
            html_body=body,
            text_body=self._get_text_body(event_type, severity, details)
        )

        if success:
            settings.emails_sent_this_hour += 1
            settings.last_notification_at = datetime.utcnow()
            db.session.commit()

        return success

    def _get_subject(self, event_type: str, severity: str) -> str:
        """Generiši email subject."""
        severity_emoji = {
            'critical': '🚨',
            'error': '❌',
            'warning': '⚠️',
            'info': 'ℹ️',
        }
        emoji = severity_emoji.get(severity, '📧')

        event_labels = {
            'admin_login_failed': 'Neuspešan admin login',
            '2fa_lockout': '2FA lockout aktiviran',
            'brute_force_detected': 'BRUTE FORCE NAPAD',
            'rate_limit_exceeded': 'Rate limit prekoračen',
            'suspicious_ip': 'Sumnjiva IP adresa',
        }
        label = event_labels.get(event_type, event_type)

        return f"{emoji} [ServisHub Security] {label}"

    def _get_body(self, event_type: str, severity: str, details: dict) -> str:
        """Generiši HTML email body."""
        return f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <div style="background: {'#dc3545' if severity == 'critical' else '#ffc107' if severity in ['error', 'warning'] else '#17a2b8'};
                        color: white; padding: 15px; border-radius: 5px; margin-bottom: 20px;">
                <h2 style="margin: 0;">Security Alert: {event_type}</h2>
                <p style="margin: 5px 0 0 0;">Severity: {severity.upper()}</p>
            </div>

            <h3>Detalji:</h3>
            <table style="border-collapse: collapse; width: 100%;">
                {''.join(f'<tr><td style="border: 1px solid #ddd; padding: 8px; font-weight: bold;">{k}</td><td style="border: 1px solid #ddd; padding: 8px;">{v}</td></tr>' for k, v in details.items())}
            </table>

            <p style="margin-top: 20px; color: #666; font-size: 12px;">
                Ovaj email je automatski generisan od strane ServisHub Security sistema.<br>
                Vreme: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
            </p>
        </body>
        </html>
        """

    def _get_text_body(self, event_type: str, severity: str, details: dict) -> str:
        """Plain text verzija email-a."""
        lines = [
            f"ServisHub Security Alert",
            f"========================",
            f"Event: {event_type}",
            f"Severity: {severity.upper()}",
            f"",
            f"Details:",
        ]
        for k, v in details.items():
            lines.append(f"  {k}: {v}")

        lines.append(f"")
        lines.append(f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")

        return "\n".join(lines)

    def send_test_notification(self, to_email: str, admin_email: str) -> bool:
        """Pošalji test notifikaciju."""
        return email_service.send_email(
            to=to_email,
            subject="🔔 [ServisHub] Test Security Notification",
            html_body=f"""
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <div style="background: #28a745; color: white; padding: 15px; border-radius: 5px;">
                    <h2 style="margin: 0;">Test Notification ✓</h2>
                </div>
                <p style="margin-top: 20px;">
                    Ovo je test notifikacija za security alerts.<br>
                    Ako vidite ovaj email, notifikacije su ispravno konfigurisane.
                </p>
                <p style="color: #666; font-size: 12px;">
                    Konfigurisano od: {admin_email}<br>
                    Vreme: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
                </p>
            </body>
            </html>
            """,
            text_body=f"Test Security Notification\n\nNotifikacije su ispravno konfigurisane.\nAdmin: {admin_email}"
        )


# Singleton
security_alerts = SecurityAlertService()
```

#### 4.1.4 Frontend Template

**Fajl:** `app/templates/admin/security/notifications.html` (novi tab)

```html
<!-- Tab content za Notifications -->
<div x-show="activeTab === 'notifications'" x-data="notificationSettings()">

    <div class="admin-card bg-white rounded-lg shadow p-6">
        <div class="flex items-center justify-between mb-6">
            <div>
                <h3 class="text-lg font-medium text-gray-900">Email Notifikacije</h3>
                <p class="text-sm text-gray-500">Primajte email obaveštenja o sigurnosnim događajima</p>
            </div>
            <div class="flex items-center">
                <span class="mr-3 text-sm text-gray-600">Notifikacije</span>
                <button @click="toggleEnabled()"
                        :class="settings.is_enabled ? 'bg-green-500' : 'bg-gray-300'"
                        class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full transition-colors">
                    <span :class="settings.is_enabled ? 'translate-x-5' : 'translate-x-0'"
                          class="inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition mt-0.5 ml-0.5"></span>
                </button>
            </div>
        </div>

        <div x-show="settings.is_enabled" class="space-y-6">
            <!-- Email Address -->
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Email za notifikacije</label>
                <input type="email" x-model="settings.notification_email"
                       class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-red-500 focus:border-red-500"
                       placeholder="security@example.com">
                <p class="text-xs text-gray-500 mt-1">Može biti različit od vašeg admin email-a</p>
            </div>

            <!-- Severity Levels -->
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-3">Severity nivoi za obaveštenja</label>
                <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <label class="flex items-center p-3 border rounded-lg cursor-pointer"
                           :class="settings.notify_critical ? 'border-red-500 bg-red-50' : 'border-gray-200'">
                        <input type="checkbox" x-model="settings.notify_critical" class="sr-only">
                        <span class="w-3 h-3 rounded-full bg-red-500 mr-2"></span>
                        <span class="text-sm">Critical</span>
                    </label>
                    <label class="flex items-center p-3 border rounded-lg cursor-pointer"
                           :class="settings.notify_error ? 'border-orange-500 bg-orange-50' : 'border-gray-200'">
                        <input type="checkbox" x-model="settings.notify_error" class="sr-only">
                        <span class="w-3 h-3 rounded-full bg-orange-500 mr-2"></span>
                        <span class="text-sm">Error</span>
                    </label>
                    <label class="flex items-center p-3 border rounded-lg cursor-pointer"
                           :class="settings.notify_warning ? 'border-yellow-500 bg-yellow-50' : 'border-gray-200'">
                        <input type="checkbox" x-model="settings.notify_warning" class="sr-only">
                        <span class="w-3 h-3 rounded-full bg-yellow-500 mr-2"></span>
                        <span class="text-sm">Warning</span>
                    </label>
                    <label class="flex items-center p-3 border rounded-lg cursor-pointer"
                           :class="settings.notify_info ? 'border-blue-500 bg-blue-50' : 'border-gray-200'">
                        <input type="checkbox" x-model="settings.notify_info" class="sr-only">
                        <span class="w-3 h-3 rounded-full bg-blue-500 mr-2"></span>
                        <span class="text-sm">Info</span>
                    </label>
                </div>
            </div>

            <!-- Event Types -->
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-3">Specifični događaji (opciono)</label>
                <p class="text-xs text-gray-500 mb-2">Ostavite prazno da primate sve događaje izabranog severity-ja</p>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
                    <template x-for="eventType in availableEventTypes" :key="eventType.value">
                        <label class="flex items-center p-2 border rounded cursor-pointer hover:bg-gray-50">
                            <input type="checkbox"
                                   :value="eventType.value"
                                   :checked="settings.notify_event_types.includes(eventType.value)"
                                   @change="toggleEventType(eventType.value)"
                                   class="mr-2">
                            <span class="w-2 h-2 rounded-full mr-2"
                                  :class="{
                                      'bg-red-500': eventType.severity === 'critical',
                                      'bg-orange-500': eventType.severity === 'error',
                                      'bg-yellow-500': eventType.severity === 'warning',
                                      'bg-blue-500': eventType.severity === 'info'
                                  }"></span>
                            <span class="text-sm" x-text="eventType.label"></span>
                        </label>
                    </template>
                </div>
            </div>

            <!-- Throttling -->
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Max email-ova po satu</label>
                <input type="number" x-model="settings.max_emails_per_hour" min="1" max="50"
                       class="w-32 px-3 py-2 border border-gray-300 rounded-md">
                <p class="text-xs text-gray-500 mt-1">Sprečava flooding inbox-a (max 50)</p>
            </div>

            <!-- Actions -->
            <div class="flex items-center justify-between pt-4 border-t">
                <button @click="sendTest()" :disabled="saving"
                        class="px-4 py-2 text-sm text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50">
                    📧 Pošalji test email
                </button>
                <button @click="saveSettings()" :disabled="saving"
                        class="px-4 py-2 text-sm text-white bg-red-600 rounded-md hover:bg-red-700 disabled:opacity-50">
                    <span x-show="!saving">Sačuvaj podešavanja</span>
                    <span x-show="saving">Čuvanje...</span>
                </button>
            </div>
        </div>

        <!-- Disabled State -->
        <div x-show="!settings.is_enabled" class="text-center py-8 text-gray-500">
            <svg class="w-12 h-12 mx-auto mb-3 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"/>
            </svg>
            <p>Email notifikacije su isključene</p>
            <p class="text-sm">Uključite ih da primate obaveštenja o sigurnosnim događajima</p>
        </div>
    </div>
</div>

<script>
function notificationSettings() {
    return {
        settings: {
            notification_email: '',
            notify_critical: true,
            notify_error: true,
            notify_warning: false,
            notify_info: false,
            notify_event_types: [],
            max_emails_per_hour: 10,
            is_enabled: false,
        },
        availableEventTypes: [],
        saving: false,

        async init() {
            await this.loadSettings();
        },

        async loadSettings() {
            const token = localStorage.getItem('admin_access_token');
            const r = await fetch('/api/admin/security/notifications/settings', {
                headers: { 'Authorization': 'Bearer ' + token }
            });
            if (r.ok) {
                const data = await r.json();
                if (data.settings) {
                    this.settings = data.settings;
                } else if (data.defaults) {
                    this.settings = data.defaults;
                }
                this.availableEventTypes = data.available_event_types || [];
            }
        },

        toggleEnabled() {
            this.settings.is_enabled = !this.settings.is_enabled;
        },

        toggleEventType(value) {
            const idx = this.settings.notify_event_types.indexOf(value);
            if (idx > -1) {
                this.settings.notify_event_types.splice(idx, 1);
            } else {
                this.settings.notify_event_types.push(value);
            }
        },

        async saveSettings() {
            this.saving = true;
            const token = localStorage.getItem('admin_access_token');

            const r = await fetch('/api/admin/security/notifications/settings', {
                method: 'PUT',
                headers: {
                    'Authorization': 'Bearer ' + token,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(this.settings)
            });

            if (r.ok) {
                alert('Podešavanja sačuvana!');
            } else {
                const err = await r.json();
                alert(err.error || 'Greška pri čuvanju');
            }
            this.saving = false;
        },

        async sendTest() {
            const token = localStorage.getItem('admin_access_token');
            const r = await fetch('/api/admin/security/notifications/test', {
                method: 'POST',
                headers: { 'Authorization': 'Bearer ' + token }
            });
            const data = await r.json();
            alert(data.message || data.error);
        }
    }
}
</script>
```

#### 4.1.5 Integracija sa SecurityEventLogger

**Modifikuj:** `app/services/security_service.py`

```python
# Na kraju log_event metode, dodaj:
from .security_alert_service import security_alerts

class SecurityEventLogger:
    @classmethod
    def log_event(cls, event_type, details=None, ...):
        # ... existing logging code ...

        # NOVO: Proveri i pošalji notifikaciju
        try:
            security_alerts.check_and_notify(
                event_type=str(event_type.value) if hasattr(event_type, 'value') else str(event_type),
                severity=level,
                details=details or {}
            )
        except Exception as e:
            # Ne blokiraj ako notifikacija ne uspe
            logging.error(f"Failed to send security notification: {e}")
```

#### 4.1.6 Migracija

```bash
flask db migrate -m "Add SecurityNotificationSettings table"
flask db upgrade
```

---

### 4.2 Real-Time Security Alerts (automatske)

### 4.2 Mandatory 2FA za Admine

Dodaj enforcement u login flow:
- Ako admin nema 2FA enabled, redirect na setup
- Grace period 24h za nove admine

### 4.3 Geo-IP Anomaly Detection

- Integriši MaxMind GeoIP2
- Detektuj impossible travel
- Zahtevaj 2FA re-verify na sumnjivoj lokaciji

### 4.4 Concurrent Session Limits

- Track sesije u Redis
- Max 3 uređaja po korisniku
- "Logout all devices" funkcionalnost

---

## Potrebne Zavisnosti

```txt
# requirements.txt - dodati

# Redis (za token blacklist i rate limiting)
redis>=4.5.0

# File type detection
python-magic>=0.4.27

# Geo-IP (Phase 4)
geoip2>=4.7.0
```

**Heroku Addons:**
- Heroku Redis (već postoji ako je REDIS_URL konfigurisan)

---

## Verifikacija i Testiranje

### Phase 1 Checklist
- [ ] Token blacklist: Logout invalidira access token
- [ ] Token blacklist: Logout invalidira refresh token
- [ ] Token blacklist: Password change invalidira sve tokene
- [ ] Redis rate limiter: Radi na 2 dynos
- [ ] Redis rate limiter: Perzistentno preko restarta
- [ ] 2FA brute force: Lockout posle 5 pokušaja
- [ ] 2FA brute force: Unlock posle 30 minuta

### Phase 2 Checklist
- [ ] TOTP: Kod stariji od 30s rejected
- [ ] JWT secret: App ne starta sa default secretom u prod
- [ ] Password change: Sve sesije invalidirane

### Phase 3 Checklist
- [ ] Refresh token: Expire posle 7 dana
- [ ] CORS: Reject unknown origins
- [ ] File upload: Executable blocked
- [ ] File upload: MIME mismatch blocked

---

## Rollback Procedure

```bash
# 1. Disable token blacklist (tokens će raditi do expiry)
heroku config:set TOKEN_BLACKLIST_ENABLED=false

# 2. Fallback na in-memory rate limiter
heroku config:unset USE_REDIS_RATE_LIMITER

# 3. Revert TOTP window (zahteva deploy)
# Izmeni valid_window=0 nazad na valid_window=1

# 4. Emergency: Regeneriši JWT secret (invalidira SVE tokene)
heroku config:set JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
```

---

## Timeline Summary

| Phase | Nedelja | Focus | Effort |
|-------|---------|-------|--------|
| 1 | 1-2 | Token blacklist, Redis rate limit, 2FA protection | 5-7 dana |
| 2 | 2-3 | TOTP window, JWT secret, password invalidation | 2-3 dana |
| 3 | 3-5 | Refresh token, CORS, CSP, file validation | 4-5 dana |
| 4 | 5-8 | Alerts, mandatory 2FA, geo-IP, session limits | 7-10 dana |

**Ukupno:** 4-8 nedelja sa jednim developerom

---

## Appendix: Database Migrations

```bash
# Phase 1.3: 2FA lockout fields
flask db migrate -m "Add 2FA lockout fields to PlatformAdmin"
flask db upgrade

# Verify:
flask shell
>>> from app.models import PlatformAdmin
>>> admin = PlatformAdmin.query.first()
>>> print(admin.totp_failed_attempts)  # Should be 0
```