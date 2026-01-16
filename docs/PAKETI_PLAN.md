# ServisHub - Sistem Paketa i Naplate

> Dokumentacija za sistem pretplata, naplate i trust score mehanizma

---

## 1. Cenovnik

| Stavka | Cena | Napomena |
|--------|------|----------|
| Bazni paket | 3.600 RSD/mesec | Uključuje 1 preduzeće + 1 lokaciju |
| Dodatna lokacija | +1.800 RSD/mesec | Po svakoj dodatnoj lokaciji |
| Valuta | RSD | Fiksno |

### Primeri kalkulacije

| Broj lokacija | Kalkulacija | Ukupno mesečno |
|---------------|-------------|----------------|
| 1 lokacija | 3.600 | 3.600 RSD |
| 2 lokacije | 3.600 + 1.800 | 5.400 RSD |
| 3 lokacije | 3.600 + (2 × 1.800) | 7.200 RSD |
| 5 lokacija | 3.600 + (4 × 1.800) | 10.800 RSD |
| 10 lokacija | 3.600 + (9 × 1.800) | 19.800 RSD |

---

## 2. Obračunski Period

| Pravilo | Vrednost |
|---------|----------|
| Obračunski period | Od 1. do poslednjeg dana u mesecu |
| Prvi mesec | Proporcionalno (pro-rata) |
| Rok za plaćanje | 7 dana od kreiranja fakture |
| Grace period | 15 dana nakon roka za plaćanje |

### Proporcionalni obračun prvog meseca

Ako se servis registruje usred meseca, prvi mesec se naplaćuje proporcionalno:

| Datum registracije | Procenat meseca | Primer (bazni paket) |
|--------------------|-----------------|----------------------|
| 1. u mesecu | 100% | 3.600 RSD |
| 10. u mesecu | ~70% | 2.520 RSD |
| 15. u mesecu | 50% | 1.800 RSD |
| 25. u mesecu | ~20% | 720 RSD |

---

## 3. Statusi Servisa

### Dijagram prelaza statusa

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│   REGISTRACIJA                                                          │
│        │                                                                │
│        ▼                                                                │
│   ┌─────────┐    Admin aktivira    ┌─────────┐                         │
│   │  DEMO   │ ─────────────────▶   │  TRIAL  │                         │
│   │ (7 dana)│                      │(90 dana)│                         │
│   └─────────┘                      └────┬────┘                         │
│                                         │                               │
│                                         │ Plaćanje                      │
│                                         ▼                               │
│                                    ┌─────────┐                         │
│                      ┌────────────▶│ ACTIVE  │◀────────────┐           │
│                      │             └────┬────┘             │           │
│                      │                  │                  │           │
│                      │                  │ Istekla          │           │
│                      │                  │ pretplata        │           │
│                      │                  ▼                  │           │
│                 Plaćanje          ┌─────────┐              │           │
│                      │            │ EXPIRED │              │           │
│                      │            │(grace   │              │           │
│                      │            │ 15 dana)│              │           │
│                      │            └────┬────┘              │           │
│                      │                 │                   │           │
│                      │                 │ 15 dana           │           │
│                      │                 │ bez uplate        │           │
│                      │                 ▼                   │           │
│                      │           ┌──────────┐              │           │
│                      └───────────│SUSPENDED │──────────────┘           │
│                                  │(blokiran)│     Plaćanje             │
│                                  └────┬─────┘                          │
│                                       │                                │
│                                       │ "Na reč"                       │
│                                       ▼                                │
│                                  ┌──────────┐                          │
│                                  │  TRUST   │                          │
│                                  │ACTIVATED │                          │
│                                  │  (48h)   │                          │
│                                  └──────────┘                          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Opis statusa

| Status | Trajanje | Pristup | Opis |
|--------|----------|---------|------|
| **DEMO** | 7 dana | Pun | Automatski pri registraciji. Servis može da testira sve funkcije. |
| **TRIAL** | 90 dana | Pun | Admin aktivira nakon KYC verifikacije. Besplatno korišćenje. |
| **ACTIVE** | Do isteka pretplate | Pun | Aktivna plaćena pretplata. |
| **EXPIRED** | 15 dana (grace) | Pun + upozorenja | Pretplata istekla, ali još nije blokiran. |
| **SUSPENDED** | Neograničeno | Ograničen | Blokiran zbog neplaćanja. |
| **TRUST_ACTIVATED** | 48 sati | Pun | Aktivirao "Na reč", ima 48h da plati. |

