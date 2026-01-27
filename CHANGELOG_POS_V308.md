# ServisHub — Changelog

---

## v3.08 — POS & Magacin Redizajn (2026-01-27)

Kompletna nadogradnja POS sistema i uvođenje magacina (robe) sa ulaznim fakturama, fiskalnom podrškom i automatskim računima za servisne naloge.

### Novi modeli

| Model | Fajl | Opis |
|-------|------|------|
| `GoodsItem` | `app/models/goods.py` | Artikl robe za maloprodaju — naziv, barkod, SKU, kategorija, nabavna/prodajna cena, marža%, stanje, poreska stopa |
| `PurchaseInvoice` | `app/models/goods.py` | Ulazna faktura od dobavljača — dobavljač, PIB, broj fakture, datum, ukupan iznos |
| `PurchaseInvoiceItem` | `app/models/goods.py` | Stavka ulazne fakture — artikl, količina, nabavna/prodajna cena, marža |
| `StockAdjustment` | `app/models/goods.py` | Korekcija stanja — otpis, inventura, oštećenje, povrat dobavljaču |
| `PosAuditLog` | `app/models/goods.py` | Audit trail za POS operacije — otvaranje/zatvaranje kase, izdavanje/storno računa, stock korekcije |

### Izmenjeni modeli

| Model | Izmene |
|-------|--------|
| `CashRegisterSession` | Dodato `fiscal_mode` polje (nasledjuje iz lokacije) |
| `Receipt` | Dodato: `fiscal_status`, `fiscal_response_json`, `fiscal_retry_count`, `fiscal_error_code`, `fiscal_qr_code`, `idempotency_key`, `buyer_pib`, `buyer_name`, `service_ticket_id` |
| `ReceiptItem` | Dodato `goods_item_id` FK |
| `SaleItemType` enum | Dodat `GOODS` tip stavke |
| `ServiceLocation` | Dodato: `fiscal_mode`, `pfr_url`, `pfr_type`, `business_unit_code`, `device_code`, `company_pib`, `company_name`, `company_address` |
| `ServiceTicket` | Dodat `parts_cost` property (računa iz SparePartUsage) |

### Novi servisi

| Servis | Fajl | Opis |
|--------|------|------|
| `GoodsService` | `app/services/goods_service.py` | CRUD artikala, prijem faktura, kalkulacija marže, zaokruživanje cena, stock korekcije, atomska dedukcija |
| `suggest_selling_price()` | `app/models/goods.py` | Predlog prodajne cene: nabavna × marža%, zaokruženo (≤500→10, ≤2000→50, >2000→100) |

### Izmenjeni servisi

| Servis | Izmene |
|--------|--------|
| `POSService.open_register()` | Nasledjuje `fiscal_mode` iz `ServiceLocation` |
| `POSService.add_item_to_receipt()` | Podrška za `GOODS` tip — atomska dedukcija stanja, nabavna/prodajna cena iz artikla |
| `POSService.issue_receipt()` | Idempotency key podrška, `buyer_pib`/`buyer_name`, `fiscal_status='pending'` za fiskalne kase |
| `POSService.void_receipt()` | Vraćanje GOODS stanja pri storniranju |
| `POSService.refund_receipt()` | Vraćanje GOODS stanja pri refundu |
| `POSService.create_service_receipt()` | **NOVO** — automatski račun pri preuzimanju servisnog naloga (DELIVERED). Idempotency: `ticket-deliver-{id}`. Auto-open sesije ako ne postoji. |

### Novi API endpointi

| Endpoint | Metoda | Opis |
|----------|--------|------|
| `/api/v1/goods` | GET | Lista artikala robe (pretraga, filteri, paginacija) |
| `/api/v1/goods` | POST | Kreiranje novog artikla |
| `/api/v1/goods/<id>` | GET | Detalji artikla |
| `/api/v1/goods/<id>` | PUT | Ažuriranje artikla |
| `/api/v1/goods/<id>/adjust` | POST | Stock korekcija (otpis, inventura, oštećenje) |
| `/api/v1/goods/suggest-price` | GET | Predlog prodajne cene (nabavna + marža) |
| `/api/v1/goods/categories` | GET | Lista kategorija |
| `/api/v1/goods/invoices` | GET | Lista ulaznih faktura |
| `/api/v1/goods/invoices` | POST | Kreiranje ulazne fakture |
| `/api/v1/goods/invoices/<id>/items` | POST | Dodavanje stavke na fakturu |
| `/api/v1/goods/invoices/<id>/receive` | POST | Prijem fakture (ažurira stanje robe) |
| `/api/v1/pos/search-items` | GET | Pretraga artikala za kasu (roba + delovi + telefoni) |
| `/api/v1/pos/reports/x` | GET | X izveštaj — tekući promet (ne zatvara kasu) |
| `/api/v1/pos/reports/z` | POST | Z izveštaj — dnevni obračun (zatvara kasu, generiše DailyReport) |
| `/api/v1/tickets/<id>/parts/receive-and-use` | POST | Brzi prijem dela od dobavljača + utrošak na nalog |

