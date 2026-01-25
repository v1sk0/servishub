# ServisHub Billing System v303 - Dokumentacija

**Verzija:** 3.03
**Datum:** Januar 2026
**Status:** Backend - KOMPLETIRAN, UI - pending

---

## 1. Overview

Billing System v303 automatizuje kompletnu naplatu pretplate za ServisHub SaaS platformu:

- **Automatsko generisanje faktura** - mesečne fakture putem scheduler task-a
- **Bank import** - parsiranje bankovnih izvoda (CSV, XML)
- **Auto-matching** - uparivanje transakcija sa fakturama po pozivu na broj
- **Reconciliation** - označavanje plaćenih faktura i ažuriranje dugovanja
- **Email slanje** - fakture sa PDF i IPS QR kodom

---

## 2. Data Model

### SubscriptionPayment (STVARNO STANJE)
| Polje | Tip | Opis |
|-------|-----|------|
| id | BigInteger | PK |
| tenant_id | Integer | FK -> Tenant |
| invoice_number | String(50) | Format: SH-{YYYY}-{NNNNNN} |
| payment_reference | String(100) | Poziv na broj |
| payment_reference_model | String(5) | Model (97), default='97' |
| total_amount | Numeric(10,2) | Iznos za placanje |
| status | String(20) | PENDING, PAID, OVERDUE, CANCELLED |
| invoice_url | String(500) | URL PDF fakture |
| uplatnica_pdf_url | String(500) | URL PDF uplatnice |
| bank_transaction_id | BigInteger | FK -> BankTransaction |
| reconciled_at | DateTime | Kada je upareno |
| reconciled_via | String(50) | BANK_IMPORT, MANUAL, PROOF_UPLOAD |

**NAPOMENA:** `payment_reference_control` kolona NE POSTOJI - kontrolna cifra je sadrzana u `payment_reference` stringu.

### BankStatementImport
| Polje | Tip | Opis |
|-------|-----|------|
| id | Integer | PK |
| filename | String | Ime fajla |
| file_hash | String | SHA256 za deduplication |
| bank_code | String | ALTA, RAIF, etc. |
| total_transactions | Integer | Broj transakcija |
| matched_count | Integer | Auto-upareno |
| unmatched_count | Integer | Neupareno |

### BankTransaction
| Polje | Tip | Opis |
|-------|-----|------|
| id | Integer | PK |
| import_id | Integer | FK -> BankStatementImport |
| transaction_date | Date | Datum |
| amount | Decimal | Iznos |
| payer_name | String | Ime platioca |
| payment_reference | String | Poziv na broj (original) |
| match_status | Enum | UNMATCHED, MATCHED, MANUAL, IGNORED |
| matched_payment_id | Integer | FK -> SubscriptionPayment |
| match_method | String | EXACT_REF, MANUAL |

---

## 3. Payment Reference Format

### Struktura (MAX 13 cifara za IPS RO tag <=25)
```
97{tenant_id:06d}{seq:05d}
```

- **97** - Model (standardni IPS)
- **tenant_id** - 6 cifara (000001-999999)
- **seq** - 5 cifara invoice sequence

### Primer
Tenant ID 1234, seq 42:
```
Referenca: 9700123400042
Display: 97 001234 00042
```

### IPSService.generate_payment_reference() - RETURN FORMAT
```python
# Funkcija vraca (ips_service.py linije 101-120):
{
    'model': '97',                    # Za payment_reference_model
    'base': '00123400042',            # Bez modela
    'control': '68',                  # MOD97 kontrola (INFO ONLY)
    'full': '9700123400042',          # Za payment_reference (13 cifara)
    'display': '97 001234 00042',     # Za prikaz korisniku
    'formatted': '97 001234-00042-68' # Sa kontrolom za stampu
}
```

---

## 4. IPS QR Spec Compliance

### Obavezni tagovi
| Tag | Format | Primer |
|-----|--------|--------|
| K | "PR" | K:PR |
| V | "01" | V:01 |
| C | "1" (UTF-8) | C:1 |
| R | 18 cifara | R:160000123456789123 |
| N | Max 70 | N:SERVISHUB DOO |
| I | RSD+iznos | I:RSD5400,00 |
| SF | 221 (B2B) | SF:221 |

### Opcioni tagovi
| Tag | Format | Ogranicenje |
|-----|--------|-------------|
| **RO** | Poziv na broj | **Max 25 karaktera** |
| S | Svrha | Max 35 |
| P | Platioc | Max 70 |

### KRITICNO: RO tag
```python
# AKO payment_reference NE POSTOJI -> NE DODAVATI RO TAG!
if reference:
    parts.append(f"RO:{reference}")
# Prazan RO tag KVARI QR kod!
```

---

## 5. API Endpoints