---

## 4. Blokada (SUSPENDED Status)

Kada servis uđe u SUSPENDED status zbog neplaćanja, ima ograničen pristup.

### Dozvoljene akcije

| Akcija | Dozvoljeno |
|--------|------------|
| Ulogovanje u sistem | ✅ Da |
| Pregled svih podataka | ✅ Da |
| Pregled servisnih naloga | ✅ Da |
| Završavanje/zatvaranje postojećih naloga | ✅ Da |
| Naplata postojećih naloga | ✅ Da |
| Pregled inventara | ✅ Da |
| Aktiviranje "Na reč" | ✅ Da (1x mesečno) |

### Zabranjene akcije

| Akcija | Dozvoljeno |
|--------|------------|
| Kreiranje NOVIH servisnih naloga | ❌ Ne |
| Dodavanje telefona na lager | ❌ Ne |
| Dodavanje rezervnih delova | ❌ Ne |
| Korišćenje marketplace-a | ❌ Ne |
| Naručivanje od dobavljača | ❌ Ne |
| Dodavanje novih lokacija | ❌ Ne |

---

## 5. Uključenje na Reč (Trust Activation)

Mehanizam koji omogućava blokiranom servisu da privremeno nastavi rad uz obećanje plaćanja.

### Pravila

| Pravilo | Vrednost |
|---------|----------|
| Kada se može aktivirati | Samo iz SUSPENDED statusa |
| Trajanje | 48 sati od aktivacije |
| Limit korišćenja | 1x po obračunskom periodu (mesecu) |
| Uslov | Mora platiti ili poslati dokaz o uplati u roku od 48h |

### Workflow

```
SUSPENDED ──▶ [Klik: "Uključenje na reč"] ──▶ TRUST_ACTIVATED (48h)
                                                      │
                    ┌─────────────────────────────────┼─────────────────────────────────┐
                    │                                 │                                 │
              Uplata u 48h                   Dokaz o uplati u 48h              Nema uplate/dokaza
                    │                        (admin verifikuje kasnije)               │
                    ▼                                 │                                 ▼
               ACTIVE                                 ▼                            SUSPENDED
           trust_score: -5                       ACTIVE                        trust_score: -30
                                            trust_score: -5
```

### Posledice

| Scenario | Status nakon | Trust Score |
|----------|--------------|-------------|
| Plati u roku od 48h | ACTIVE | -5 |
| Pošalje dokaz, admin verifikuje | ACTIVE | -5 |
| Ne plati i ne pošalje dokaz | SUSPENDED | -30 |

---

## 6. Trust Score (Sistem Poverenja)

Numerička vrednost koja pokazuje pouzdanost servisa u pogledu plaćanja.

### Promene Trust Score-a

| Događaj | Promena | Napomena |
|---------|---------|----------|
| Uplata na vreme (pre roka) | **+10** | Podstiče redovno plaćanje |
| Uplata u grace periodu (1-15 dana) | 0 | Neutralno |
| Koristi "Na reč" i plati u 48h | -5 | Malo umanjenje zbog kašnjenja |
| Koristi "Na reč" i NE plati | **-30** | Značajno umanjenje |
| 12 meseci uzastopnih uplata na vreme | **+15** | Godišnji bonus za pouzdanost |

### Nivoi Trust Score-a

| Score | Nivo | Boja | Značenje |
|-------|------|------|----------|
| 80-100 | Odličan | 🟢 Zeleno | Pouzdan korisnik, nema problema |
| 60-79 | Dobar | 🟡 Žuto | Standardan korisnik |
| 40-59 | Upozorenje | 🟠 Narandžasto | Potrebna pažnja, česta kašnjenja |
| 20-39 | Rizičan | 🔴 Crveno | Problematičan korisnik |
| 0-19 | Kritičan | ⚫ Crno | Kandidat za trajnu blokadu |

### Početna vrednost

- Novi servis počinje sa **trust_score = 100**

### Admin akcije na osnovu Trust Score-a

| Trust Score | Preporučena akcija |
|-------------|-------------------|
| < 40 | Razmotriti ručnu blokadu ili kontakt |
| < 20 | Razmotriti trajno ukidanje naloga |

---

