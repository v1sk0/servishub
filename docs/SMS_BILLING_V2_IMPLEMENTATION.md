# SMS Billing V2 - Kompletna Dokumentacija

**Projekat:** ServisHub - SMS Robustnost (D7 Networks)
**Datum implementacije:** 2026-02-01
**Status:** IMPLEMENTIRANO

---

## Pregled Projekta

SMS Billing V2 je poboljšanje SMS sistema za ServisHub platformu koje uključuje:
- Atomic credit charging (sprečavanje race condition-a)
- Telefon input sa country selector-om
- SMS opt-out po tiketu
- DLR Webhook za praćenje isporuke
- Redis-based rate limiting
- Finansijska analitika za admin panel

---

## Arhitektura

### SMS Provajder
- **D7 Networks** (https://d7networks.com)
- API endpoint: `https://api.d7networks.com/messages/v1/send`
- Cena za Srbiju: **$0.026** po SMS-u

### Environment Varijable
```
D7_API_TOKEN=<api_token>
D7_SENDER_ID=ServisHub
D7_WEBHOOK_SECRET=<webhook_secret>
REDIS_URL=<redis_url>
```

---

## Implementirane Faze

### FAZA 1: Atomic Credit Charging

**Problem:** Paralelni SMS-ovi mogu duplirati naplatu (race condition).

**Rešenje:** `SELECT FOR UPDATE` row-level locking u PostgreSQL.

**Fajl:** `app/services/sms_billing_service.py`

```python
from sqlalchemy import select

def charge_for_sms(tenant_id, sms_type, reference_id, description):
    # Atomic lock na CreditBalance red
    stmt = select(CreditBalance).where(
        CreditBalance.owner_type == OwnerType.TENANT,
        CreditBalance.tenant_id == tenant_id
    ).with_for_update(nowait=False)  # Čekaj ako je zaključano

    result = db.session.execute(stmt)
    credit_balance = result.scalar_one_or_none()

    # Proveri balance i naplati atomski
    if credit_balance.balance >= sms_cost:
        credit_balance.balance -= sms_cost
        # Kreiraj transakciju...
```

**Ključne tačke:**
- `with_for_update(nowait=False)` - čeka dok se lock oslobodi
- Lock se oslobađa na `db.session.commit()`
- Sprečava duplu naplatu kod paralelnih zahteva

---

### FAZA 2: Telefon Input sa Country Selector

**Problem:** Telefon se unosio kao plain text bez validacije.

**Rešenje:** Alpine.js dropdown sa zastavicama i automatskim formatiranjem.

**Fajl:** `app/templates/tenant/tickets/new.html`

**Ex-YU zemlje (prioritet):**
| Zemlja | Kod | Flag |
|--------|-----|------|
| Srbija | +381 | 🇷🇸 |
| Hrvatska | +385 | 🇭🇷 |
| BiH | +387 | 🇧🇦 |
| Crna Gora | +382 | 🇲🇪 |
| Slovenija | +386 | 🇸🇮 |
| Kosovo | +383 | 🇽🇰 |
| S. Makedonija | +389 | 🇲🇰 |

**Format za D7 API:**
```javascript
// Input: 064 909 0060 (sa leading 0)
// Output: 381649090060 (bez +, bez leading 0)

get formattedPhoneForApi() {
    const digits = this.phoneNumber.replace(/\D/g, '');
    const cleanDigits = digits.startsWith('0') ? digits.slice(1) : digits;
    return this.selectedCountry.dial + cleanDigits;
}
```

---

### FAZA 3: SMS Opt-Out + GSM-7 Validacija

**Problem:** Nema načina da se zabeleži da klijent ne želi SMS.

**Rešenje:**
- Novo polje `sms_opt_out` na ServiceTicket modelu
- `sms_notification_completed` flag za sprečavanje duplog slanja
- GSM-7 transliteracija i validacija dužine poruke
- Print klauzula sa SMS statusom

#### Consent Politika: AUTO OPT-IN

| Aspekt | Vrednost |
|--------|----------|
| Default | `sms_opt_out = False` (prima SMS) |
| Checkbox | "Klijent NE želi SMS" (unchecked = prima) |
| Tok | Radnik informiše klijenta → ako odbije, čekira |
| Print | "SMS obavestenja: DA" (zeleno) ili "NE" (crveno) |

**Model:** `app/models/ticket.py`
```python
class ServiceTicket(db.Model):
    # SMS polja
    sms_opt_out = db.Column(db.Boolean, default=False, nullable=False)
    sms_notification_completed = db.Column(db.Boolean, default=False)
```

**Print Klauzula:** `app/templates/tenant/tickets/print.html`
```html
<div class="sms-clause">
  SMS obavestenja: <strong id="sms-status-1">DA</strong>
</div>
```
- Zeleno "DA" ako prima SMS (`sms_opt_out = false`)
- Crveno "NE" ako je odbio (`sms_opt_out = true`)

**Transliteracija:** `app/services/sms_service.py`
```python
TRANSLITERATION_MAP = {
    'ć': 'c', 'Ć': 'C',
    'č': 'c', 'Č': 'C',
    'š': 's', 'Š': 'S',
    'đ': 'dj', 'Đ': 'Dj',
    'ž': 'z', 'Ž': 'Z',
    # + ćirilica...
}

MAX_SMS_LENGTH = 160  # Striktni limit
```

**Validacija pre slanja:**
1. Proveri `sms_opt_out` flag
2. Proveri `sms_notification_completed` flag
3. Transliteriraj poruku (ćčšđž → ccsdz)
4. Proveri dužinu (max 160 karaktera)
5. Ako prekorači - logiraj grešku, ne šalji

---

### FAZA 4: DLR Webhook

**Problem:** `status='sent'` znači samo "poslato D7-u", ne "delivered".

**Rešenje:** Webhook endpoint za D7 Delivery Reports.

**Endpoint:** `POST /webhooks/d7/dlr`

**Fajl:** `app/api/webhooks/d7.py`

**Sigurnosne mere:**
1. **HMAC-SHA256 Signature Verification**
   ```python
   def _verify_signature(payload: bytes, signature: str) -> bool:
       secret = os.environ.get('D7_WEBHOOK_SECRET', '')
       expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
       return hmac.compare_digest(expected, signature)
   ```

2. **Replay Protection** (max 5 min stara poruka)
   ```python
   if datetime.utcnow() - msg_time > timedelta(minutes=5):
       return jsonify({'error': 'Replay detected'}), 400
   ```

3. **Idempotency** (SmsDlrLog model)
   ```python
   existing_dlr = SmsDlrLog.query.filter_by(message_id=message_id).first()
   if existing_dlr:
       return jsonify({'status': 'already_processed'}), 200
   ```

**Auto-Refund za failed/expired:**
```python
if status in ('failed', 'expired'):
    _process_refund(sms_log, status, error_code)
```

**Nova polja u TenantSmsUsage:**
```python
delivery_status = db.Column(db.String(30), default='pending')
delivery_status_at = db.Column(db.DateTime(timezone=True))
delivery_error_code = db.Column(db.String(20))
```

**SmsDlrLog model:**
```python
class SmsDlrLog(db.Model):
    __tablename__ = 'sms_dlr_log'

    id = db.Column(db.BigInteger, primary_key=True)
    message_id = db.Column(db.String(100), unique=True, index=True)
    status = db.Column(db.String(30), nullable=False)
    raw_payload = db.Column(db.Text)
    error_code = db.Column(db.String(20))
    received_at = db.Column(db.DateTime, default=datetime.utcnow)
```

---

### FAZA 5: Rate Limiting (Redis)

**Problem:** Samo mesečni limit, nema burst protection.

**Rešenje:** Redis-based sliding window rate limiting.

**Fajl:** `app/services/sms_rate_limiter.py`

**Limiti:**
| Tip | Limit | TTL |
|-----|-------|-----|
| Tenant per minute | 10 SMS | 60s |
| Tenant per hour | 100 SMS | 3600s |
| Recipient per day | 3 SMS | 86400s |

**Implementacija:**
```python
class SmsRateLimiter:
    TENANT_PER_MINUTE = 10
    TENANT_PER_HOUR = 100
    RECIPIENT_PER_DAY = 3

    def can_send(self, tenant_id: int, phone: str) -> Tuple[bool, str]:
        # Proveri sve limite
        minute_key = f"sms:tenant:{tenant_id}:minute:{now.strftime('%Y%m%d%H%M')}"
        minute_count = int(self.redis.get(minute_key) or 0)
        if minute_count >= self.TENANT_PER_MINUTE:
            return False, f"rate_limit:tenant_minute:{self.TENANT_PER_MINUTE}"
        # ... ostali limiti
        return True, "ok"

    def record_send(self, tenant_id: int, phone: str):
        # Inkrementiraj brojače sa TTL
        pipe = self.redis.pipeline()
        pipe.incr(minute_key)
        pipe.expire(minute_key, 60)
        # ...
        pipe.execute()
```

**Karakteristike:**
- Fail-open design (ako Redis nije dostupan, SMS se šalje)
- Privacy: telefon se hashira (SHA256)
- Singleton pattern za reuse konekcije

---

### FAZA 6: SMS Finansijska Analitika

**Problem:** Admin nema uvid u zaradu od SMS-a.

**Rešenje:** Novi API endpoint i UI u admin panelu.

**Fajl:** `app/api/admin/sms.py`

**Endpoint:** `GET /api/admin/sms/stats/financial`

**Response:**
```json
{
  "period_days": 30,
  "pricing": {
    "sms_price_credits": 0.20,
    "d7_cost_usd": 0.026,
    "d7_cost_eur": 0.024,
    "usd_to_eur": 0.92
  },
  "summary": {
    "total_sent": 150,
    "total_revenue_credits": 30.00,
    "total_refunded_credits": 2.00,
    "net_revenue_credits": 28.00,
    "d7_cost_eur": 3.58,
    "profit_eur": 24.42,
    "margin_percent": 87.2
  },
  "monthly": [...],
  "top_tenants": [...]
}
```

**Nova polja u PlatformSettings:**
```python
sms_d7_cost_usd = db.Column(db.Numeric(10, 4), default=Decimal('0.026'))
sms_usd_to_eur = db.Column(db.Numeric(10, 4), default=Decimal('0.92'))
```

**UI:** `app/templates/admin/sms/index.html`
- Finansijska kartica na vrhu (prihod, trošak, profit, marža)
- Nov tab "Finansije" sa mesečnim pregledom
- Top 10 servisa po zaradi

---

## Kreiran/Izmenjen Fajlovi

### Novi fajlovi:
| Fajl | Opis |
|------|------|
| `app/api/webhooks/__init__.py` | Webhooks blueprint |
| `app/api/webhooks/d7.py` | DLR webhook endpoint |
| `app/services/sms_rate_limiter.py` | Redis rate limiter |
| `migrations/versions/v324_sms_opt_out.py` | Migracija za sms_opt_out |
| `migrations/versions/v325_sms_delivery_status.py` | DLR polja + SmsDlrLog |
| `migrations/versions/v326_sms_d7_cost_fields.py` | D7 cost polja |

### Izmenjeni fajlovi:
| Fajl | Izmene |
|------|--------|
| `app/__init__.py` | Registrovan webhooks blueprint |
| `app/models/__init__.py` | Export SmsDlrLog |
| `app/models/ticket.py` | sms_opt_out + sms_notification_completed |
| `app/models/sms_management.py` | delivery_status polja + SmsDlrLog model |
| `app/models/platform_settings.py` | sms_d7_cost_usd + sms_usd_to_eur |
| `app/services/sms_service.py` | Transliteracija, opt-out, rate limiter |
| `app/services/sms_billing_service.py` | Atomic charging (FOR UPDATE) |
| `app/api/admin/sms.py` | Financial stats endpoint |
| `app/templates/tenant/tickets/new.html` | Country selector + opt-out checkbox |
| `app/templates/tenant/tickets/list.html` | SMS status kolona |
| `app/templates/admin/sms/index.html` | Finansije tab + kartica |

---

## Migracije

Pokreni migracije redom:
```bash
flask db upgrade
```

Migracije:
1. `v324_sms_opt_out` - sms_opt_out polje na service_ticket
2. `v325_sms_delivery_status` - delivery_status polja + sms_dlr_log tabela
3. `v326_sms_d7_cost_fields` - sms_d7_cost_usd + sms_usd_to_eur

---

## D7 Networks Konfiguracija

### Webhook Setup
1. Idi na D7 Dashboard
2. Settings > Webhooks
3. Dodaj novi webhook:
   - **URL:** `https://app.servishub.rs/webhooks/d7/dlr`
   - **Method:** POST
   - **Events:** Delivery Reports
4. Kopiraj Secret i dodaj u Heroku:
   ```bash
   heroku config:set D7_WEBHOOK_SECRET=<secret>
   ```

### ⚠️ PRODUKCIONA VERIFIKACIJA

**Pre puštanja u produkciju, OBAVEZNO proveriti:**

| Stavka | Komanda za proveru | Očekivani rezultat |
|--------|-------------------|-------------------|
| Webhook URL | Proveri D7 Dashboard | `https://app.servishub.rs/webhooks/d7/dlr` |
| D7_WEBHOOK_SECRET | `heroku config:get D7_WEBHOOK_SECRET` | Secret mora biti podešen |
| Webhook Events | D7 Dashboard > Webhooks | Delivery Reports uključen |
| Test endpoint | `curl https://app.servishub.rs/webhooks/d7/test` | `{"status": "ok"}` |

**Ako webhook nije konfigurisan:**
- SMS-ovi će se slati normalno
- `delivery_status` će ostati `pending` (neće se ažurirati)
- Auto-refund neće raditi (jer nema DLR notifikacija)

### Test Webhook
```bash
curl -X GET https://app.servishub.rs/webhooks/d7/test
```

---

## SMS Flow

### Slanje SMS-a (Tiket spreman)

```
1. Tiket prelazi u status READY
   ↓
2. Proveri sms_opt_out flag
   → Ako je true, skip SMS
   ↓
3. Proveri sms_notification_completed flag
   → Ako je true, skip (već poslat)
   ↓
4. Proveri rate limit (Redis)
   → Ako je prekoračen, logiraj i skip
   ↓
5. Proveri kredit balance
   → Ako nema dovoljno, skip
   ↓
6. Validiraj poruku (GSM-7, max 160)
   → Ako je preduga, logiraj grešku i skip
   ↓
7. Naplati kredit (ATOMIC - FOR UPDATE)
   ↓
8. Pošalji SMS preko D7 API
   ↓
9. Ako uspe:
   - Logiraj u TenantSmsUsage
   - Postavi sms_notification_completed = true
   - Record rate limit
   ↓
10. Ako ne uspe:
    - Refund kredit
    - Logiraj grešku
```

### DLR Webhook Flow

```
1. D7 šalje POST /webhooks/d7/dlr
   ↓
2. Verifikuj HMAC-SHA256 signature
   → Ako je nevažeći, 401 Unauthorized
   ↓
3. Proveri replay (max 5 min)
   → Ako je stara poruka, 400 Bad Request
   ↓
4. Proveri idempotency (SmsDlrLog)
   → Ako je već obrađen, 200 OK
   ↓
5. Nađi TenantSmsUsage po message_id
   ↓
6. Ažuriraj delivery_status
   ↓
7. Ako je failed/expired:
   - Automatski refund kredita
   ↓
8. Logiraj u SmsDlrLog
   ↓
9. Vrati 200 OK
```

---

## Testiranje

### Test Rate Limiter
```python
from app.services.sms_rate_limiter import rate_limiter

# Proveri da li može da pošalje
can_send, reason = rate_limiter.can_send(tenant_id=1, phone="+381649090060")
print(f"Can send: {can_send}, Reason: {reason}")

# Simuliraj slanje
rate_limiter.record_send(tenant_id=1, phone="+381649090060")
```

### Test DLR Webhook (lokalno)
```bash
curl -X POST http://localhost:5000/webhooks/d7/dlr \
  -H "Content-Type: application/json" \
  -d '{"message_id": "test123", "status": "delivered", "timestamp": "2026-02-01T12:00:00Z"}'
```

### Test Atomic Charging
```python
from app.services.sms_billing_service import sms_billing_service

# Proveri da li može da pošalje
can_send, reason = sms_billing_service.can_send_sms(tenant_id=1)
print(f"Can send: {can_send}, Reason: {reason}")

# Naplati
success, tx_id, msg = sms_billing_service.charge_for_sms(
    tenant_id=1,
    sms_type='TICKET_READY',
    reference_id=123,
    description='Test SMS'
)
print(f"Success: {success}, TX ID: {tx_id}, Message: {msg}")
```

---

## Troubleshooting

### SMS se ne šalje

1. **Proveri D7_API_TOKEN**
   ```bash
   heroku config:get D7_API_TOKEN
   ```

2. **Proveri kredit balance**
   ```sql
   SELECT balance FROM credit_balance
   WHERE tenant_id = <tenant_id>;
   ```

3. **Proveri sms_opt_out**
   ```sql
   SELECT sms_opt_out, sms_notification_completed
   FROM service_ticket WHERE id = <ticket_id>;
   ```

4. **Proveri rate limit**
   ```bash
   heroku redis:cli
   > KEYS sms:tenant:<tenant_id>:*
   ```

### DLR Webhook ne radi

1. **Proveri D7_WEBHOOK_SECRET**
   ```bash
   heroku config:get D7_WEBHOOK_SECRET
   ```

2. **Proveri logove**
   ```bash
   heroku logs --tail | grep DLR
   ```

3. **Test endpoint**
   ```bash
   curl https://app.servishub.rs/webhooks/d7/test
   ```

### Finansijska analitika prikazuje 0

1. **Proveri CreditTransaction tabelu**
   ```sql
   SELECT * FROM credit_transaction
   WHERE transaction_type = 'SMS_NOTIFICATION'
   ORDER BY created_at DESC LIMIT 10;
   ```

2. **Proveri TenantSmsUsage**
   ```sql
   SELECT COUNT(*), status FROM tenant_sms_usage
   WHERE created_at > NOW() - INTERVAL '30 days'
   GROUP BY status;
   ```

---

## Buduća Unapređenja

1. **Multi-segment SMS** - Podrška za poruke duže od 160 karaktera
2. **Template sistem** - Predefinisane poruke sa placeholder-ima
3. **Scheduled SMS** - Zakazivanje slanja
4. **SMS Campaign** - Bulk slanje za marketing
5. **Two-way SMS** - Primanje odgovora od korisnika

---

## Kontakt

Za pitanja o implementaciji, kontaktiraj razvojni tim ili pogledaj:
- Plan fajl: `C:\Users\darko\.claude\plans\iterative-leaping-sky.md`
- Glavni CLAUDE.md: `c:\dolcevita\CLAUDE.md`

---

## ✅ Produkciona Checklist

Pre puštanja u produkciju, obavezno proveriti:

### 1. Environment Varijable
```bash
heroku config:get D7_API_TOKEN      # Mora biti podešen
heroku config:get D7_SENDER_ID      # "ServisHub" ili custom
heroku config:get D7_WEBHOOK_SECRET # Za DLR verifikaciju
heroku config:get REDIS_URL         # Za rate limiting
```

### 2. D7 Dashboard
- [ ] Webhook URL: `https://app.servishub.rs/webhooks/d7/dlr`
- [ ] Events: Delivery Reports uključen
- [ ] Secret kopiran i postavljen u Heroku

### 3. Baza podataka
```bash
heroku run flask db upgrade         # Sve migracije primenjene
```

### 4. Test endpoints
```bash
curl https://app.servishub.rs/webhooks/d7/test  # {"status": "ok"}
```

### 5. Admin panel
- [ ] SMS Pricing vidljiv (sms_d7_cost_usd, sms_usd_to_eur)
- [ ] Finansije tab prikazuje statistiku
- [ ] Monthly breakdown radi

**Status na dan 2026-02-01:** Sav kod implementiran. Webhook konfiguracija u D7 Dashboard zahteva manuelnu verifikaciju.