### Admin API (`/api/admin/`)

| Metoda | Endpoint | Opis | Status |
|--------|----------|------|--------|
| GET | `/payments/` | Lista uplata | OK |
| GET | `/payments/stats` | Statistike uplata | DODATO |
| POST | `/payments/{id}/verify` | Rucna potvrda | OK |
| GET | `/payments/{id}/pdf` | Download PDF | OK |
| POST | `/payments/{id}/send` | Email slanje | OK |
| POST | `/bank-import` | Upload izvoda | OK |
| POST | `/bank-import/{id}/process` | Auto-match | OK |
| GET | `/bank-transactions/unmatched` | Neuparene | OK |
| POST | `/bank-transactions/{id}/match` | Rucno upari | OK |
| POST | `/bank-transactions/{id}/ignore` | Ignorisi | OK |

### Tenant API (`/api/v1/tenant/`)

| Metoda | Endpoint | Opis | Status |
|--------|----------|------|--------|
| GET | `/subscription/payments` | Lista faktura | OK |
| GET | `/subscription/payments/{id}` | Detalji | OK |
| GET | `/subscription/payments/{id}/pdf` | PDF fakture | DODATO |
| GET | `/subscription/payments/{id}/uplatnica` | PDF uplatnice | DODATO |
| GET | `/subscription/payments/{id}/qr` | IPS QR PNG | DODATO |

---

## 6. Bank Import Flow

```
UPLOAD -> PARSE -> AUTO-MATCH -> RECONCILE
```

1. **Upload** - Admin uploaduje CSV/XML
2. **Parse** - Detektuje banku, parsira transakcije
3. **Auto-Match** - SAMO EXACT_REF + amount match
4. **Reconcile** - Payment -> PAID, debt update

---

## 7. Matching Rules

### Auto-Match (SAMO EXACT_REF)
```
IF payment_reference_normalized == payment.payment_reference
AND amount == payment.total_amount
AND confidence >= 1.0
THEN -> MATCHED, call reconcile_payment()
```

### Manual Suggestions (za UI)
- FUZZY_REF: 0.9 confidence
- AMOUNT_TENANT: 0.7 confidence
- AMOUNT_DATE: 0.5 confidence

-> NE AUTO-MATCH, samo predlozi za rucno uparivanje!

---

## 8. Email Sending

### Endpoint
`POST /api/admin/payments/{id}/send`

### Attachments
1. `faktura_{broj}.pdf`
2. `uplatnica_{broj}.pdf`
3. `qr_{broj}.png` (IPS QR)

---

## 9. ISPRAVLJENI BUGOVI (v303)

### BUG 1: dashboard.py - p.amount -> p.total_amount
**Fajl:** `app/api/admin/dashboard.py` linija 452

### BUG 2: tenants.py - p.amount -> p.total_amount
**Fajl:** `app/api/admin/tenants.py` linija 192

### BUG 3: billing_tasks.py - payment_reference
**Fajl:** `app/services/billing_tasks.py` linije 371-390
- Dodato: `IPSService.generate_payment_reference()` za generisanje reference

### BUG 4: tenant.py - payment_reference format
**Fajl:** `app/api/v1/tenant.py`
- Koristi `IPSService.generate_payment_reference()` umesto rucnog formata

### BUG 5: tenant.py - hard-coded bank info
**Fajl:** `app/api/v1/tenant.py`
- Koristi `PlatformSettings.get_settings()` za bank info

### BUG 6: ips_service.py - RO tag za prazan reference
**Fajl:** `app/services/ips_service.py` linije 196-200
- RO tag se dodaje SAMO ako postoji reference

### BUG 7: payment_matcher.py - preagresivan auto-match
**Fajl:** `app/services/payment_matcher.py` linije 48-75
- Auto-match SAMO za EXACT_REF sa confidence >= 1.0

### BUG 8: bank_import.py - auto-match bez reconcile
**Fajl:** `app/api/admin/bank_import.py` linije 387-399
- Dodato: `reconcile_payment()` poziv nakon uspesnog match-a

### BUG 9: billing_tasks.py - notes kolona
**Fajl:** `app/services/billing_tasks.py`
- Uklonjen `notes` parametar (kolona ne postoji)

---

## 10. DODATI ENDPOINTI (v303)

### 1. GET /api/admin/payments/stats
```python
@bp.route('/stats', methods=['GET'])
@platform_admin_required
def get_payments_stats():
    """Statistike uplata za dashboard."""
    # Vraca: pending_count, paid_count, overdue_count, total amounts
```

### 2. GET /api/v1/tenant/subscription/payments/{id}/pdf
```python
@bp.route('/subscription/payments/<int:payment_id>/pdf', methods=['GET'])
@jwt_required
def get_payment_pdf(payment_id):
    """Download PDF fakture."""
```