## 7. Fakture i Plaćanje

### Generisanje faktura

| Tip | Kada | Ko |
|-----|------|-----|
| Automatski | 7 dana pre isteka pretplate | Sistem |
| Ručno | Po potrebi | Admin |

### Metodi plaćanja

| Metod | Podržan | Napomena |
|-------|---------|----------|
| Bankarski transfer | ✅ Da | Primarni metod |
| Kartica | ❌ Ne (za sada) | Planirano za budućnost |
| Gotovina | ❌ Ne | Nije podržano |

### Proces plaćanja

1. **Sistem generiše fakturu** (automatski ili admin ručno)
2. **Servis dobija obaveštenje** (email + in-app poruka)
3. **Servis vrši uplatu** na bankovni račun
4. **Servis prijavljuje uplatu** (upload slike uplatnice)
5. **Admin verifikuje uplatu**
6. **Status se ažurira** na ACTIVE

### Struktura fakture

```json
{
  "invoice_number": "SH-2026-001234",
  "tenant_id": 42,
  "period_start": "2026-02-01",
  "period_end": "2026-02-28",
  "items": [
    {"type": "BASE", "description": "Bazni paket", "amount": 3600},
    {"type": "LOCATION", "location_id": 2, "name": "Lokacija Zemun", "amount": 1800},
    {"type": "LOCATION", "location_id": 3, "name": "Lokacija Novi Beograd", "amount": 1800}
  ],
  "subtotal": 7200,
  "discount_amount": 0,
  "total_amount": 7200,
  "currency": "RSD",
  "due_date": "2026-02-08",
  "status": "PENDING"
}
```

---

## 8. Custom Cene (Popusti)

Admin može postaviti prilagođene cene za pojedinačne servise.

### Pravila

| Pravilo | Vrednost |
|---------|----------|
| Ko može promeniti | Samo Platform Admin |
| Kada se primenjuje | Od sledećeg obračunskog perioda |
| Obaveštenje | Servis dobija sistemsku poruku |

### Primer

```
Standardna cena: 3.600 RSD
Custom cena za "Servis XYZ": 2.500 RSD
Razlog: "Dugoročna saradnja - 30% popust"
Važi od: 2026-03-01
```

---

## 9. Sistem Poruka (Inbox)

In-app sistem za obaveštenja i komunikaciju.

### Tipovi poruka

| Tip | Izvor | Opis |
|-----|-------|------|
| SYSTEM | Automatski | Sistemska obaveštenja |
| ADMIN | Platform Admin | Direktna komunikacija |
| TENANT | Drugi servis | *(Buduće)* |
| SUPPLIER | Dobavljač | *(Buduće)* |

### Automatske sistemske poruke

| Događaj | Naslov | Prioritet |
|---------|--------|-----------|
| Faktura kreirana | "Nova faktura za februar 2026" | NORMAL |
| Uplata potvrđena | "Uplata potvrđena - hvala!" | NORMAL |
| Trial ističe (7 dana) | "Trial period ističe za 7 dana" | HIGH |
| Kašnjenje 3 dana | "Faktura kasni 3 dana" | HIGH |
| Kašnjenje 7 dana | "Faktura kasni 7 dana" | HIGH |
| Kašnjenje 10 dana | "Faktura kasni 10 dana - upozorenje" | HIGH |
| Kašnjenje 14 dana | "POSLEDNJE UPOZORENJE - blokada za 1 dan" | URGENT |
| Blokada | "Nalog je blokiran zbog neplaćanja" | URGENT |
| Deblokada | "Nalog je ponovo aktivan" | NORMAL |
| Promena cene | "Obaveštenje o promeni cene paketa" | HIGH |
| "Na reč" aktivirano | "Aktivirali ste uključenje na reč - imate 48h" | URGENT |

---

## 10. Email Notifikacije

### Kada se šalju emailovi

| Događaj | Email | Timing |
|---------|-------|--------|
| Trial ističe | ✅ Da | 7 dana pre |
| Faktura kreirana | ✅ Da | Odmah |
| Uplata potvrđena | ✅ Da | Odmah |
| Kašnjenje 3 dana | ✅ Da | Dan 3 |
| Kašnjenje 7 dana | ✅ Da | Dan 7 |
| Kašnjenje 10 dana | ✅ Da | Dan 10 |
| Kašnjenje 14 dana | ✅ Da | Dan 14 |
| Blokada | ✅ Da | Dan 15 |
| "Na reč" aktivirano | ✅ Da | Odmah |
| "Na reč" ističe (bez uplate) | ✅ Da | Nakon 48h |

