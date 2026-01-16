# ServisHub - Billing System Analysis

> Kompletna tehnička dokumentacija billing sistema

---

## 1. Arhitektura Modela

```
┌─────────────────────────────────────────────────────────────────────┐
│                         PLATFORM SETTINGS                           │
│  (singleton - globalna konfiguracija platforme)                     │
│  - base_price: 3600 RSD                                             │
│  - location_price: 1800 RSD                                         │
│  - trial_days: 90                                                   │
│  - demo_days: 7                                                     │
│  - grace_period_days: 15                                            │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                            TENANT                                   │
│  Billing polja:                    Trust Score polja:               │
│  - current_debt: Decimal           - trust_score: 0-100             │
│  - days_overdue: int               - trust_activated_at: DateTime   │
│  - last_payment_at: DateTime       - trust_activation_count: int    │
│  - blocked_at: DateTime            - last_trust_activation_period   │
│  - block_reason: str               - consecutive_on_time_payments   │
│                                                                      │
│  Custom cene:                      Status:                          │
│  - custom_base_price               - DEMO → TRIAL → ACTIVE          │
│  - custom_location_price           - EXPIRED → SUSPENDED            │
│  - custom_price_reason                                               │
└─────────────────────────────────────────────────────────────────────┘
                    │                               │
                    ▼                               ▼
┌─────────────────────────────┐     ┌─────────────────────────────────┐
│   SUBSCRIPTION_PAYMENT      │     │       TENANT_MESSAGE            │
│  - invoice_number: SH-YYYY- │     │  - message_type: SYSTEM/ADMIN   │
│  - period_start/end         │     │  - category: BILLING/SYSTEM...  │
│  - items_json: []           │     │  - priority: LOW/NORMAL/HIGH    │
│  - subtotal, total_amount   │     │  - is_read, read_at             │
│  - status: PENDING/PAID     │     │  - related_payment_id           │
│  - due_date                 │     │  - action_url, action_label     │
│  - payment_proof_url        │     └─────────────────────────────────┘
│  - verified_by_id           │
└─────────────────────────────┘
```

---

## 2. Životni Ciklus Servisa (Tenant)

```
REGISTRACIJA
     │
     ▼
┌─────────┐     KYC + Admin aktivira    ┌─────────┐
│  DEMO   │ ─────────────────────────▶  │  TRIAL  │
│ 7 dana  │                             │ 90 dana │
└────┬────┘                             └────┬────┘
     │                                       │
     │ Demo istekao                          │ Plaćanje
     │ (bez KYC)                             ▼
     ▼                                  ┌─────────┐
┌─────────┐                             │ ACTIVE  │◀─────────┐
│SUSPENDED│                             └────┬────┘          │
└─────────┘                                  │               │
                                             │ Pretplata    │
                                             │ istekla      │
                                             ▼               │
                                        ┌─────────┐          │
                                        │ EXPIRED │          │
                                        │ 15 dana │          │
                                        │ grace   │          │
                                        └────┬────┘          │
                                             │               │
                                             │ 15 dana       │ Plaćanje
                                             │ bez uplate    │
                                             ▼               │
                                        ┌─────────┐          │
                                        │SUSPENDED│──────────┘
                                        │(blokira)│
                                        └────┬────┘
                                             │
                                             │ "Na reč"
                                             ▼
                                        ┌─────────┐
                                        │  TRUST  │ 48h da plati
                                        │ ACTIVE  │─────────▶ SUSPENDED
                                        └─────────┘  (ako ne plati)
```

### Opis Statusa

| Status | Trajanje | Pristup | Opis |
|--------|----------|---------|------|
| **DEMO** | 7 dana | Pun | Automatski pri registraciji |
| **TRIAL** | 90 dana | Pun | Admin aktivira nakon KYC |
| **ACTIVE** | Do isteka | Pun | Aktivna pretplata |
| **EXPIRED** | 15 dana | Pun + upozorenja | Grace period |
| **SUSPENDED** | Neograničeno | Ograničen | Blokiran |

---

## 3. Kalkulacija Mesečne Cene

```python
def calculate_monthly_price(tenant):
    settings = PlatformSettings.get_settings()

    # Koristi custom cene ako postoje
    base = tenant.custom_base_price or settings.base_price  # 3600 RSD
    location = tenant.custom_location_price or settings.location_price  # 1800 RSD

    # Broj aktivnih lokacija
    locations_count = ServiceLocation.query.filter_by(
        tenant_id=tenant.id, is_active=True
    ).count()

    # Kalkulacija: bazni + (dodatne lokacije * cena)
    additional = max(0, locations_count - 1)
    total = base + (additional * location)

    return {
        'base_price': float(base),
        'location_price': float(location),
        'locations_count': locations_count,
        'additional_locations': additional,
        'monthly_total': float(total),
        'currency': settings.currency
    }
```