### Izmenjeni API endpointi

| Endpoint | Izmene |
|----------|--------|
| `POST /api/v1/pos/register/open` | Vraća `fiscal_mode` u response |
| `GET /api/v1/pos/register/current` | Vraća `fiscal_mode` u response |
| `POST /api/v1/pos/receipts/<id>/issue` | Prima `idempotency_key`, `buyer_pib`, `buyer_name`; vraća `fiscal_status` |
| `POST /api/v1/tickets/<id>/collect` | Automatski kreira POS račun pri preuzimanju naloga |

### Frontend

| Stranica | Fajl | Opis |
|----------|------|------|
| POS Kasa | `register.html` | **Potpuni redizajn** — search bar za artikle, dual-mode badge (FISKALNA/INTERNA), keyboard shortcuts (F1/F2/ESC), payment panel sa gotovina/kartica/prenos, B2B polja, idempotency |
| Roba — lista | `goods/list.html` | **NOVO** — CRUD artikala, pretraga, filteri, stock korekcija modal |
| Ulazne fakture — lista | `goods/invoice_list.html` | **NOVO** — tabela faktura sa status badge-om |
| Ulazna faktura — unos | `goods/invoice.html` | **NOVO** — header + stavke, predlog cene, prijem fakture |
| Sidebar | `tenant_sidebar.html` | Dodat "Magacin" link sa podmenijima |
| Frontend rute | `tenant.py` | Dodati: `/goods`, `/goods/invoices`, `/goods/invoices/new` |

### Dual-Mode POS — Fiskalna vs Interna kasa

- `ServiceLocation.fiscal_mode` — podešavanje po lokaciji
- `CashRegisterSession.fiscal_mode` — nasledjuje iz lokacije pri otvaranju
- Fiskalna kasa: `fiscal_status='pending'` na izdatim računima (priprema za PFR integraciju)
- Interna kasa: `fiscal_status=None` — iste funkcije, bez fiskalnih polja
- UI badge prikazuje režim kase

### Srpska fiskalizacija — priprema

Polja pripremljena za buduću LPFR/VPFR integraciju:
- `Receipt`: fiscal_status, fiscal_response_json, fiscal_qr_code, fiscal_signature, fiscal_invoice_number
- `ServiceLocation`: pfr_url, pfr_type, business_unit_code, device_code, company_pib/name/address
- Poreske stope: A=20%, B=10%, C=0% (`GoodsItem.tax_label`)

### Bugfix-evi pronađeni tokom testiranja

1. **`Decimal(str(None))` crash** — API prosleđivao `None` za `unit_price`/`purchase_price` umesto da izostavi parametar. Fix: `kwargs.get('key') or default` umesto `kwargs.get('key', default)` u svim 6 tipova stavki (`pos_service.py`)
2. **SQLite date parsing** — `invoice_date` string nije parsiran u Python `date` objekat. Fix: `_parse_date()` helper u `goods_service.py`

### Testovi

**34 novih testova** u `tests/test_goods_pos.py` (ukupno 98/98 prolazi):

| Test klasa | Br. | Šta pokriva |
|------------|-----|-------------|
| `TestSuggestPrice` | 4 | Zaokruživanje cena (3 ranga + granica) |
| `TestGoodsCRUD` | 7 | Kreiranje, lista, pretraga, update, IDOR izolacija, feature flag |
| `TestPurchaseInvoice` | 2 | Kreiranje + prijem fakture (stock raste), prazna faktura |
| `TestStockAdjustment` | 3 | Otpis, negativno stanje, audit log |
| `TestPOSWithGoods` | 5 | Prodaja GOODS stavke, nedovoljno stanje, pretraga po imenu/barkodu |
| `TestIdempotency` | 1 | Dupli issue sa istim ključem → isti račun |
| `TestDualMode` | 3 | Interna (fiscal_status=None), fiskalna (pending), API fiscal_mode |
| `TestServiceReceipt` | 4 | Auto-račun, idempotencija, fiskalni režim, auto-open sesije |
| `TestVoidRefundStock` | 2 | Void/refund vraća GOODS stanje |
| `TestXZReports` | 2 | X izveštaj (čita promet), Z izveštaj (zatvara kasu) |
| `TestB2BBuyer` | 1 | PIB/naziv kupca na računu |

### Migracija

- `migrations/versions/v308_goods_invoice_fiscal.py` — sve nove tabele i kolone

### Izmenjeni fajlovi — kompletna lista

