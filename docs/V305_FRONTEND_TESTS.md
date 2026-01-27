# ServisHub v3.05 — Frontend + Test Suite

**Verzija:** 3.05
**Datum:** 27. Januar 2026
**Status:** Complete (64/64 testova prolazi)

---

## Pregled

Ova verzija dodaje frontend stranice za POS, Credits i Billing module, UI za upravljanje rezervnim delovima na tiketima, i kompletnu test suite za sve nove backend servise.

---

## 1. POS / Kasa Frontend

### Nove stranice
| Fajl | Opis |
|------|------|
| `app/templates/tenant/pos/register.html` | Otvaranje/zatvaranje kase, pregled sesije |
| `app/templates/tenant/pos/receipts.html` | Lista racuna sa filterima |
| `app/templates/tenant/pos/daily_report.html` | Dnevni izvestaj kase |

### Rute (`app/frontend/tenant.py`)
| Ruta | Funkcija |
|------|----------|
| `/pos/register` | POS kasa — otvaranje/zatvaranje |
| `/pos/receipts` | Lista racuna |
| `/pos/daily-report` | Dnevni izvestaj |

### Sidebar
- Link "Kasa" u `tenant_sidebar.html`, vidljiv samo kad je `pos_enabled` feature flag aktivan.

### Backend referenca
- API: `app/api/v1/pos.py`
- Service: `app/services/pos_service.py`
- Modeli: `CashRegisterSession`, `Receipt`, `ReceiptItem`

---

## 2. Credits Frontend

### Nove stranice
| Fajl | Opis |
|------|------|
| `app/templates/tenant/credits/balance.html` | Stanje kredita + istorija transakcija |
| `app/templates/tenant/credits/purchase.html` | Kupovina kredita (paketi + promo kod, idempotency) |

### Rute (`app/frontend/tenant.py`)
| Ruta | Funkcija |
|------|----------|
| `/credits` | Stanje kredita |
| `/credits/purchase` | Kupovina paketa |

### Sidebar
- Link "Krediti" u `tenant_sidebar.html`, vidljiv samo kad je `credits_enabled` feature flag aktivan.

### Backend referenca
- API: `app/api/v1/credits.py`
- Service: `app/services/credit_service.py`
- Modeli: `CreditBalance`, `CreditTransaction`
- Paketi: `CREDIT_PACKAGES` dict u `credit_service.py`

---

## 3. Billing Dashboard (Admin)

### Nova stranica
| Fajl | Opis |
|------|------|
| `app/templates/admin/billing/dashboard.html` | KPI kartice, top duznici, brzi pristup |

### Ruta (`app/frontend/admin.py`)
| Ruta | Funkcija |
|------|----------|
| `/admin/billing/dashboard` | Billing dashboard |

### Admin Sidebar
- Link "Billing Dashboard" u `app/templates/admin/_sidebar.html`.

---

## 4. Ticket Parts UI

### Izmena
- `app/templates/tenant/tickets/detail.html` — nova sekcija "Utroseni delovi":
  - Alpine.js komponenta za CRUD operacije
  - Modal za dodavanje dela (izbor dela, kolicina)
  - Prikaz ukupnog troska delova na tiketu
  - Automatska dedukcija/povrat zalihe

### Backend referenca
- API endpointi: `POST/GET /api/v1/tickets/<id>/parts`, `DELETE /api/v1/tickets/<id>/parts/<usage_id>`
- Model: `SparePartUsage` u `app/models/inventory.py`

---

## 5. Bugfixevi u app kodu

| Fajl | Fix |
|------|-----|
| `app/models/audit.py` | `AuditLog.log()` sada prima `user_id` parametar (int), pored `user` (objekat). POS service prosleđuje `user_id` umesto `user` objekta. |
| `app/api/public/marketplace.py` | Blueprint preimenovan u `public_marketplace_legacy` da izbegne koliziju sa `app/api/public_user/marketplace.py` |

---

## 6. Test Suite

**Rezultat:** 64/64 passed

### Novi test fajlovi
| Fajl | Testova | Pokriva |
|------|---------|---------|
| `tests/test_billing.py` | 10 | PROMO tranzicija, trust 72h, nema activate/unsuspend bypass |
| `tests/test_credits.py` | 11 | add/deduct/refund, API balance/packages/purchase, idempotency, feature flag OFF |
| `tests/test_pos.py` | 6 | open/close register, create+issue receipt, void bez kase, feature flag OFF |
| `tests/test_ticket_parts.py` | 7 | add/remove parts, stock dedukcija, insufficient stock, validacija |
| `tests/test_permissions.py` | 7 | POS/Credits pristup po roli (OWNER, TECHNICIAN, unauthenticated, cross-tenant) |

### Izmenjeni test fajlovi
| Fajl | Izmena |
|------|--------|
| `tests/conftest.py` | BigInteger→Integer SQLite compatibility (monkey-patch), NOW() SQLite function |
| `tests/test_v303_smoke.py` | Azuriran `test_payment_reference_generation` za novi 18-cifreni format (v3.04) |

### Postojeci testovi (nepromenjeni)
| Fajl | Testova |
|------|---------|
| `tests/test_idor.py` | 15 |
| `tests/test_v303_smoke.py` | 8 |

### Test infrastruktura (`conftest.py`)
- **SQLite kompatibilnost:** `_BigIntegerSQLite` TypeDecorator — mapira `BigInteger` PK na `Integer` za SQLite (autoincrement radi)
- **NOW() funkcija:** Registrovana custom SQLite funkcija za PostgreSQL kompatibilnost
- **Fixtures:** 2 tenanta (A, B), 3 lokacije, 3 korisnika (OWNER, TECHNICIAN x2), 3 auth klijenta
- **In-memory SQLite:** Svaki test dobija cistu bazu (`scope='function'`)

---

## 7. Feature Flag sistem

Oba nova modula (POS, Credits) su gated iza feature flagova:

| Flag | Kontrolise |
|------|-----------|
| `pos_enabled` | POS/Kasa pristup (API + sidebar link) |
| `credits_enabled` | Credits pristup (API + sidebar link) |

Kad je flag OFF:
- API vraca **403 Forbidden**
- Sidebar link se **ne prikazuje**

---

## 8. Pokretanje testova

```bash
cd c:\servishub
venv\Scripts\activate
python -m pytest tests/ -v
```

Ocekivani rezultat: `64 passed`