### Primeri Kalkulacije

| Lokacije | Kalkulacija | Ukupno |
|----------|-------------|--------|
| 1 | 3600 | 3.600 RSD |
| 2 | 3600 + 1800 | 5.400 RSD |
| 3 | 3600 + (2 × 1800) | 7.200 RSD |
| 5 | 3600 + (4 × 1800) | 10.800 RSD |
| 10 | 3600 + (9 × 1800) | 19.800 RSD |

---

## 4. Faktura (SubscriptionPayment) Workflow

### 4.1 Generisanje Fakture

```json
{
  "invoice_number": "SH-2026-000001",
  "tenant_id": 42,
  "period_start": "2026-02-01",
  "period_end": "2026-02-28",
  "due_date": "2026-02-08",
  "items_json": [
    {"type": "BASE", "description": "Bazni paket", "amount": 3600},
    {"type": "LOCATION", "location_id": 2, "name": "Lokacija Zemun", "amount": 1800}
  ],
  "subtotal": 5400,
  "discount_amount": 0,
  "total_amount": 5400,
  "currency": "RSD",
  "status": "PENDING"
}
```

### 4.2 Statusi Fakture

| Status | Opis |
|--------|------|
| PENDING | Čeka uplatu |
| PAID | Plaćeno i verifikovano |
| OVERDUE | Prošao rok za plaćanje |
| CANCELLED | Otkazano |
| REFUNDED | Refundirano |

### 4.3 Workflow

```
1. GENERISANJE
   - Automatski 7 dana pre isteka pretplate
   - Ili admin ručno generiše
   - Sistemska poruka servisu

2. PRIJAVA UPLATE (servis)
   - Upload slike uplatnice
   - Unos reference plaćanja
   - Status ostaje PENDING

3. VERIFIKACIJA (admin)
   - Admin proverava na izvodu
   - Potvrđuje ili odbija
   - Ažurira tenant billing polja
   - Sistemska poruka servisu
```

---

## 5. Trust Score Sistem

### 5.1 Promene Score-a

| Događaj | Promena | Napomena |
|---------|---------|----------|
| Uplata pre roka | **+10** | Podstiče redovnost |
| Uplata u grace periodu | 0 | Neutralno |
| "Na reč" + platio | **-5** | Malo umanjenje |
| "Na reč" + NIJE platio | **-30** | Značajno umanjenje |
| 12 meseci uzastopnih uplata | **+15** | Godišnji bonus |

### 5.2 Nivoi

| Score | Nivo | Boja | Značenje |
|-------|------|------|----------|
| 80-100 | EXCELLENT | 🟢 Zeleno | Pouzdan |
| 60-79 | GOOD | 🟡 Žuto | Standardan |
| 40-59 | WARNING | 🟠 Narandžasto | Pažnja |
| 20-39 | RISKY | 🔴 Crveno | Problematičan |
| 0-19 | CRITICAL | ⚫ Crno | Kritičan |

---

## 6. "Uključenje na Reč" (Trust Activation)

### 6.1 Pravila

| Pravilo | Vrednost |
|---------|----------|
| Kada | Samo iz SUSPENDED statusa |
| Trajanje | 48 sati |
| Limit | 1x mesečno |
| Uslov | Mora platiti u 48h |

### 6.2 Workflow

```
SUSPENDED ──▶ [Klik: "Na reč"] ──▶ TRUST_ACTIVATED (48h)
                                          │
                ┌─────────────────────────┼─────────────────────────┐
                │                         │                         │
          Uplata u 48h              Dokaz u 48h              Nema uplate
                │                         │                         │
                ▼                         ▼                         ▼
           ACTIVE                    ACTIVE                    SUSPENDED
        trust: -5                  trust: -5                  trust: -30
```

---

## 7. Vremenska Linija Kašnjenja

```
Dan 0:  Faktura kreirana, rok 7 dana
        │
Dan 7:  ═══ ROK ZA PLAĆANJE ═══
        │
        │ ══════════════════════════════════════
        │        GRACE PERIOD (15 dana)
        │ ══════════════════════════════════════
        │
Dan 10: (3 dana kašnjenja) - Email + poruka
        │
Dan 14: (7 dana kašnjenja) - Email + poruka
        │
Dan 17: (10 dana kašnjenja) - Email + poruka
        │
Dan 21: (14 dana kašnjenja) - POSLEDNJE UPOZORENJE
        │
Dan 22: ═══ BLOKADA (SUSPENDED) ═══
```