### 3. GET /api/v1/tenant/subscription/payments/{id}/uplatnica
```python
@bp.route('/subscription/payments/<int:payment_id>/uplatnica', methods=['GET'])
@jwt_required
def get_payment_slip(payment_id):
    """Download PDF uplatnice."""
```

### 4. GET /api/v1/tenant/subscription/payments/{id}/qr
```python
@bp.route('/subscription/payments/<int:payment_id>/qr', methods=['GET'])
@jwt_required
def get_payment_qr(payment_id):
    """Download IPS QR kod kao PNG."""
```

---

## 11. File Structure

```
app/
|-- api/
|   |-- admin/
|   |   |-- payments.py         # Admin payments + /stats
|   |   |-- bank_import.py      # Bank upload + match + reconcile
|   |   |-- bank_transactions.py # Manual matching
|   |   |-- dashboard.py        # FIXED: p.total_amount
|   |   +-- tenants.py          # FIXED: p.total_amount
|   +-- v1/
|       +-- tenant.py           # FIXED: IPSService + PlatformSettings + endpoints
|-- services/
|   |-- billing_tasks.py        # FIXED: payment_reference
|   |-- ips_service.py          # FIXED: RO tag
|   |-- payment_matcher.py      # FIXED: EXACT_REF only
|   |-- reconciliation.py       # OK
|   +-- pdf_service.py          # OK
+-- models/
    +-- bank_import.py          # OK
```

---

## 12. Smoke Tests

### Test 1: Payment Reference
```python
from app.services.ips_service import IPSService
ref = IPSService.generate_payment_reference(1234, 42)
assert ref['full'] == '9700123400042'
assert ref['model'] == '97'
assert len(ref['full']) == 13  # Staje u RO tag (max 25)
```

### Test 2: IPS QR bez RO taga
```python
# Payment bez payment_reference
payment.payment_reference = None
qr_string = ips.generate_qr_string(payment, tenant, settings)
assert 'RO:' not in qr_string  # Prazan RO se NE dodaje
```

### Test 3: Auto-match EXACT_REF only
```python
# Transakcija sa tacnim pozivom i iznosom
txn.payment_reference = '9700123400042'
txn.amount = Decimal('5400.00')
# Payment sa istim
payment.payment_reference = '9700123400042'
payment.total_amount = Decimal('5400.00')
# Rezultat: MATCHED

# Transakcija sa iznosom ali BEZ poziva
txn2.payment_reference = None
txn2.amount = Decimal('5400.00')
# Rezultat: UNMATCHED (ne koristi AMOUNT_MATCH za auto)
```

### Test 4: Bank import + reconcile
```python
# Upload CSV sa EXACT_REF match
# Ocekivano posle process_import():
assert bank_transaction.match_status == MatchStatus.MATCHED
assert payment.status == 'PAID'
assert tenant.current_debt == (old_debt - payment.total_amount)
```

---

## 13. Verifikacija

1. Generisati test fakturu -> proveriti payment_reference format (13 cifara)
2. Generisati IPS QR za fakturu BEZ reference -> nema RO tag
3. Upload test CSV sa EXACT_REF -> MATCHED + PAID + debt update
4. Upload test CSV bez reference -> UNMATCHED (ne koristi fuzzy)
5. Tenant endpoint /pdf -> download radi
6. Tenant endpoint /qr -> PNG download radi

---

## 14. Sazetak v303 Izmena

### ISPRAVLJENO (9 bugova):
1. `dashboard.py:452` - p.amount -> p.total_amount
2. `tenants.py:192` - p.amount -> p.total_amount
3. `billing_tasks.py:373` - dodato payment_reference via IPSService
4. `tenant.py` - koristi IPSService za reference
5. `tenant.py` - koristi PlatformSettings za bank info
6. `ips_service.py:196` - RO tag samo ako postoji reference
7. `payment_matcher.py:61` - auto-match SAMO za EXACT_REF
8. `bank_import.py:375` - pozvana reconcile_payment()
9. `billing_tasks.py` - uklonjen notes parametar

### DODATO (4 endpointa):
1. `GET /api/admin/payments/stats` - statistike uplata
2. `GET /api/v1/tenant/subscription/payments/{id}/pdf` - PDF fakture
3. `GET /api/v1/tenant/subscription/payments/{id}/uplatnica` - PDF uplatnice
4. `GET /api/v1/tenant/subscription/payments/{id}/qr` - IPS QR PNG

### MIGRACIJE:
- Nisu potrebne - koriste se postojece kolone

---

## 15. Sledeci Koraci

1. **UI Admin Panel** - stranice za bank import i matching
2. **Testiranje** - end-to-end test sa pravim bankovnim izvodom
3. **Email templates** - HTML sabloni za fakture