---

## 11. Vremenska Linija Kašnjenja

```
Dan 0: Faktura kreirana, rok 7 dana
       │
Dan 7: ROK ZA PLAĆANJE
       │
       │ ══════════════════════════════════════
       │        GRACE PERIOD (15 dana)
       │ ══════════════════════════════════════
       │
Dan 10 (3 dana kašnjenja): Email + poruka upozorenja
       │
Dan 14 (7 dana kašnjenja): Email + poruka upozorenja
       │
Dan 17 (10 dana kašnjenja): Email + poruka upozorenja
       │
Dan 21 (14 dana kašnjenja): POSLEDNJE UPOZORENJE
       │
Dan 22 (15 dana kašnjenja): ══▶ BLOKADA (SUSPENDED)
```

---

## 12. Audit Log

Sve akcije vezane za pakete se loguju.

| Akcija | Opis |
|--------|------|
| VERIFY_PAYMENT | Admin verifikovao uplatu |
| REJECT_PAYMENT | Admin odbio uplatu |
| GENERATE_INVOICE | Generisana faktura (auto ili ručno) |
| BLOCK_TENANT | Servis blokiran |
| UNBLOCK_TENANT | Servis deblokiran |
| ADD_DISCOUNT | Promenjena cena paketa |
| SEND_MESSAGE | Poslata poruka servisu |
| TRUST_ACTIVATE | Servis aktivirao "na reč" |
| TRUST_EXPIRED | Isteklo 48h bez uplate |
| UPDATE_TRUST_SCORE | Promenjen trust score |

---

## 13. Tehnička Implementacija

### Novi Modeli

| Model | Tabela | Opis |
|-------|--------|------|
| SubscriptionPayment | subscription_payment | Evidencija faktura/uplata |
| TenantMessage | tenant_message | Sistem poruka |

### Proširenje Tenant Modela

```python
# Dugovanje
current_debt = db.Column(db.Numeric(10, 2), default=0)
last_payment_at = db.Column(db.DateTime)
days_overdue = db.Column(db.Integer, default=0)

# Blokada
blocked_at = db.Column(db.DateTime)
block_reason = db.Column(db.String(200))

# Trust Score
trust_score = db.Column(db.Integer, default=100)
trust_activated_at = db.Column(db.DateTime)
trust_activation_count = db.Column(db.Integer, default=0)
last_trust_activation_period = db.Column(db.String(7))

# Custom cene
custom_base_price = db.Column(db.Numeric(10, 2))
custom_location_price = db.Column(db.Numeric(10, 2))
custom_price_reason = db.Column(db.String(200))
custom_price_valid_from = db.Column(db.Date)
```

### API Endpointi

**Tenant API:**
```
GET  /api/v1/subscription              - Status pretplate
GET  /api/v1/subscription/payments     - Istorija uplata
POST /api/v1/subscription/notify       - Prijavi uplatu
POST /api/v1/subscription/trust-activate - Aktiviraj "na reč"
GET  /api/v1/messages                  - Lista poruka
GET  /api/v1/messages/unread-count     - Broj nepročitanih
PUT  /api/v1/messages/:id/read         - Označi kao pročitano
```

**Admin API:**
```
GET    /api/admin/payments             - Sve uplate
GET    /api/admin/payments/pending     - Čekaju verifikaciju
GET    /api/admin/payments/overdue     - Zakasnele
PUT    /api/admin/payments/:id/verify  - Verifikuj
PUT    /api/admin/payments/:id/reject  - Odbij
POST   /api/admin/tenants/:id/invoice  - Generiši fakturu
POST   /api/admin/tenants/:id/message  - Pošalji poruku
POST   /api/admin/tenants/:id/block    - Blokiraj
POST   /api/admin/tenants/:id/unblock  - Deblokiraj
PUT    /api/admin/tenants/:id/pricing  - Promeni cenu
```

---

## 14. Verzija Dokumenta

| Verzija | Datum | Opis |
|---------|-------|------|
| 1.0 | 2026-01-16 | Inicijalna verzija |

---

*Dokument kreiran za ServisHub SaaS platformu*