---

## 8. Sistemske Poruke (TenantMessage)

### 8.1 Tipovi

| Tip | Opis |
|-----|------|
| SYSTEM | Automatska sistemska |
| ADMIN | Od platform admina |
| TENANT | Od drugog servisa (buduće) |
| SUPPLIER | Od dobavljača (buduće) |

### 8.2 Kategorije

| Kategorija | Opis |
|------------|------|
| BILLING | Fakture, uplate |
| PACKAGE_CHANGE | Promene cena |
| SYSTEM | Sistemska obaveštenja |
| SUPPORT | Podrška |
| ANNOUNCEMENT | Obaveštenja platforme |

### 8.3 Automatske Poruke

| Događaj | Naslov | Prioritet |
|---------|--------|-----------|
| Faktura kreirana | "Nova faktura za {mesec}" | NORMAL |
| Uplata potvrđena | "Uplata potvrđena - hvala!" | NORMAL |
| Kašnjenje 3 dana | "Faktura kasni 3 dana" | HIGH |
| Kašnjenje 7 dana | "Faktura kasni 7 dana" | HIGH |
| Kašnjenje 14 dana | "POSLEDNJE UPOZORENJE" | URGENT |
| Blokada | "Nalog blokiran" | URGENT |
| Trust aktiviran | "Na reč - imate 48h" | URGENT |
| Trust istekao | "48h isteklo bez uplate" | URGENT |

---

## 9. Blokada (SUSPENDED)

### 9.1 Dozvoljene Akcije

| Akcija | Dozvoljeno |
|--------|------------|
| Ulogovanje | ✅ Da |
| Pregled podataka | ✅ Da |
| Pregled naloga | ✅ Da |
| Zatvaranje postojećih naloga | ✅ Da |
| Naplata postojećih | ✅ Da |
| Aktiviranje "Na reč" | ✅ Da (1x mesečno) |

### 9.2 Zabranjene Akcije

| Akcija | Dozvoljeno |
|--------|------------|
| Kreiranje NOVIH naloga | ❌ Ne |
| Dodavanje telefona | ❌ Ne |
| Dodavanje delova | ❌ Ne |
| Marketplace | ❌ Ne |
| Naručivanje | ❌ Ne |
| Dodavanje lokacija | ❌ Ne |

---

## 10. API Endpointi

### 10.1 Tenant API (`/api/v1`)

| Metod | Endpoint | Opis |
|-------|----------|------|
| GET | `/subscription` | Status pretplate + billing |
| GET | `/subscription/payments` | Lista faktura |
| POST | `/subscription/payments/{id}/notify` | Prijavi uplatu |
| POST | `/subscription/trust-activate` | Aktiviraj "na reč" |
| GET | `/messages` | Lista poruka |
| GET | `/messages/unread-count` | Broj nepročitanih |
| PUT | `/messages/{id}/read` | Označi pročitano |
| DELETE | `/messages/{id}` | Obriši poruku |

### 10.2 Admin API (`/api/admin`)

| Metod | Endpoint | Opis |
|-------|----------|------|
| GET | `/payments` | Sve fakture |
| GET | `/payments/pending` | Čekaju verifikaciju |
| GET | `/payments/overdue` | Zakasnele |
| PUT | `/payments/{id}/verify` | Verifikuj uplatu |
| PUT | `/payments/{id}/reject` | Odbij uplatu |
| POST | `/tenants/{id}/invoice` | Generiši fakturu |
| POST | `/tenants/{id}/block` | Blokiraj |
| POST | `/tenants/{id}/unblock` | Deblokiraj |
| PUT | `/tenants/{id}/pricing` | Custom cene |
| POST | `/tenants/{id}/message` | Pošalji poruku |

---

## 11. Audit Log Akcije

| Akcija | Opis |
|--------|------|
| GENERATE_INVOICE | Generisana faktura |
| VERIFY_PAYMENT | Verifikovana uplata |
| REJECT_PAYMENT | Odbijena uplata |
| BLOCK_TENANT | Blokiran servis |
| UNBLOCK_TENANT | Deblokiran servis |
| UPDATE_PRICING | Promenjena cena |
| TRUST_ACTIVATE | Aktivirano "na reč" |
| TRUST_EXPIRED | Isteklo 48h |
| UPDATE_TRUST_SCORE | Promenjen trust score |
| SEND_MESSAGE | Poslata poruka |

---

## 12. Verzija Dokumenta

| Verzija | Datum | Opis |
|---------|-------|------|
| 1.0 | 2026-01-17 | Inicijalna verzija |

---

*Dokument kreiran za ServisHub SaaS platformu*