**Novi fajlovi:**
- `app/models/goods.py`
- `app/services/goods_service.py`
- `app/api/v1/goods.py`
- `app/templates/tenant/goods/list.html`
- `app/templates/tenant/goods/invoice.html`
- `app/templates/tenant/goods/invoice_list.html`
- `migrations/versions/v308_goods_invoice_fiscal.py`
- `tests/test_goods_pos.py`

**Izmenjeni fajlovi:**
- `app/models/pos.py` — GOODS enum, goods_item_id, fiscal polja
- `app/models/tenant.py` — fiscal polja na ServiceLocation
- `app/models/ticket.py` — parts_cost property
- `app/models/__init__.py` — import goods modela
- `app/api/v1/__init__.py` — registracija goods blueprint-a
- `app/api/v1/pos.py` — search-items, fiscal_mode, X/Z reports
- `app/api/v1/tickets.py` — auto-receipt na collect, receive-and-use endpoint
- `app/services/pos_service.py` — GOODS podrška, fiscal_mode, idempotency, create_service_receipt, Decimal bugfix
- `app/services/goods_service.py` — _parse_date helper
- `app/frontend/tenant.py` — goods rute
- `app/templates/components/tenant_sidebar.html` — Magacin link
- `app/templates/tenant/pos/register.html` — potpuni redizajn

---

## v3.08a — Audit Fixes (2026-01-27)

Ispravke pronađene audit analizom v3.08 changelog-a i plana.

### Izmene

| # | Opis | Fajl |
|---|------|------|
| 1 | **Barcode normalizacija** — `.upper().strip()` pri kreiranju i ažuriranju GoodsItem | `goods_service.py` |
| 2 | **buyer_pib validacija** — regex `^\d{9}$` (srpski PIB = 9 cifara) | `pos_service.py` |
| 3 | **Provera zatvorene kase** — `issue_receipt()` odbija ako je sesija CLOSED | `pos_service.py` |
| 4 | **Zabrana duplog Z izveštaja** — provera postojećeg DailyReport pre generisanja → 409 | `pos.py` (API) |
| 5 | **Fiscal state-machine** — `FiscalStatus` enum + `FISCAL_TRANSITIONS` dict + `Receipt.transition_fiscal()` | `pos.py` (model) |
| 6 | **Fiscal retry stub** — `POST /pos/fiscal/retry` (max 3 pokušaja, pending→failed→pending) | `pos.py` (API) |
| 7 | **POS role permissions** — `PosRole` enum (CASHIER/MANAGER/ADMIN), `TenantUser.pos_role` kolona, void/refund zahteva MANAGER+ | `user.py`, `pos_service.py` |

### Novi testovi (9 testova, ukupno 43)

| Test klasa | Br. | Šta pokriva |
|------------|-----|-------------|
| `TestB2BBuyer` | +2 | Nevalidan PIB (slova, pogrešna dužina) |
| `TestClosedRegister` | 1 | Issue receipt na zatvorenu kasu → ValueError |
| `TestDuplicateZReport` | 1 | Dupli Z izveštaj → 409 |
| `TestFiscalStateMachine` | 3 | Validni prelazi, nevažeći prelaz, failed→pending retry |
| `TestBarcodeNormalization` | 2 | Normalizacija pri create/update |

### Izmenjeni fajlovi

- `app/models/user.py` — PosRole enum, pos_role kolona (nullable, None=sve dozvoljeno)
- `app/models/pos.py` — FiscalStatus enum, FISCAL_TRANSITIONS, transition_fiscal()
- `app/services/pos_service.py` — PIB validacija, closed register guard, _check_pos_permission()
- `app/services/goods_service.py` — barcode normalizacija
- `app/api/v1/pos.py` — duplicate Z guard, fiscal retry endpoint
- `tests/test_goods_pos.py` — 9 novih testova

### Migracija

- `pos_role` kolona na `TenantUser` (nullable Enum, bez default-a)

---

## v3.05 — POS/Credits/Billing Frontend + Test Suite (prethodno)

- POS kasa frontend (otvaranje/zatvaranje, kreiranje računa)
- Credits (stanje, kupovina paketa)
- Billing dashboard
- Ticket parts UI (dodavanje/uklanjanje delova)
- 64 testova (IDOR, billing, credits, POS, permissions, ticket parts, smoke)

---

## v3.04 — Billing & Subscription (prethodno)

- Promo → Trust → Active → Suspended lifecycle
- Feature flags per tenant
- Location scoping

---

## v3.03 — B2B/B2C Marketplace, Credits, POS modeli (prethodno)

- Credit sistem (kupovina paketa, dedukcija, refund)
- POS modeli (CashRegisterSession, Receipt, ReceiptItem, DailyReport)
- B2B marketplace sa anonimnim dobavljačima
- B2C marketplace modeli
- SparePartUsage tracking
- Bankovni parseri (Alta, AIK)
- IPS QR/PDF generacija