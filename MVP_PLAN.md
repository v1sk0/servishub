# ServisHub MVP - Plan za Komercijalizaciju

> **CILJ**: Minimalni proizvod spreman za komercijalizaciju - servisni nalozi, osnovni lager, dnevna prodaja.

---

## METADATA

| Ključ | Vrednost |
|-------|----------|
| **Projekat** | `c:\servishub` |
| **Tip** | MVP - Servis + Lager + POS + Audit |
| **Poslednja migracija** | `v328_add_color_mode_to_profile.py` |
| **Nove migracije** | v329 → v340 (12 migracija) |
| **Ključne tabele** | `stock_movement` (ledger), `location_stock` (cache) |
| **Arhivirani full plan** | `ARCHIVE_servishub_full_erp_plan.md` |

---

## ŠTA JE MVP

### ✅ UKLJUČENO U MVP:

1. **Servisni nalozi** (već postoji, treba fix/poboljšanja)
   - Kreiranje naloga sa podacima o kupcu i uređaju
   - Dodavanje rezervnih delova na nalog
   - Status workflow (Open → In Progress → Closed)
   - Garancija tracking
   - Štampa naloga

2. **Dobavljači i Prijem Robe** ⭐ NOVO
   - **Dobavljači** - dva tipa:
     - Pravno lice (firma) - PIB, matični broj, žiro račun
     - Fizičko lice - JMBG, broj LK, adresa
   - **Prijem od firme** - PurchaseInvoice (faktura/predračun)
   - **Otkup od fizičkog lica** - BuybackContract po zakonu RS

3. **Osnovni lager**
   - GoodsItem (roba za prodaju)
   - SparePart (rezervni delovi za servis)
   - Prijem robe (vezan za dobavljača)
   - Utrošak na nalogu
   - Pregled stanja

4. **StockMovement - Jedinstven ledger za zalihe** ⭐ OBAVEZNO
   - Svaka promena zaliha = novi red u tabeli (nikad UPDATE/DELETE)
   - Praćenje po lokaciji (location_id) - svaka lokacija ima svoj lager
   - Tipovi: INITIAL_BALANCE, RECEIVE, SALE, USE_TICKET, ADJUST, DAMAGE, RETURN
   - `LocationStock` = cache stanja po lokaciji
   - Audit: user_id, timestamp, action, reason
   - DB constraint: balance_after >= 0
   - **Inicijalizacija stanja:** Import iz Excel-a ili ručni unos

5. **Dnevna prodaja (POS)**
   - Prodaja robe sa stanja
   - Prodaja usluga (bez količine)
   - Dnevni izveštaj pazara
   - Fiskalizacija (ESIR integracija)

6. **ServiceItem (usluge)**
   - Usluge bez praćenja količine
   - Za POS i za naloge

7. **Transfer između lokacija** ⭐ NOVO
   - Radnik vidi stanje na drugim lokacijama svog tenanta
   - Kreira zahtev za transfer (TransferRequest)
   - Menadžer odredišne lokacije odobrava
   - TRANSFER_OUT/TRANSFER_IN movements

8. **Supplier Marketplace - B2B Delovi** ⭐ NOVO
   - Dobavljači uploaduju cenovnike (CSV/Excel)
   - Tenant vidi matchove dok kreira servisni nalog
   - Prikazano: samo ime artikla + cena + dugme "Poruči"
   - Tenant naruči → Dobavljač potvrdi → Krediti se skinu sa obe strane
   - Posle potvrde: full kontakt detalji za obe strane
   - Poruke/chat za dogovor oko preuzimanja
   - **Naplata:** 0.5 kredita kupac + 0.5 kredita dobavljač (konfiguriše se u Admin → Paketi)
   - Kompletan audit trail

### ❌ ODLOŽENO ZA KASNIJE (vidi ARCHIVE_servishub_full_erp_plan.md):

- GoodsIssue dokumenti
- InventoryTransfer između lokacija
- StockCount/Popis
- E-Fakture (SEF)
- PurchaseOrder
- Kompletno knjigovodstvo

---

## FAZA 1: BUGFIX - unit_cost [P0]

### Problem
`SparePartUsage` nema `unit_cost` polje → ne može se izračunati profit po nalogu.

### Rešenje

**Fajl:** `c:\servishub\app\models\inventory.py`

Dodati u `SparePartUsage`:
```python
unit_cost = db.Column(db.Numeric(10, 2))  # Nabavna cena
```

Izmeniti `to_dict()`:
```python
'unit_cost': float(self.unit_cost) if self.unit_cost else None,
'profit': float((self.unit_price - self.unit_cost) * self.quantity_used) if self.unit_price and self.unit_cost else None,
```

**Migracija:** `v329_add_unit_cost_to_usage.py`
```python
def upgrade():
    op.add_column('spare_part_usage', sa.Column('unit_cost', sa.Numeric(10, 2), nullable=True))

def downgrade():
    op.drop_column('spare_part_usage', 'unit_cost')
```

**Izmena pri dodavanju dela na nalog:**
Kada se kreira `SparePartUsage`, postaviti:
```python
unit_cost=spare_part.purchase_price
```

---

## FAZA 2: ServiceItem (Usluge) [P1]

### Zašto
Usluge poput "Dijagnostika", "Servis telefona", "Instalacija OS" se prodaju kroz POS ali nemaju količinu.

### Model

**Novi fajl:** `c:\servishub\app\models\service_item.py`

```python
"""ServiceItem - Usluge za POS bez praćenja količine."""

import enum
from datetime import datetime
from ..extensions import db


class ServiceCategory(enum.Enum):
    REPAIR = 'REPAIR'           # Popravke
    DIAGNOSTIC = 'DIAGNOSTIC'   # Dijagnostika
    SOFTWARE = 'SOFTWARE'       # Softverske usluge
    OTHER = 'OTHER'


class ServiceItem(db.Model):
    """Usluga za POS - nema quantity."""
    __tablename__ = 'service_item'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    code = db.Column(db.String(20), index=True)  # USL-001
    name = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text)

    category = db.Column(
        db.Enum(ServiceCategory),
        default=ServiceCategory.OTHER,
        nullable=False
    )

    price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    currency = db.Column(db.String(3), default='RSD')
    is_variable_price = db.Column(db.Boolean, default=False)

    tax_label = db.Column(db.String(1), default='A')  # PDV oznaka
    is_active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'code', name='uq_service_item_tenant_code'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'category': self.category.value if self.category else None,
            'price': float(self.price) if self.price else 0,
            'is_variable_price': self.is_variable_price,
            'tax_label': self.tax_label,
            'is_active': self.is_active,
            'item_type': 'SERVICE',
        }
```

**Migracija:** `v330_create_service_item.py`

---

## FAZA 3: Dobavljači i Prijem Robe [P1]

### Pregled

Dva toka prijema robe:
1. **Od pravnog lica (firma)** → Faktura/Predračun → `PurchaseInvoice`
2. **Od fizičkog lica** → Otkupni ugovor → `BuybackContract`

### 3.1 Proširenje Supplier Modela

Postojeći `Supplier` model je za B2B marketplace. Za MVP prijem dodajemo jednostavniji pristup.

**Fajl:** `c:\servishub\app\models\goods.py` (ili novi fajl)

```python
class SupplierType(enum.Enum):
    """Tip dobavljača."""
    COMPANY = 'COMPANY'       # Pravno lice (firma)
    INDIVIDUAL = 'INDIVIDUAL' # Fizičko lice


class SimpleSupplier(db.Model):
    """
    Jednostavan dobavljač za prijem robe.

    Razlika od Supplier modela (marketplace):
    - Ovaj je za interne ulazne fakture i otkup
    - Nema commission, ratings, listings
    """
    __tablename__ = 'simple_supplier'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Tip dobavljača
    supplier_type = db.Column(
        db.Enum(SupplierType),
        nullable=False,
        default=SupplierType.COMPANY
    )

    # Osnovni podaci (oba tipa)
    name = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(50))
    email = db.Column(db.String(100))
    address = db.Column(db.Text)
    city = db.Column(db.String(100))

    # Za COMPANY (pravno lice)
    company_name = db.Column(db.String(200))  # Pun pravni naziv
    pib = db.Column(db.String(20))            # PIB (9 cifara)
    maticni_broj = db.Column(db.String(20))   # Matični broj (8 cifara)
    bank_account = db.Column(db.String(50))   # Žiro račun

    # Za INDIVIDUAL (fizičko lice)
    jmbg = db.Column(db.String(13))           # JMBG (13 cifara)
    id_card_number = db.Column(db.String(20)) # Broj lične karte
    id_card_issued_by = db.Column(db.String(100))  # Izdata od (MUP)
    id_card_issue_date = db.Column(db.Date)   # Datum izdavanja

    # Status
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    __table_args__ = (
        db.Index('ix_simple_supplier_tenant_type', 'tenant_id', 'supplier_type'),
    )

    def to_dict(self):
        data = {
            'id': self.id,
            'supplier_type': self.supplier_type.value,
            'name': self.name,
            'phone': self.phone,
            'email': self.email,
            'address': self.address,
            'city': self.city,
            'is_active': self.is_active,
        }
        if self.supplier_type == SupplierType.COMPANY:
            data.update({
                'company_name': self.company_name,
                'pib': self.pib,
                'maticni_broj': self.maticni_broj,
                'bank_account': self.bank_account,
            })
        else:
            data.update({
                'jmbg': self.jmbg,
                'id_card_number': self.id_card_number,
            })
        return data
```

### 3.2 BuybackContract - Otkupni Ugovor (po zakonu RS)

**Fajl:** `c:\servishub\app\models\buyback.py`

```python
"""
BuybackContract - Otkupni ugovor za otkup od fizičkih lica.

Po zakonu RS otkupni ugovor mora sadržati:
- Podatke o kupcu (firma koja otkupljuje)
- Podatke o prodavcu (fizičko lice) - ime, JMBG, LK, adresa
- Opis robe/artikala
- Cenu
- Datum i mesto
- Potpise obe strane
"""

import enum
from datetime import datetime, date
from ..extensions import db


class BuybackStatus(enum.Enum):
    """Status otkupnog ugovora."""
    DRAFT = 'DRAFT'         # U pripremi
    SIGNED = 'SIGNED'       # Potpisan, roba primljena
    PAID = 'PAID'           # Isplaćeno prodavcu
    CANCELLED = 'CANCELLED' # Otkazano


class BuybackContract(db.Model):
    """Otkupni ugovor za fizička lica."""
    __tablename__ = 'buyback_contract'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    location_id = db.Column(
        db.Integer,
        db.ForeignKey('service_location.id', ondelete='SET NULL'),
        nullable=True
    )

    # Broj ugovora: OTK-2026-00001
    contract_number = db.Column(db.String(20), unique=True, nullable=False)
    contract_date = db.Column(db.Date, nullable=False, default=date.today)

    # Podaci o prodavcu (fizičko lice)
    seller_name = db.Column(db.String(200), nullable=False)
    seller_jmbg = db.Column(db.String(13), nullable=False)
    seller_id_card = db.Column(db.String(20), nullable=False)
    seller_id_issued_by = db.Column(db.String(100))
    seller_address = db.Column(db.Text, nullable=False)
    seller_city = db.Column(db.String(100))
    seller_phone = db.Column(db.String(50))

    # Opciono - veza ka SimpleSupplier za ponovne otkupe
    supplier_id = db.Column(db.Integer, db.ForeignKey('simple_supplier.id'))

    # Ukupan iznos
    total_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    currency = db.Column(db.String(3), default='RSD')

    # Način isplate
    payment_method = db.Column(db.String(20), default='CASH')  # CASH, BANK_TRANSFER
    bank_account = db.Column(db.String(50))  # Ako je BANK_TRANSFER

    # Status workflow
    status = db.Column(
        db.Enum(BuybackStatus),
        default=BuybackStatus.DRAFT,
        nullable=False,
        index=True
    )

    # Datumi promene statusa
    signed_at = db.Column(db.DateTime)
    paid_at = db.Column(db.DateTime)
    cancelled_at = db.Column(db.DateTime)
    cancel_reason = db.Column(db.String(255))

    # Audit
    created_by_id = db.Column(db.Integer, db.ForeignKey('tenant_user.id'), nullable=False)
    signed_by_id = db.Column(db.Integer, db.ForeignKey('tenant_user.id'))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Napomena
    notes = db.Column(db.Text)

    # Relacije
    items = db.relationship(
        'BuybackContractItem',
        backref='contract',
        cascade='all, delete-orphan',
        lazy='dynamic'
    )

    @staticmethod
    def generate_contract_number(tenant_id: int) -> str:
        """Generiše sledeći broj ugovora: OTK-2026-00001"""
        year = datetime.now().year
        prefix = f"OTK-{year}-"

        last = BuybackContract.query.filter(
            BuybackContract.tenant_id == tenant_id,
            BuybackContract.contract_number.like(f"{prefix}%")
        ).order_by(BuybackContract.contract_number.desc()).first()

        next_num = 1
        if last:
            try:
                next_num = int(last.contract_number.split('-')[-1]) + 1
            except ValueError:
                pass
        return f"{prefix}{next_num:05d}"

    def to_dict(self):
        return {
            'id': self.id,
            'contract_number': self.contract_number,
            'contract_date': self.contract_date.isoformat() if self.contract_date else None,
            'seller_name': self.seller_name,
            'seller_jmbg': self.seller_jmbg,
            'seller_id_card': self.seller_id_card,
            'seller_address': self.seller_address,
            'seller_phone': self.seller_phone,
            'total_amount': float(self.total_amount) if self.total_amount else 0,
            'currency': self.currency,
            'payment_method': self.payment_method,
            'status': self.status.value,
            'items_count': self.items.count(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class BuybackContractItem(db.Model):
    """Stavka otkupnog ugovora."""
    __tablename__ = 'buyback_contract_item'

    id = db.Column(db.Integer, primary_key=True)
    contract_id = db.Column(
        db.Integer,
        db.ForeignKey('buyback_contract.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Opis artikla
    item_description = db.Column(db.String(300), nullable=False)
    brand = db.Column(db.String(100))
    model = db.Column(db.String(100))

    # Identifikatori (opciono)
    imei = db.Column(db.String(20))
    serial_number = db.Column(db.String(50))

    # Količina i cena
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    line_total = db.Column(db.Numeric(12, 2), nullable=False)

    # Stanje artikla
    condition = db.Column(db.String(20), default='USED')  # NEW, USED, DAMAGED

    # Kategorija (za automatsko kreiranje SparePart/GoodsItem)
    item_type = db.Column(db.String(20), default='SPARE_PART')  # SPARE_PART, GOODS, PHONE
    part_category = db.Column(db.String(30))  # DISPLAY, BATTERY, etc.

    # Link ka kreiranom artiklu posle potpisivanja
    spare_part_id = db.Column(db.BigInteger, db.ForeignKey('spare_part.id'))
    goods_item_id = db.Column(db.Integer, db.ForeignKey('goods_item.id'))
    phone_listing_id = db.Column(db.BigInteger, db.ForeignKey('phone_listing.id'))

    def to_dict(self):
        return {
            'id': self.id,
            'item_description': self.item_description,
            'brand': self.brand,
            'model': self.model,
            'imei': self.imei,
            'serial_number': self.serial_number,
            'quantity': self.quantity,
            'unit_price': float(self.unit_price) if self.unit_price else 0,
            'line_total': float(self.line_total) if self.line_total else 0,
            'condition': self.condition,
            'item_type': self.item_type,
        }
```

### 3.3 Migracije

**Migracija v331:** `v331_create_simple_supplier.py`
```python
def upgrade():
    op.create_table(
        'simple_supplier',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenant.id', ondelete='CASCADE'), nullable=False),
        sa.Column('supplier_type', sa.String(20), nullable=False, server_default='COMPANY'),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('phone', sa.String(50)),
        sa.Column('email', sa.String(100)),
        sa.Column('address', sa.Text()),
        sa.Column('city', sa.String(100)),
        # Company fields
        sa.Column('company_name', sa.String(200)),
        sa.Column('pib', sa.String(20)),
        sa.Column('maticni_broj', sa.String(20)),
        sa.Column('bank_account', sa.String(50)),
        # Individual fields
        sa.Column('jmbg', sa.String(13)),
        sa.Column('id_card_number', sa.String(20)),
        sa.Column('id_card_issued_by', sa.String(100)),
        sa.Column('id_card_issue_date', sa.Date()),
        # Status
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('notes', sa.Text()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime()),
    )
    op.create_index('ix_simple_supplier_tenant_type', 'simple_supplier', ['tenant_id', 'supplier_type'])
```

**Migracija v332:** `v332_create_buyback_contract.py`
```python
def upgrade():
    op.create_table(
        'buyback_contract',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenant.id', ondelete='CASCADE'), nullable=False),
        sa.Column('location_id', sa.Integer(), sa.ForeignKey('service_location.id', ondelete='SET NULL')),
        sa.Column('contract_number', sa.String(20), unique=True, nullable=False),
        sa.Column('contract_date', sa.Date(), nullable=False),
        # Seller data
        sa.Column('seller_name', sa.String(200), nullable=False),
        sa.Column('seller_jmbg', sa.String(13), nullable=False),
        sa.Column('seller_id_card', sa.String(20), nullable=False),
        sa.Column('seller_id_issued_by', sa.String(100)),
        sa.Column('seller_address', sa.Text(), nullable=False),
        sa.Column('seller_city', sa.String(100)),
        sa.Column('seller_phone', sa.String(50)),
        sa.Column('supplier_id', sa.Integer(), sa.ForeignKey('simple_supplier.id')),
        # Amount
        sa.Column('total_amount', sa.Numeric(12, 2), server_default='0'),
        sa.Column('currency', sa.String(3), server_default='RSD'),
        sa.Column('payment_method', sa.String(20), server_default='CASH'),
        sa.Column('bank_account', sa.String(50)),
        # Status
        sa.Column('status', sa.String(20), server_default='DRAFT'),
        sa.Column('signed_at', sa.DateTime()),
        sa.Column('paid_at', sa.DateTime()),
        sa.Column('cancelled_at', sa.DateTime()),
        sa.Column('cancel_reason', sa.String(255)),
        # Audit
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('tenant_user.id'), nullable=False),
        sa.Column('signed_by_id', sa.Integer(), sa.ForeignKey('tenant_user.id')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('notes', sa.Text()),
    )

    op.create_table(
        'buyback_contract_item',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('contract_id', sa.Integer(), sa.ForeignKey('buyback_contract.id', ondelete='CASCADE'), nullable=False),
        sa.Column('item_description', sa.String(300), nullable=False),
        sa.Column('brand', sa.String(100)),
        sa.Column('model', sa.String(100)),
        sa.Column('imei', sa.String(20)),
        sa.Column('serial_number', sa.String(50)),
        sa.Column('quantity', sa.Integer(), server_default='1'),
        sa.Column('unit_price', sa.Numeric(10, 2), nullable=False),
        sa.Column('line_total', sa.Numeric(12, 2), nullable=False),
        sa.Column('condition', sa.String(20), server_default='USED'),
        sa.Column('item_type', sa.String(20), server_default='SPARE_PART'),
        sa.Column('part_category', sa.String(30)),
        sa.Column('spare_part_id', sa.BigInteger(), sa.ForeignKey('spare_part.id')),
        sa.Column('goods_item_id', sa.Integer(), sa.ForeignKey('goods_item.id')),
        sa.Column('phone_listing_id', sa.BigInteger(), sa.ForeignKey('phone_listing.id')),
    )
```

### 3.4 Otkupni Ugovor - Workflow

```
┌─────────┐     ┌─────────┐     ┌─────────┐
│  DRAFT  │────►│ SIGNED  │────►│  PAID   │
└─────────┘     └─────────┘     └─────────┘
     │
     └──────────►┌───────────┐
                 │ CANCELLED │
                 └───────────┘
```

**DRAFT → SIGNED:**
1. Korisnik popuni podatke o prodavcu i stavke
2. Štampa ugovor u 2 primerka (PDF)
3. Obe strane potpišu
4. Klik "Potpiši" → status = SIGNED
5. **Automatski se kreiraju artikli na stanju:**
   - `item_type='SPARE_PART'` → novi `SparePart`
   - `item_type='GOODS'` → novi `GoodsItem`
   - `item_type='PHONE'` → novi `PhoneListing`

**SIGNED → PAID:**
1. Isplata prodavcu (gotovina ili transfer)
2. Klik "Označi kao isplaćeno" → status = PAID

### 3.5 Modal za Otkup - Obavezna Polja (Zakon RS)

```html
<!-- Podaci o prodavcu -->
<input name="seller_name" required placeholder="Ime i prezime">
<input name="seller_jmbg" required pattern="[0-9]{13}" placeholder="JMBG (13 cifara)">
<input name="seller_id_card" required placeholder="Broj lične karte">
<input name="seller_id_issued_by" placeholder="Izdata od (MUP...)">
<input name="seller_address" required placeholder="Adresa prebivališta">
<input name="seller_city" placeholder="Grad">
<input name="seller_phone" placeholder="Telefon">

<!-- Stavke -->
<table id="items">
  <tr>
    <td><input name="item_description" required></td>
    <td><input name="brand"></td>
    <td><input name="model"></td>
    <td><input name="imei"></td>
    <td><input name="quantity" type="number" value="1"></td>
    <td><input name="unit_price" type="number" required></td>
  </tr>
</table>

<!-- Ukupno i način isplate -->
<div>Ukupno: <span id="total">0</span> RSD</div>
<select name="payment_method">
  <option value="CASH">Gotovina</option>
  <option value="BANK_TRANSFER">Prenos na račun</option>
</select>
```

### 3.6 PDF Otkupnog Ugovora

Template mora sadržati:

```
                    UGOVOR O OTKUPU POLOVNE ROBE
                         Br: OTK-2026-00001

Zaključen dana ________ u _________ između:

1. KUPAC:
   [Naziv firme iz tenant settings]
   PIB: [PIB]
   Adresa: [Adresa]

2. PRODAVAC:
   Ime i prezime: ________________
   JMBG: ________________
   Br. lične karte: ________ izdata od ________
   Adresa: ________________

PREDMET UGOVORA:
┌────┬──────────────┬───────┬────────┬─────┬──────────┐
│ Rb │ Opis artikla │ Brand │ Model  │ Kol.│ Cena     │
├────┼──────────────┼───────┼────────┼─────┼──────────┤
│ 1  │              │       │        │     │          │
└────┴──────────────┴───────┴────────┴─────┴──────────┘

UKUPNO: _____________ RSD

USLOVI:
1. Prodavac izjavljuje da je isključivi vlasnik navedene robe.
2. Prodavac garantuje da roba nije predmet spora ili zaloge.
3. Kupac isplaćuje iznos odmah po potpisivanju / na račun.
4. Roba se predaje u viđenom stanju.

Potpisi:
_________________          _________________
    Za kupca                   Prodavac
```

---

## FAZA 4: Povezivanje PurchaseInvoice sa Dobavljačem [P1]

### Problem
Postojeći `PurchaseInvoice` ima samo `supplier_name` i `supplier_pib` kao stringove.
Treba povezati sa `SimpleSupplier` za konzistentnost.

### Rešenje
Dodati `supplier_id` FK u `PurchaseInvoice`:

```python
# U PurchaseInvoice modelu dodati:
supplier_id = db.Column(db.Integer, db.ForeignKey('simple_supplier.id'), nullable=True)
```

**Migracija v333:** `v333_link_invoice_supplier.py`

---

## FAZA 5: StockMovement - Jedinstven Ledger [P0] ⭐

### Zašto je obavezno
- **Jedini izvor istine** za stanje zaliha
- Svaka promena = novi red (nikad UPDATE/DELETE na movement-u)
- `LocationStock.quantity` je CACHE (stanje po lokaciji)
- Potpun audit trail: ko, kad, šta, zašto, koliko
- **INITIAL_BALANCE** za početno stanje

### Model

**Fajl:** `c:\servishub\app\models\stock_movement.py`

```python
"""
StockMovement - Jedinstven ledger za sve promene zaliha.

PRAVILO: Svaka promena zaliha MORA proći kroz ovaj model.
Nikad direktno menjati quantity na LocationStock!
"""

import enum
from datetime import datetime
from decimal import Decimal
from ..extensions import db


class MovementType(enum.Enum):
    """Tip promene zaliha."""
    INITIAL_BALANCE = 'INITIAL_BALANCE'  # Početno stanje (import, ručni unos)
    RECEIVE = 'RECEIVE'           # Prijem robe (faktura, otkup)
    SALE = 'SALE'                 # Prodaja kroz POS
    USE_TICKET = 'USE_TICKET'     # Utrošak na servisnom nalogu
    USE_INTERNAL = 'USE_INTERNAL' # Interni utrošak (potrošni materijal)
    RETURN = 'RETURN'             # Povrat od kupca
    ADJUST = 'ADJUST'             # Korekcija (inventura) - samo admin
    DAMAGE = 'DAMAGE'             # Oštećenje/otpis
    TRANSFER_OUT = 'TRANSFER_OUT' # Izlaz za transfer (između lokacija)
    TRANSFER_IN = 'TRANSFER_IN'   # Ulaz od transfera


class StockMovement(db.Model):
    """
    Ledger tabela - svaka promena zaliha je novi red.

    NIKAD ne raditi UPDATE ili DELETE na ovoj tabeli!
    Za ispravku: novi red sa suprotnim predznakom + reason.
    """
    __tablename__ = 'stock_movement'

    id = db.Column(db.BigInteger, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    location_id = db.Column(
        db.Integer,
        db.ForeignKey('service_location.id', ondelete='RESTRICT'),
        nullable=False,
        index=True
    )

    # Šta se menja (jedno od dva) - RESTRICT jer ne možemo brisati artikal sa istorijom
    goods_item_id = db.Column(
        db.Integer,
        db.ForeignKey('goods_item.id', ondelete='RESTRICT'),
        nullable=True,
        index=True
    )
    spare_part_id = db.Column(
        db.BigInteger,
        db.ForeignKey('spare_part.id', ondelete='RESTRICT'),
        nullable=True,
        index=True
    )

    # Za transfere - odredišna lokacija
    target_location_id = db.Column(
        db.Integer,
        db.ForeignKey('service_location.id', ondelete='SET NULL'),
        nullable=True
    )

    # Tip i količina
    movement_type = db.Column(
        db.Enum(MovementType),
        nullable=False,
        index=True
    )
    quantity = db.Column(db.Integer, nullable=False)  # + ili -

    # Stanje PRE i POSLE (za validaciju)
    balance_before = db.Column(db.Integer, nullable=False)
    balance_after = db.Column(db.Integer, nullable=False)

    # Cena u trenutku pokreta (za FIFO/kalkulacije)
    unit_cost = db.Column(db.Numeric(10, 2))
    unit_price = db.Column(db.Numeric(10, 2))  # Prodajna cena (za SALE)

    # Referenca na dokument
    reference_type = db.Column(db.String(30))  # 'purchase_invoice', 'buyback', 'pos_receipt', 'ticket', 'adjustment'
    reference_id = db.Column(db.BigInteger)
    reference_number = db.Column(db.String(50))  # Broj dokumenta za prikaz

    # Audit - OBAVEZNO
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant_user.id', ondelete='SET NULL'),
        nullable=False
    )
    reason = db.Column(db.String(255))  # Obavezno za ADJUST, DAMAGE
    notes = db.Column(db.Text)

    # Timestamp - nikad se ne menja
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True
    )

    # Relacije
    location = db.relationship('ServiceLocation', foreign_keys=[location_id])
    target_location = db.relationship('ServiceLocation', foreign_keys=[target_location_id])
    goods_item = db.relationship('GoodsItem', backref='movements')
    spare_part = db.relationship('SparePart', backref='movements')
    user = db.relationship('TenantUser')

    # DB Constraints
    __table_args__ = (
        # Mora biti ili goods_item_id ili spare_part_id
        db.CheckConstraint(
            '(goods_item_id IS NOT NULL AND spare_part_id IS NULL) OR '
            '(goods_item_id IS NULL AND spare_part_id IS NOT NULL)',
            name='ck_movement_one_item'
        ),
        # quantity != 0
        db.CheckConstraint('quantity != 0', name='ck_movement_quantity_nonzero'),
        # balance_after >= 0 (ne može u minus)
        db.CheckConstraint('balance_after >= 0', name='ck_movement_balance_positive'),
        # Indeksi za brze upite
        db.Index('ix_movement_location_created', 'location_id', 'created_at'),
        db.Index('ix_movement_goods_created', 'goods_item_id', 'created_at'),
        db.Index('ix_movement_spare_created', 'spare_part_id', 'created_at'),
        db.Index('ix_movement_reference', 'reference_type', 'reference_id'),
    )

    def __repr__(self):
        item = f"goods:{self.goods_item_id}" if self.goods_item_id else f"part:{self.spare_part_id}"
        return f'<StockMovement {self.id}: {self.movement_type.value} {self.quantity:+d} {item}>'

    def to_dict(self):
        return {
            'id': self.id,
            'movement_type': self.movement_type.value,
            'quantity': self.quantity,
            'balance_before': self.balance_before,
            'balance_after': self.balance_after,
            'unit_cost': float(self.unit_cost) if self.unit_cost else None,
            'reference_type': self.reference_type,
            'reference_number': self.reference_number,
            'reason': self.reason,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat(),
        }


# ============================================
# HELPER FUNKCIJE ZA KREIRANJE MOVEMENT-A
# ============================================

def create_stock_movement(
    tenant_id: int,
    location_id: int,
    user_id: int,
    movement_type: MovementType,
    quantity: int,
    goods_item_id: int = None,
    spare_part_id: int = None,
    unit_cost: Decimal = None,
    unit_price: Decimal = None,
    reference_type: str = None,
    reference_id: int = None,
    reference_number: str = None,
    reason: str = None,
    notes: str = None,
    target_location_id: int = None,  # Za TRANSFER
) -> StockMovement:
    """
    Kreira StockMovement i ažurira cache u LocationStock.

    MORA se koristiti unutar transakcije sa SELECT...FOR UPDATE!

    Args:
        tenant_id: ID tenanta
        location_id: ID lokacije (OBAVEZNO)
        user_id: ID korisnika koji radi akciju
        movement_type: Tip promene (RECEIVE, SALE, etc.)
        quantity: Količina (+ za ulaz, - za izlaz)
        goods_item_id: ID robe (XOR spare_part_id)
        spare_part_id: ID dela (XOR goods_item_id)
        unit_cost: Nabavna cena
        unit_price: Prodajna cena
        reference_type: Tip dokumenta
        reference_id: ID dokumenta
        reference_number: Broj dokumenta (za prikaz)
        reason: Razlog (obavezno za ADJUST, DAMAGE, INITIAL_BALANCE)
        notes: Dodatne napomene
        target_location_id: Odredišna lokacija (za TRANSFER)

    Returns:
        Kreirani StockMovement

    Raises:
        ValueError: Ako nema dovoljno stanja za izlaz
    """

    # Validacija
    if not location_id:
        raise ValueError("location_id je obavezan")
    if not goods_item_id and not spare_part_id:
        raise ValueError("Mora biti goods_item_id ili spare_part_id")
    if goods_item_id and spare_part_id:
        raise ValueError("Ne može biti oba: goods_item_id i spare_part_id")
    if movement_type in (MovementType.ADJUST, MovementType.DAMAGE, MovementType.INITIAL_BALANCE) and not reason:
        raise ValueError(f"{movement_type.value} zahteva reason")

    # Dohvati ili kreiraj LocationStock sa LOCK-om
    if goods_item_id:
        loc_stock = db.session.query(LocationStock).with_for_update().filter_by(
            location_id=location_id,
            goods_item_id=goods_item_id
        ).first()
        if not loc_stock:
            loc_stock = LocationStock(
                location_id=location_id,
                goods_item_id=goods_item_id,
                quantity=0
            )
            db.session.add(loc_stock)
            db.session.flush()
    else:
        loc_stock = db.session.query(LocationStock).with_for_update().filter_by(
            location_id=location_id,
            spare_part_id=spare_part_id
        ).first()
        if not loc_stock:
            loc_stock = LocationStock(
                location_id=location_id,
                spare_part_id=spare_part_id,
                quantity=0
            )
            db.session.add(loc_stock)
            db.session.flush()

    balance_before = loc_stock.quantity
    balance_after = balance_before + quantity

    # Validacija: ne može u minus
    if balance_after < 0:
        raise ValueError(
            f"Nedovoljno stanja na lokaciji: {balance_before} + ({quantity}) = {balance_after}"
        )

    # Kreiraj movement
    movement = StockMovement(
        tenant_id=tenant_id,
        location_id=location_id,
        target_location_id=target_location_id,
        goods_item_id=goods_item_id,
        spare_part_id=spare_part_id,
        movement_type=movement_type,
        quantity=quantity,
        balance_before=balance_before,
        balance_after=balance_after,
        unit_cost=unit_cost,
        unit_price=unit_price,
        reference_type=reference_type,
        reference_id=reference_id,
        reference_number=reference_number,
        user_id=user_id,
        reason=reason,
        notes=notes,
    )
    db.session.add(movement)

    # Ažuriraj cache u LocationStock
    loc_stock.quantity = balance_after
    loc_stock.last_movement_id = movement.id

    return movement


class LocationStock(db.Model):
    """
    Cache stanja artikla po lokaciji.

    Pravo stanje se računa iz StockMovement, ovo je samo cache za brze upite.
    """
    __tablename__ = 'location_stock'

    id = db.Column(db.BigInteger, primary_key=True)
    location_id = db.Column(
        db.Integer,
        db.ForeignKey('service_location.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Šta (jedno od dva)
    goods_item_id = db.Column(db.Integer, db.ForeignKey('goods_item.id', ondelete='CASCADE'))
    spare_part_id = db.Column(db.BigInteger, db.ForeignKey('spare_part.id', ondelete='CASCADE'))

    # Cache stanja
    quantity = db.Column(db.Integer, default=0, nullable=False)

    # Poslednja promena
    last_movement_id = db.Column(db.BigInteger)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    __table_args__ = (
        db.CheckConstraint(
            '(goods_item_id IS NOT NULL AND spare_part_id IS NULL) OR '
            '(goods_item_id IS NULL AND spare_part_id IS NOT NULL)',
            name='ck_loc_stock_one_item'
        ),
        db.UniqueConstraint('location_id', 'goods_item_id', name='uq_loc_stock_goods'),
        db.UniqueConstraint('location_id', 'spare_part_id', name='uq_loc_stock_spare'),
    )


def get_stock_card(
    goods_item_id: int = None,
    spare_part_id: int = None,
    from_date: datetime = None,
    to_date: datetime = None
) -> list:
    """
    Vraća lager karticu (stock card) za artikal.

    Prikazuje sve promene sa running balance.
    """
    query = StockMovement.query

    if goods_item_id:
        query = query.filter(StockMovement.goods_item_id == goods_item_id)
    elif spare_part_id:
        query = query.filter(StockMovement.spare_part_id == spare_part_id)
    else:
        raise ValueError("Mora biti goods_item_id ili spare_part_id")

    if from_date:
        query = query.filter(StockMovement.created_at >= from_date)
    if to_date:
        query = query.filter(StockMovement.created_at <= to_date)

    return query.order_by(StockMovement.created_at.asc()).all()


def validate_stock_balance(goods_item_id: int = None, spare_part_id: int = None) -> bool:
    """
    Validira da cache na artiklu odgovara poslednjoj vrednosti iz ledger-a.

    Returns:
        True ako je validno, False ako ima razlike
    """
    from .goods import GoodsItem
    from .inventory import SparePart
    from sqlalchemy import func

    if goods_item_id:
        item = GoodsItem.query.get(goods_item_id)
        if not item:
            return False
        # Uzmi poslednji movement
        last = StockMovement.query.filter(
            StockMovement.goods_item_id == goods_item_id
        ).order_by(StockMovement.created_at.desc()).first()

        expected = last.balance_after if last else 0
        return item.current_stock == expected

    elif spare_part_id:
        item = SparePart.query.get(spare_part_id)
        if not item:
            return False
        last = StockMovement.query.filter(
            StockMovement.spare_part_id == spare_part_id
        ).order_by(StockMovement.created_at.desc()).first()

        expected = last.balance_after if last else 0
        return item.quantity == expected

    return False
```

### Migracija v334: `v334_create_stock_movement.py`

```python
def upgrade():
    # LocationStock - cache stanja po lokaciji
    op.create_table(
        'location_stock',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('location_id', sa.Integer(), sa.ForeignKey('service_location.id', ondelete='CASCADE'), nullable=False),
        sa.Column('goods_item_id', sa.Integer(), sa.ForeignKey('goods_item.id', ondelete='CASCADE')),
        sa.Column('spare_part_id', sa.BigInteger(), sa.ForeignKey('spare_part.id', ondelete='CASCADE')),
        sa.Column('quantity', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last_movement_id', sa.BigInteger()),
        sa.Column('updated_at', sa.DateTime()),
    )
    op.create_check_constraint(
        'ck_loc_stock_one_item', 'location_stock',
        '(goods_item_id IS NOT NULL AND spare_part_id IS NULL) OR '
        '(goods_item_id IS NULL AND spare_part_id IS NOT NULL)'
    )
    op.create_unique_constraint('uq_loc_stock_goods', 'location_stock', ['location_id', 'goods_item_id'])
    op.create_unique_constraint('uq_loc_stock_spare', 'location_stock', ['location_id', 'spare_part_id'])
    op.create_index('ix_loc_stock_location', 'location_stock', ['location_id'])

    # StockMovement - ledger
    op.create_table(
        'stock_movement',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenant.id', ondelete='CASCADE'), nullable=False),
        sa.Column('location_id', sa.Integer(), sa.ForeignKey('service_location.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('target_location_id', sa.Integer(), sa.ForeignKey('service_location.id', ondelete='SET NULL')),
        # Item references
        sa.Column('goods_item_id', sa.Integer(), sa.ForeignKey('goods_item.id', ondelete='RESTRICT')),
        sa.Column('spare_part_id', sa.BigInteger(), sa.ForeignKey('spare_part.id', ondelete='RESTRICT')),
        # Movement data
        sa.Column('movement_type', sa.String(20), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('balance_before', sa.Integer(), nullable=False),
        sa.Column('balance_after', sa.Integer(), nullable=False),
        # Prices
        sa.Column('unit_cost', sa.Numeric(10, 2)),
        sa.Column('unit_price', sa.Numeric(10, 2)),
        # Reference
        sa.Column('reference_type', sa.String(30)),
        sa.Column('reference_id', sa.BigInteger()),
        sa.Column('reference_number', sa.String(50)),
        # Audit
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('tenant_user.id', ondelete='SET NULL'), nullable=False),
        sa.Column('reason', sa.String(255)),
        sa.Column('notes', sa.Text()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # Constraints
    op.create_check_constraint(
        'ck_movement_one_item', 'stock_movement',
        '(goods_item_id IS NOT NULL AND spare_part_id IS NULL) OR '
        '(goods_item_id IS NULL AND spare_part_id IS NOT NULL)'
    )
    op.create_check_constraint(
        'ck_movement_quantity_nonzero', 'stock_movement',
        'quantity != 0'
    )
    op.create_check_constraint(
        'ck_movement_balance_positive', 'stock_movement',
        'balance_after >= 0'
    )

    # Indexes
    op.create_index('ix_stock_movement_tenant', 'stock_movement', ['tenant_id'])
    op.create_index('ix_stock_movement_location', 'stock_movement', ['location_id'])
    op.create_index('ix_stock_movement_goods', 'stock_movement', ['goods_item_id'])
    op.create_index('ix_stock_movement_spare', 'stock_movement', ['spare_part_id'])
    op.create_index('ix_stock_movement_type', 'stock_movement', ['movement_type'])
    op.create_index('ix_stock_movement_created', 'stock_movement', ['created_at'])
    op.create_index('ix_stock_movement_reference', 'stock_movement', ['reference_type', 'reference_id'])


def downgrade():
    op.drop_table('stock_movement')
    op.drop_table('location_stock')
```

---

### Inicijalizacija Početnog Stanja

**1. Import iz Excel-a:**

```python
@bp.route('/stock/import', methods=['POST'])
@login_required
@admin_required
def import_initial_stock():
    """
    Import početnog stanja iz Excel-a.

    Excel format:
    | barcode | name | location_name | quantity | purchase_price |
    |---------|------|---------------|----------|----------------|
    | 123456  | Baterija iPhone 12 | Glavni servis | 10 | 1500 |
    """
    import pandas as pd
    from app.models.stock_movement import create_stock_movement, MovementType

    file = request.files['file']
    df = pd.read_excel(file)

    errors = []
    imported = 0

    with db.session.begin_nested():
        for idx, row in df.iterrows():
            try:
                # Pronađi artikal po barkodu
                item = GoodsItem.query.filter_by(
                    tenant_id=current_user.tenant_id,
                    barcode=row['barcode']
                ).first()

                if not item:
                    # Kreiraj novi artikal
                    item = GoodsItem(
                        tenant_id=current_user.tenant_id,
                        name=row['name'],
                        barcode=row['barcode'],
                        purchase_price=row.get('purchase_price', 0),
                    )
                    db.session.add(item)
                    db.session.flush()

                # Pronađi lokaciju
                location = ServiceLocation.query.filter_by(
                    tenant_id=current_user.tenant_id,
                    name=row['location_name']
                ).first()

                if not location:
                    errors.append(f"Red {idx+2}: Lokacija '{row['location_name']}' ne postoji")
                    continue

                # Kreiraj INITIAL_BALANCE movement
                create_stock_movement(
                    tenant_id=current_user.tenant_id,
                    location_id=location.id,
                    user_id=current_user.id,
                    movement_type=MovementType.INITIAL_BALANCE,
                    quantity=int(row['quantity']),
                    goods_item_id=item.id,
                    unit_cost=Decimal(str(row.get('purchase_price', 0))),
                    reason=f"Import iz Excel-a: {file.filename}",
                )
                imported += 1

            except Exception as e:
                errors.append(f"Red {idx+2}: {str(e)}")

    if errors:
        db.session.rollback()
        return jsonify({'success': False, 'errors': errors}), 400

    db.session.commit()
    return jsonify({
        'success': True,
        'imported': imported,
        'message': f'Uspešno importovano {imported} artikala'
    })
```

**2. Ručni unos početnog stanja:**

```python
@bp.route('/stock/<item_type>/<int:item_id>/initial', methods=['POST'])
@login_required
@admin_required
def set_initial_stock(item_type, item_id):
    """Ručni unos početnog stanja za artikal na lokaciji."""
    data = request.get_json()
    location_id = data['location_id']
    quantity = data['quantity']
    purchase_price = data.get('purchase_price')

    try:
        with db.session.begin_nested():
            create_stock_movement(
                tenant_id=current_user.tenant_id,
                location_id=location_id,
                user_id=current_user.id,
                movement_type=MovementType.INITIAL_BALANCE,
                quantity=quantity,
                goods_item_id=item_id if item_type == 'goods' else None,
                spare_part_id=item_id if item_type == 'spare' else None,
                unit_cost=Decimal(str(purchase_price)) if purchase_price else None,
                reason=f"Početno stanje - ručni unos",
            )
        db.session.commit()
        return jsonify({'success': True})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
```

### Korišćenje u kodu

**Prijem robe (umesto direktne promene):**
```python
# POGREŠNO - direktna promena
# item.current_stock += quantity

# ISPRAVNO - kroz StockMovement
from app.models.stock_movement import create_stock_movement, MovementType

with db.session.begin():
    movement = create_stock_movement(
        tenant_id=current_tenant.id,
        user_id=current_user.id,
        movement_type=MovementType.RECEIVE,
        quantity=10,  # + = ulaz
        goods_item_id=item.id,
        unit_cost=Decimal('1500.00'),
        reference_type='purchase_invoice',
        reference_id=invoice.id,
        reference_number=invoice.invoice_number,
    )
```

**Prodaja kroz POS:**
```python
with db.session.begin():
    movement = create_stock_movement(
        tenant_id=current_tenant.id,
        user_id=current_user.id,
        movement_type=MovementType.SALE,
        quantity=-1,  # - = izlaz
        goods_item_id=item.id,
        unit_cost=item.purchase_price,
        unit_price=Decimal('2000.00'),
        reference_type='pos_receipt',
        reference_id=receipt.id,
        reference_number=receipt.receipt_number,
    )
```

**Korekcija (samo admin):**
```python
with db.session.begin():
    movement = create_stock_movement(
        tenant_id=current_tenant.id,
        user_id=current_user.id,
        movement_type=MovementType.ADJUST,
        quantity=-3,  # Pronađen manjak od 3 komada
        goods_item_id=item.id,
        reason="Inventura 2026-02-06: pronađen manjak",  # OBAVEZNO
    )
```

---

## FAZA 6: Lager Endpoints sa StockMovement [P1]

### Sve promene idu kroz StockMovement!
Nikad direktno menjati `quantity` na LocationStock - samo kroz `create_stock_movement()`.

### 6.1 Prijem robe (RECEIVE)

```python
@bp.route('/goods/<int:item_id>/receive', methods=['POST'])
@login_required
def receive_goods(item_id):
    """Prijem robe na lokaciju - kreira StockMovement."""
    from app.models.stock_movement import create_stock_movement, MovementType, LocationStock

    data = request.get_json()
    location_id = data['location_id']  # OBAVEZNO - na koju lokaciju
    quantity = data['quantity']
    purchase_price = data.get('purchase_price')
    reference_type = data.get('reference_type', 'manual')
    reference_id = data.get('reference_id')
    reference_number = data.get('reference_number')

    item = GoodsItem.query.get_or_404(item_id)

    try:
        with db.session.begin_nested():
            movement = create_stock_movement(
                tenant_id=current_user.tenant_id,
                location_id=location_id,
                user_id=current_user.id,
                movement_type=MovementType.RECEIVE,
                quantity=quantity,  # + = ulaz
                goods_item_id=item.id,
                unit_cost=Decimal(str(purchase_price)) if purchase_price else item.purchase_price,
                reference_type=reference_type,
                reference_id=reference_id,
                reference_number=reference_number,
            )
        db.session.commit()

        # Dohvati novo stanje na toj lokaciji
        loc_stock = LocationStock.query.filter_by(
            location_id=location_id, goods_item_id=item.id
        ).first()

        return jsonify({
            'success': True,
            'movement_id': movement.id,
            'location_stock': loc_stock.quantity if loc_stock else 0
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
```

### 6.2 Prodaja kroz POS (SALE)

```python
@bp.route('/pos/sell', methods=['POST'])
@login_required
def pos_sell():
    """Prodaja kroz kasu - kreira PosReceipt + StockMovement za svaku stavku."""
    from app.models.stock_movement import create_stock_movement, MovementType
    from app.models.pos import PosReceipt, PosReceiptItem

    data = request.get_json()
    location_id = data.get('location_id', current_user.location_id)  # Sa koje lokacije
    items = data['items']  # [{type: 'goods', id: 1, qty: 2, price: 1500}, {type: 'service', id: 5, price: 500}]
    payment_method = data.get('payment_method', 'CASH')

    try:
        with db.session.begin_nested():
            # 1. Kreiraj receipt
            receipt = PosReceipt(
                tenant_id=current_user.tenant_id,
                location_id=location_id,
                receipt_number=PosReceipt.generate_number(current_user.tenant_id),
                payment_method=payment_method,
                created_by_id=current_user.id,
            )
            db.session.add(receipt)
            db.session.flush()

            total = Decimal('0')

            for item_data in items:
                if item_data['type'] == 'goods':
                    goods = GoodsItem.query.get(item_data['id'])
                    qty = item_data.get('qty', 1)
                    price = Decimal(str(item_data.get('price', goods.selling_price)))

                    # Kreiraj StockMovement (validira stanje!)
                    create_stock_movement(
                        tenant_id=current_user.tenant_id,
                        location_id=location_id,  # Sa ove lokacije
                        user_id=current_user.id,
                        movement_type=MovementType.SALE,
                        quantity=-qty,  # - = izlaz
                        goods_item_id=goods.id,
                        unit_cost=goods.purchase_price,
                        unit_price=price,
                        reference_type='pos_receipt',
                        reference_id=receipt.id,
                        reference_number=receipt.receipt_number,
                    )

                    # Dodaj stavku
                    line = PosReceiptItem(
                        receipt_id=receipt.id,
                        goods_item_id=goods.id,
                        item_name=goods.name,
                        quantity=qty,
                        unit_price=price,
                        tax_label=goods.tax_label,
                        line_total=price * qty,
                    )
                    db.session.add(line)
                    total += price * qty

                elif item_data['type'] == 'service':
                    service = ServiceItem.query.get(item_data['id'])
                    price = Decimal(str(item_data.get('price', service.price)))

                    # Usluga - nema StockMovement!
                    line = PosReceiptItem(
                        receipt_id=receipt.id,
                        service_item_id=service.id,
                        item_name=service.name,
                        quantity=1,
                        unit_price=price,
                        tax_label=service.tax_label,
                        line_total=price,
                    )
                    db.session.add(line)
                    total += price

            receipt.total_amount = total

        db.session.commit()

        return jsonify({
            'success': True,
            'receipt_id': receipt.id,
            'receipt_number': receipt.receipt_number,
            'total': float(total),
        })

    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400
```

### 6.3 Korekcija stanja (ADJUST) - samo Admin

```python
@bp.route('/stock/<item_type>/<int:item_id>/adjust', methods=['POST'])
@login_required
@admin_required
def adjust_stock(item_type, item_id):
    """Korekcija stanja na lokaciji (inventura) - zahteva reason!"""
    from app.models.stock_movement import create_stock_movement, MovementType

    data = request.get_json()
    location_id = data['location_id']  # Na kojoj lokaciji
    quantity = data['quantity']  # + ili -
    reason = data.get('reason')

    if not reason:
        return jsonify({'error': 'Razlog je obavezan za korekciju'}), 400

    try:
        with db.session.begin_nested():
            movement = create_stock_movement(
                tenant_id=current_user.tenant_id,
                location_id=location_id,
                user_id=current_user.id,
                movement_type=MovementType.ADJUST,
                quantity=quantity,
                goods_item_id=item_id if item_type == 'goods' else None,
                spare_part_id=item_id if item_type == 'spare' else None,
                reason=reason,
            )

        db.session.commit()
        return jsonify({'success': True, 'movement_id': movement.id})

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
```

### 6.4 Lager Kartica (Stock Card)

```python
@bp.route('/stock-card/<item_type>/<int:item_id>')
@login_required
def stock_card(item_type, item_id):
    """Prikaz svih promena za artikal (opciono po lokaciji)."""
    location_id = request.args.get('location_id', type=int)
    from_date = request.args.get('from')
    to_date = request.args.get('to')

    query = StockMovement.query.filter(
        StockMovement.tenant_id == current_user.tenant_id
    )

    if item_type == 'goods':
        query = query.filter(StockMovement.goods_item_id == item_id)
    else:
        query = query.filter(StockMovement.spare_part_id == item_id)

    if location_id:
        query = query.filter(StockMovement.location_id == location_id)

    movements = query.order_by(StockMovement.created_at.desc()).all()
    return jsonify([m.to_dict() for m in movements])
```

### 6.5 Pregled stanja po lokacijama

```python
@bp.route('/stock-overview/<item_type>/<int:item_id>')
@login_required
def stock_overview(item_type, item_id):
    """Pregled stanja artikla po svim lokacijama."""
    from app.models.stock_movement import LocationStock

    if item_type == 'goods':
        stocks = LocationStock.query.filter_by(goods_item_id=item_id).all()
    else:
        stocks = LocationStock.query.filter_by(spare_part_id=item_id).all()

    return jsonify([{
        'location_id': s.location_id,
        'location_name': s.location.name if s.location else None,
        'quantity': s.quantity,
    } for s in stocks])
```

---

## FAZA 7: POS Receipt Model [P1]

### Zašto
Potrebno je čuvati istoriju prodaje za izveštaje i fiskalizaciju.

### Model

**Dodati u postojeći fajl ili novi:** `c:\servishub\app\models\pos.py`

```python
class PosReceipt(db.Model):
    """Račun sa kase."""
    __tablename__ = 'pos_receipt'

    id = db.Column(db.BigInteger, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('service_location.id'))

    receipt_number = db.Column(db.String(30), nullable=False)  # 2026-00001
    receipt_date = db.Column(db.DateTime, default=datetime.utcnow)

    # Iznosi
    subtotal = db.Column(db.Numeric(12, 2), default=0)
    tax_amount = db.Column(db.Numeric(12, 2), default=0)
    total_amount = db.Column(db.Numeric(12, 2), default=0)

    # Plaćanje
    payment_method = db.Column(db.String(20), default='CASH')  # CASH, CARD
    cash_received = db.Column(db.Numeric(12, 2))
    change_given = db.Column(db.Numeric(12, 2))

    # Fiskalno
    fiscal_number = db.Column(db.String(50))  # PFR broj
    fiscal_signature = db.Column(db.Text)
    is_fiscalized = db.Column(db.Boolean, default=False)

    # Storno
    is_voided = db.Column(db.Boolean, default=False)
    voided_at = db.Column(db.DateTime)
    void_reason = db.Column(db.String(255))

    created_by_id = db.Column(db.Integer, db.ForeignKey('tenant_user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship('PosReceiptItem', backref='receipt', cascade='all, delete-orphan')


class PosReceiptItem(db.Model):
    """Stavka računa."""
    __tablename__ = 'pos_receipt_item'

    id = db.Column(db.BigInteger, primary_key=True)
    receipt_id = db.Column(db.BigInteger, db.ForeignKey('pos_receipt.id'), nullable=False)

    # Šta je prodato (jedno od dva)
    goods_item_id = db.Column(db.Integer, db.ForeignKey('goods_item.id'))
    service_item_id = db.Column(db.Integer, db.ForeignKey('service_item.id'))

    item_name = db.Column(db.String(300), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    tax_label = db.Column(db.String(1), default='A')
    line_total = db.Column(db.Numeric(12, 2), nullable=False)
```

**Migracija:** `v335_create_pos_receipt.py`

---

## FAZA 8: Dnevni Izveštaj Pazara [P1]

### Endpoint

```python
@bp.route('/reports/daily-sales', methods=['GET'])
def daily_sales_report():
    """Dnevni izveštaj pazara."""
    date_str = request.args.get('date', date.today().isoformat())
    report_date = datetime.strptime(date_str, '%Y-%m-%d').date()

    # Sumiraj po načinu plaćanja
    receipts = PosReceipt.query.filter(
        PosReceipt.tenant_id == tenant_id,
        func.date(PosReceipt.receipt_date) == report_date,
        PosReceipt.is_voided == False
    ).all()

    cash_total = sum(r.total_amount for r in receipts if r.payment_method == 'CASH')
    card_total = sum(r.total_amount for r in receipts if r.payment_method == 'CARD')

    return jsonify({
        'date': report_date.isoformat(),
        'receipts_count': len(receipts),
        'cash_total': float(cash_total),
        'card_total': float(card_total),
        'grand_total': float(cash_total + card_total),
    })
```

---

## MIGRACIJE (redom)

| Verzija | Fajl | Opis |
|---------|------|------|
| v329 | `v329_add_unit_cost_to_usage.py` | unit_cost u SparePartUsage |
| v330 | `v330_create_service_item.py` | ServiceItem (usluge) |
| v331 | `v331_create_simple_supplier.py` | SimpleSupplier (dobavljači) |
| v332 | `v332_create_buyback_contract.py` | BuybackContract + Items (otkup) |
| v333 | `v333_link_invoice_supplier.py` | FK supplier_id u PurchaseInvoice |
| v334 | `v334_create_stock_movement.py` | **StockMovement + LocationStock** ⭐ |
| v335 | `v335_create_pos_receipt.py` | POS računi |
| v336 | `v336_add_stock_import.py` | Import endpoints (opciono) |
| v337 | `v337_create_transfer_request.py` | **TransferRequest** (transfer između lokacija) |
| v338 | `v338_create_supplier_price_list.py` | **SupplierPriceList** (cenovnici dobavljača) |
| v339 | `v339_create_part_order.py` | **PartOrderRequest** (B2B porudžbine) |
| v340 | `v340_create_marketplace_settings.py` | **MarketplaceSettings** (cena transakcije) |
| v341 | `v341_create_marketplace_rating.py` | **MarketplaceRating** (ocene) ⭐ |
| v342 | `v342_create_tenant_favorites.py` | **TenantFavoriteSupplier** (favoriti) |
| v343 | `v343_add_tenant_location.py` | city, lat, lng u Tenant (blizina) |
| v344 | `v344_add_tenant_rating_cache.py` | Rating cache polja u Tenant |
| v345 | `v345_create_delivery_options.py` | **SupplierDeliveryOption** (dostava) |
| v346 | `v346_add_order_delivery_fields.py` | Delivery polja u PartOrderRequest |

---

## CHECKLIST

### FAZA 1: unit_cost Fix
- [ ] Dodaj `unit_cost` u SparePartUsage model
- [ ] Kreiraj migraciju v329
- [ ] Izmeni endpoint za dodavanje dela - postavi unit_cost
- [ ] VERIFIKACIJA: Novi utrošak ima unit_cost != NULL

### FAZA 2: ServiceItem
- [ ] Kreiraj `app/models/service_item.py`
- [ ] Registruj u `__init__.py`
- [ ] Kreiraj migraciju v330
- [ ] Dodaj CRUD endpoints za usluge
- [ ] VERIFIKACIJA: Kreiranje usluge, prikaz u listi

### FAZA 3: Dobavljači i Otkup
- [ ] Kreiraj `SimpleSupplier` model (COMPANY/INDIVIDUAL)
- [ ] Kreiraj migraciju v331
- [ ] Kreiraj `BuybackContract` + `BuybackContractItem` modele
- [ ] Kreiraj migraciju v332
- [ ] Dodaj CRUD endpoints za dobavljače
- [ ] Dodaj buyback endpoints (create, sign, pay, pdf)
- [ ] Kreiraj PDF template za otkupni ugovor
- [ ] Implementiraj auto-kreiranje artikala pri potpisivanju
- [ ] VERIFIKACIJA: Kreiranje otkupa → PDF → potpis → artikl na stanju

### FAZA 4: Link PurchaseInvoice ↔ Supplier
- [ ] Dodaj `supplier_id` FK u PurchaseInvoice
- [ ] Kreiraj migraciju v333
- [ ] Ažuriraj invoice endpoints da koriste supplier_id
- [ ] VERIFIKACIJA: Nova faktura ima link ka dobavljaču

### FAZA 5: StockMovement + LocationStock ⭐ KRITIČNO
- [ ] Kreiraj `app/models/stock_movement.py` sa:
  - [ ] StockMovement model
  - [ ] LocationStock model (cache po lokaciji)
  - [ ] create_stock_movement() helper
  - [ ] MovementType enum sa INITIAL_BALANCE
- [ ] Registruj u `__init__.py`
- [ ] Kreiraj migraciju v334 sa CHECK constraints
- [ ] VERIFIKACIJA: Svaka promena zaliha kreira movement
- [ ] VERIFIKACIJA: balance_after uvek >= 0
- [ ] VERIFIKACIJA: LocationStock se ažurira automatski

### FAZA 6: Lager Endpoints (koriste StockMovement!)
- [ ] Dodaj `/goods/<id>/receive` endpoint → RECEIVE movement
- [ ] Dodaj `/parts/<id>/receive` endpoint → RECEIVE movement
- [ ] Dodaj `/stock/<type>/<id>/adjust` endpoint → ADJUST movement (samo admin)
- [ ] Dodaj `/stock-card/<type>/<id>` endpoint → prikaz kartice
- [ ] Dodaj `/stock-overview/<type>/<id>` endpoint → stanje po lokacijama
- [ ] Dodaj `/stock/import` endpoint → import iz Excel-a
- [ ] Dodaj `/stock/<type>/<id>/initial` endpoint → ručni unos početnog stanja
- [ ] VERIFIKACIJA: Prijem kreira RECEIVE movement
- [ ] VERIFIKACIJA: Korekcija zahteva reason
- [ ] VERIFIKACIJA: Import kreira INITIAL_BALANCE movements

### FAZA 7: POS Receipt
- [ ] Kreiraj PosReceipt i PosReceiptItem modele
- [ ] Kreiraj migraciju v335
- [ ] Implementiraj `/pos/sell` sa SALE movement-ima
- [ ] VERIFIKACIJA: Prodaja kreira receipt + movement za svaku stavku
- [ ] VERIFIKACIJA: Prodaja smanjuje LocationStock na lokaciji

### FAZA 8: Izveštaji
- [ ] Dodaj `/reports/daily-sales` endpoint
- [ ] Dodaj `/reports/stock-movements` endpoint
- [ ] Dodaj UI za dnevni pazar
- [ ] Dodaj UI za lager karticu po lokaciji
- [ ] VERIFIKACIJA: Suma računa = prikazani pazar
- [ ] VERIFIKACIJA: LocationStock.quantity == poslednji balance_after

---

## FAZA 9: Transfer između lokacija + Prikaz u nalogu [P2] ⭐ NOVO

### Pregled

**Transfer između lokacija istog tenanta:**
- Radnik vidi stanje na svim lokacijama svog tenanta
- Kreira zahtev za transfer (TransferRequest)
- Menadžer odredišne lokacije odobrava
- TRANSFER_OUT/TRANSFER_IN movements

**Prikaz delova u servisnom nalogu:**
- Delovi iz MOJE lokacije (odmah dostupni)
- Delovi iz DRUGIH lokacija istog tenanta (može kreirati TransferRequest)
- Matchovi iz Supplier Marketplace (može naručiti od dobavljača)

### 9.1 Interno Deljenje - TransferRequest

**Scenario:** Radnik na lokaciji A vidi da mu treba deo koji postoji na lokaciji B.

**Workflow:**
```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   PENDING   │────►│  APPROVED   │────►│   SHIPPED   │────►│  RECEIVED   │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
       │                   │
       └──────────────────►┌───────────┐
                           │  REJECTED │
                           └───────────┘
```

1. Radnik kreira `TransferRequest` (lokacija A traži od lokacije B)
2. Menadžer lokacije B odobrava/odbija zahtev
3. Ako odobren → kreiranje `TRANSFER_OUT` movement na lokaciji B
4. Primanje na lokaciji A → kreiranje `TRANSFER_IN` movement

**Model: TransferRequest**

```python
class TransferRequestStatus(enum.Enum):
    PENDING = 'PENDING'       # Čeka odobrenje
    APPROVED = 'APPROVED'     # Odobren, čeka slanje
    REJECTED = 'REJECTED'     # Odbijen
    SHIPPED = 'SHIPPED'       # Poslato
    RECEIVED = 'RECEIVED'     # Primljeno
    CANCELLED = 'CANCELLED'   # Otkazano


class TransferRequest(db.Model):
    """Zahtev za transfer robe između lokacija istog tenanta."""
    __tablename__ = 'transfer_request'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Request number: TR-2026-00001
    request_number = db.Column(db.String(20), unique=True, nullable=False)
    request_date = db.Column(db.Date, nullable=False, default=date.today)

    # Ko traži i od koga
    from_location_id = db.Column(
        db.Integer,
        db.ForeignKey('service_location.id', ondelete='RESTRICT'),
        nullable=False
    )
    to_location_id = db.Column(
        db.Integer,
        db.ForeignKey('service_location.id', ondelete='RESTRICT'),
        nullable=False
    )

    # Status
    status = db.Column(
        db.Enum(TransferRequestStatus),
        default=TransferRequestStatus.PENDING,
        nullable=False,
        index=True
    )

    # Razlog zahteva
    reason = db.Column(db.String(255))
    notes = db.Column(db.Text)

    # Audit
    requested_by_id = db.Column(db.Integer, db.ForeignKey('tenant_user.id'), nullable=False)
    approved_by_id = db.Column(db.Integer, db.ForeignKey('tenant_user.id'))
    approved_at = db.Column(db.DateTime)
    rejected_reason = db.Column(db.String(255))

    shipped_at = db.Column(db.DateTime)
    received_at = db.Column(db.DateTime)
    received_by_id = db.Column(db.Integer, db.ForeignKey('tenant_user.id'))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacije
    items = db.relationship(
        'TransferRequestItem',
        backref='request',
        cascade='all, delete-orphan',
        lazy='dynamic'
    )
    from_location = db.relationship('ServiceLocation', foreign_keys=[from_location_id])
    to_location = db.relationship('ServiceLocation', foreign_keys=[to_location_id])

    __table_args__ = (
        db.CheckConstraint('from_location_id != to_location_id', name='ck_transfer_diff_locations'),
    )


class TransferRequestItem(db.Model):
    """Stavka zahteva za transfer."""
    __tablename__ = 'transfer_request_item'

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(
        db.Integer,
        db.ForeignKey('transfer_request.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Šta se traži (jedno od dva)
    goods_item_id = db.Column(db.Integer, db.ForeignKey('goods_item.id'))
    spare_part_id = db.Column(db.BigInteger, db.ForeignKey('spare_part.id'))

    # Količine
    quantity_requested = db.Column(db.Integer, nullable=False)
    quantity_approved = db.Column(db.Integer)  # Može biti manje od traženog
    quantity_received = db.Column(db.Integer)

    notes = db.Column(db.String(255))

    __table_args__ = (
        db.CheckConstraint(
            '(goods_item_id IS NOT NULL AND spare_part_id IS NULL) OR '
            '(goods_item_id IS NULL AND spare_part_id IS NOT NULL)',
            name='ck_transfer_item_one'
        ),
    )
```

**Migracija:** `v337_create_transfer_request.py`

**Endpoints:**

| Ruta | Metoda | Opis |
|------|--------|------|
| `/transfers` | GET | Lista zahteva za moju lokaciju |
| `/transfers/create` | POST | Kreiraj novi zahtev |
| `/transfers/<id>` | GET | Detalji zahteva |
| `/transfers/<id>/approve` | POST | Odobri zahtev (menadžer) |
| `/transfers/<id>/reject` | POST | Odbij zahtev |
| `/transfers/<id>/ship` | POST | Označi kao poslato |
| `/transfers/<id>/receive` | POST | Potvrdi prijem |

**Integracija sa StockMovement:**

```python
@bp.route('/transfers/<int:request_id>/ship', methods=['POST'])
@login_required
def ship_transfer(request_id):
    """Šalje robu - kreira TRANSFER_OUT movements."""
    req = TransferRequest.query.get_or_404(request_id)

    if req.status != TransferRequestStatus.APPROVED:
        return jsonify({'error': 'Zahtev nije odobren'}), 400

    try:
        with db.session.begin_nested():
            for item in req.items:
                qty = item.quantity_approved or item.quantity_requested

                # Kreira TRANSFER_OUT na izvornoj lokaciji
                create_stock_movement(
                    tenant_id=req.tenant_id,
                    location_id=req.from_location_id,  # SA ove lokacije
                    target_location_id=req.to_location_id,  # NA ovu lokaciju
                    user_id=current_user.id,
                    movement_type=MovementType.TRANSFER_OUT,
                    quantity=-qty,  # Izlaz
                    goods_item_id=item.goods_item_id,
                    spare_part_id=item.spare_part_id,
                    reference_type='transfer_request',
                    reference_id=req.id,
                    reference_number=req.request_number,
                )

            req.status = TransferRequestStatus.SHIPPED
            req.shipped_at = datetime.utcnow()

        db.session.commit()
        return jsonify({'success': True})

    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@bp.route('/transfers/<int:request_id>/receive', methods=['POST'])
@login_required
def receive_transfer(request_id):
    """Prima robu - kreira TRANSFER_IN movements."""
    req = TransferRequest.query.get_or_404(request_id)

    if req.status != TransferRequestStatus.SHIPPED:
        return jsonify({'error': 'Roba nije poslata'}), 400

    data = request.get_json()

    try:
        with db.session.begin_nested():
            for item in req.items:
                # Korisnik potvrđuje primljenu količinu
                received_qty = data.get(f'item_{item.id}', item.quantity_approved)
                item.quantity_received = received_qty

                if received_qty > 0:
                    # Kreira TRANSFER_IN na odredišnoj lokaciji
                    create_stock_movement(
                        tenant_id=req.tenant_id,
                        location_id=req.to_location_id,  # NA ovu lokaciju
                        user_id=current_user.id,
                        movement_type=MovementType.TRANSFER_IN,
                        quantity=received_qty,  # Ulaz
                        goods_item_id=item.goods_item_id,
                        spare_part_id=item.spare_part_id,
                        reference_type='transfer_request',
                        reference_id=req.id,
                        reference_number=req.request_number,
                    )

            req.status = TransferRequestStatus.RECEIVED
            req.received_at = datetime.utcnow()
            req.received_by_id = current_user.id

        db.session.commit()
        return jsonify({'success': True})

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
```

---

### 9.2 Prikaz delova u servisnom nalogu

Kada tehničar kreira/edituje servisni nalog, sistem prikazuje dostupne delove iz tri izvora:

**UI Layout:**
```
┌────────────────────────────────────────────────────────────────────┐
│ DOSTUPNI DELOVI ZA: iPhone 12 Pro - Display                       │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│ 📍 MOJA LOKACIJA (Glavni servis)                                  │
│ ┌──────────────────────────────────────────────────────────────┐  │
│ │ Display iPhone 12 Pro OLED Original    Qty: 3    [DODAJ]     │  │
│ │ Display iPhone 12 Pro LCD AAA          Qty: 5    [DODAJ]     │  │
│ └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
│ 🏢 DRUGE LOKACIJE                                                 │
│ ┌──────────────────────────────────────────────────────────────┐  │
│ │ Lokacija: Novi Beograd                                       │  │
│ │ Display iPhone 12 Pro OLED Original    Qty: 2    [TRAŽI]     │  │
│ └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
│ 🛒 SUPPLIER MARKETPLACE                                           │
│ ┌──────────────────────────────────────────────────────────────┐  │
│ │ Display iPhone 12 Pro OLED     Cena: 12.500 RSD   [PORUČI]   │  │
│ │ Display iPhone 12 Pro LCD AAA  Cena: 8.000 RSD    [PORUČI]   │  │
│ └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

**Akcije:**
- **[DODAJ]** - Direktno dodaje deo na nalog (USE_TICKET movement)
- **[TRAŽI]** - Kreira TransferRequest ka toj lokaciji
- **[PORUČI]** - Kreira PartOrderRequest ka dobavljaču

**API Endpoint za prikaz:**

```python
@bp.route('/api/ticket/<int:ticket_id>/available-parts')
@login_required
def get_available_parts(ticket_id):
    """
    Vraća dostupne delove za servisni nalog iz svih izvora.

    Matchuje po brand/model uređaja iz naloga.
    """
    ticket = ServiceTicket.query.get_or_404(ticket_id)

    brand = ticket.device_brand  # npr. "Apple"
    model = ticket.device_model  # npr. "iPhone 12 Pro"

    result = {
        'my_location': [],      # Delovi na mojoj lokaciji
        'other_locations': [],  # Delovi na drugim lokacijama tenanta
        'marketplace': [],      # Matchovi iz supplier marketplace-a
    }

    # 1. Moja lokacija
    my_location_id = current_user.location_id
    my_stock = LocationStock.query.join(SparePart).filter(
        LocationStock.location_id == my_location_id,
        LocationStock.quantity > 0,
        SparePart.brand.ilike(f'%{brand}%'),
        SparePart.model.ilike(f'%{model}%'),
    ).all()

    for stock in my_stock:
        result['my_location'].append({
            'spare_part_id': stock.spare_part_id,
            'part_name': stock.spare_part.part_name,
            'quantity': stock.quantity,
            'selling_price': float(stock.spare_part.selling_price) if stock.spare_part.selling_price else None,
        })

    # 2. Druge lokacije istog tenanta
    other_locations = ServiceLocation.query.filter(
        ServiceLocation.tenant_id == current_user.tenant_id,
        ServiceLocation.id != my_location_id
    ).all()

    for loc in other_locations:
        loc_stock = LocationStock.query.join(SparePart).filter(
            LocationStock.location_id == loc.id,
            LocationStock.quantity > 0,
            SparePart.brand.ilike(f'%{brand}%'),
            SparePart.model.ilike(f'%{model}%'),
        ).all()

        if loc_stock:
            result['other_locations'].append({
                'location_id': loc.id,
                'location_name': loc.name,
                'parts': [{
                    'spare_part_id': s.spare_part_id,
                    'part_name': s.spare_part.part_name,
                    'quantity': s.quantity,
                } for s in loc_stock]
            })

    # 3. Supplier Marketplace
    result['marketplace'] = find_marketplace_matches(brand, model, buyer_tenant_id=current_user.tenant_id)

    return jsonify(result)
```

---

### 9.3 Migracija za FAZU 9

| Verzija | Fajl | Opis |
|---------|------|------|
| v337 | `v337_create_transfer_request.py` | TransferRequest + TransferRequestItem |

---

### 9.4 UI Komponente

- Badge "Dostupno na drugim lokacijama" na artiklu ako ima stanja drugde
- Modal za kreiranje zahteva za transfer
- Lista dolaznih/odlaznih zahteva sa akcijama (odobri/odbij/pošalji/primi)
- Widget u servisnom nalogu sa 3 izvora delova

---

### 9.5 CHECKLIST za FAZU 9

**TransferRequest:**
- [ ] Kreiraj TransferRequest + TransferRequestItem modele
- [ ] Kreiraj migraciju v337
- [ ] Dodaj `/transfers/*` endpoints (create, approve, reject, ship, receive)
- [ ] Implementiraj TRANSFER_OUT/IN movements pri slanju/prijemu
- [ ] Dodaj UI za pregled stanja na svim lokacijama tenanta
- [ ] Dodaj UI za kreiranje i odobravanje zahteva
- [ ] VERIFIKACIJA: Transfer kreira parove OUT/IN movements
- [ ] VERIFIKACIJA: Stanje se ispravno menja na obe lokacije

**Prikaz u servisnom nalogu:**
- [ ] Endpoint `/api/ticket/<id>/available-parts`
- [ ] UI widget sa 3 sekcije (moja lokacija, druge lokacije, marketplace)
- [ ] Akcija [DODAJ] → USE_TICKET movement
- [ ] Akcija [TRAŽI] → kreira TransferRequest
- [ ] Akcija [PORUČI] → kreira PartOrderRequest (FAZA 10)
- [ ] VERIFIKACIJA: Matchovanje po brand/model uređaja radi

---

## FAZA 10: Supplier Marketplace - B2B Delovi [P1] ⭐ NOVO

### Pregled

Dobavljači objavljuju cenovnike rezervnih delova. Servisi (tenanti) vide matchove dok kreiraju servisni nalog i mogu direktno naručiti. Nakon obostrane potvrde, obe strane dobijaju kontakt detalje i skida se kredit.

**Ključni flow:**
```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ Dobavljač       │     │ Tenant kreira   │     │ Tenant vidi     │
│ upload cenovnik │────►│ servisni nalog  │────►│ match iz        │
│                 │     │ (iPhone 12 Pro) │     │ marketplace-a   │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                          │
                        ┌─────────────────┐               │
                        │ Tenant klikne   │◄──────────────┘
                        │ "Poruči"        │
                        └────────┬────────┘
                                 │
┌─────────────────┐              │
│ Dobavljač vidi  │◄─────────────┘
│ novu porudžbinu │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ Dobavljač       │     │ Obostrana       │     │ Obe strane      │
│ potvrdi         │────►│ konfirmacija    │────►│ -0.5 kredita    │
│ (ima na stanju) │     │                 │     │ + full detalji  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

---

### 10.1 Model: SupplierPriceList (Cenovnik)

Dobavljač uploaduje cenovnik sa artiklima i cenama.

```python
class PriceListStatus(enum.Enum):
    DRAFT = 'DRAFT'       # U pripremi
    ACTIVE = 'ACTIVE'     # Aktivan, vidljiv tenantima
    PAUSED = 'PAUSED'     # Pauziran (privremeno nevidljiv)
    ARCHIVED = 'ARCHIVED' # Arhiviran


class SupplierPriceList(db.Model):
    """
    Cenovnik dobavljača.

    Dobavljač može imati više cenovnika (npr. po kategorijama).
    """
    __tablename__ = 'supplier_price_list'

    id = db.Column(db.Integer, primary_key=True)

    # Dobavljač (tenant koji je registrovan kao dobavljač)
    supplier_tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Osnovni podaci
    name = db.Column(db.String(200), nullable=False)  # "Ekrani za iPhone"
    description = db.Column(db.Text)
    currency = db.Column(db.String(3), default='RSD')

    # Status
    status = db.Column(
        db.Enum(PriceListStatus),
        default=PriceListStatus.DRAFT,
        nullable=False,
        index=True
    )

    # Validnost (opciono)
    valid_from = db.Column(db.Date)
    valid_until = db.Column(db.Date)

    # Statistika
    total_items = db.Column(db.Integer, default=0)
    total_orders = db.Column(db.Integer, default=0)

    # Audit
    created_by_id = db.Column(db.Integer, db.ForeignKey('tenant_user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    last_import_at = db.Column(db.DateTime)

    # Relacije
    items = db.relationship(
        'SupplierPriceListItem',
        backref='price_list',
        cascade='all, delete-orphan',
        lazy='dynamic'
    )
    supplier_tenant = db.relationship('Tenant')
```

---

### 10.2 Model: SupplierPriceListItem (Stavka cenovnika)

```python
class SupplierPriceListItem(db.Model):
    """
    Stavka u cenovniku dobavljača.

    Matchuje se sa servisnim nalozima po brand/model/part_category.
    """
    __tablename__ = 'supplier_price_list_item'

    id = db.Column(db.BigInteger, primary_key=True)
    price_list_id = db.Column(
        db.Integer,
        db.ForeignKey('supplier_price_list.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Podaci za matching
    brand = db.Column(db.String(100), nullable=False, index=True)  # Apple, Samsung
    model = db.Column(db.String(100), index=True)  # iPhone 12 Pro, Galaxy S21
    part_category = db.Column(db.String(50), index=True)  # DISPLAY, BATTERY, CAMERA
    part_name = db.Column(db.String(200), nullable=False)  # "Ekran iPhone 12 Pro OLED Original"

    # Kvalitet/tip
    quality_grade = db.Column(db.String(20))  # Original, OEM, AAA, AA
    is_original = db.Column(db.Boolean, default=False)

    # Cena (ovo tenant vidi)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), default='RSD')

    # Dostupnost (informativno, dobavljač potvrđuje pre finalizacije)
    in_stock = db.Column(db.Boolean, default=True)
    stock_quantity = db.Column(db.Integer)  # Opciono
    lead_time_days = db.Column(db.Integer)  # "Dostava za X dana"

    # Za pretragu - konkatenirani tekst
    search_text = db.Column(db.Text)  # brand + model + part_name + quality

    # Status
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    __table_args__ = (
        db.Index('ix_price_item_brand_model', 'brand', 'model'),
        db.Index('ix_price_item_active_stock', 'is_active', 'in_stock'),
    )

    def to_public_dict(self):
        """Za prikaz tenantu - SAMO ime i cena, bez detalja o dobavljaču!"""
        return {
            'id': self.id,
            'part_name': self.part_name,
            'brand': self.brand,
            'model': self.model,
            'quality_grade': self.quality_grade,
            'is_original': self.is_original,
            'price': float(self.price),
            'currency': self.currency,
            'in_stock': self.in_stock,
            'lead_time_days': self.lead_time_days,
            # NE uključuje: supplier info, kontakt, itd.
        }
```

---

### 10.3 Model: PartOrderRequest (Porudžbina dela)

```python
class PartOrderStatus(enum.Enum):
    PENDING = 'PENDING'           # Tenant poslao, čeka potvrdu dobavljača
    CONFIRMED = 'CONFIRMED'       # Dobavljač potvrdio - krediti skinuti, detalji razmenjeni
    REJECTED = 'REJECTED'         # Dobavljač odbio (nema na stanju, cena se promenila)
    CANCELLED = 'CANCELLED'       # Tenant otkazao pre potvrde
    COMPLETED = 'COMPLETED'       # Roba preuzeta/isporučena
    DISPUTED = 'DISPUTED'         # Problem prijavljen


class PartOrderRequest(db.Model):
    """
    Porudžbina rezervnog dela iz marketplace-a.

    Tenant naručuje → Dobavljač potvrđuje → Krediti se skidaju → Razmena detalja.
    """
    __tablename__ = 'part_order_request'

    id = db.Column(db.Integer, primary_key=True)

    # Broj porudžbine: MKT-2026-00001
    order_number = db.Column(db.String(20), unique=True, nullable=False)
    order_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Ko naručuje (servis)
    buyer_tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='RESTRICT'),
        nullable=False,
        index=True
    )

    # Od koga naručuje (dobavljač)
    supplier_tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='RESTRICT'),
        nullable=False,
        index=True
    )

    # Šta naručuje
    price_list_item_id = db.Column(
        db.BigInteger,
        db.ForeignKey('supplier_price_list_item.id', ondelete='RESTRICT'),
        nullable=False
    )

    # Opciono: veza sa servisnim nalogom
    service_ticket_id = db.Column(
        db.BigInteger,
        db.ForeignKey('service_ticket.id', ondelete='SET NULL'),
        nullable=True
    )

    # Količina i cena (snapshot u trenutku narudžbine)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), default='RSD')
    total_amount = db.Column(db.Numeric(12, 2), nullable=False)

    # Status
    status = db.Column(
        db.Enum(PartOrderStatus),
        default=PartOrderStatus.PENDING,
        nullable=False,
        index=True
    )

    # Napomene
    buyer_notes = db.Column(db.Text)      # "Treba mi hitno"
    supplier_notes = db.Column(db.Text)   # "Šaljemo u sledećoj turi"
    reject_reason = db.Column(db.String(255))

    # Naplata kredita
    credit_charged = db.Column(db.Boolean, default=False)
    credit_amount_buyer = db.Column(db.Numeric(5, 2))   # 0.5 default
    credit_amount_supplier = db.Column(db.Numeric(5, 2))  # 0.5 default
    credit_charged_at = db.Column(db.DateTime)

    # Audit
    created_by_id = db.Column(db.Integer, db.ForeignKey('tenant_user.id'), nullable=False)
    confirmed_by_id = db.Column(db.Integer, db.ForeignKey('tenant_user.id'))
    confirmed_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacije
    buyer_tenant = db.relationship('Tenant', foreign_keys=[buyer_tenant_id])
    supplier_tenant = db.relationship('Tenant', foreign_keys=[supplier_tenant_id])
    price_list_item = db.relationship('SupplierPriceListItem')
    service_ticket = db.relationship('ServiceTicket')
    messages = db.relationship(
        'PartOrderMessage',
        backref='order',
        cascade='all, delete-orphan',
        order_by='PartOrderMessage.created_at'
    )

    @staticmethod
    def generate_order_number() -> str:
        year = datetime.now().year
        prefix = f"MKT-{year}-"
        last = PartOrderRequest.query.filter(
            PartOrderRequest.order_number.like(f"{prefix}%")
        ).order_by(PartOrderRequest.order_number.desc()).first()
        next_num = 1
        if last:
            try:
                next_num = int(last.order_number.split('-')[-1]) + 1
            except ValueError:
                pass
        return f"{prefix}{next_num:05d}"

    def to_buyer_dict(self):
        """Za kupca - prikazuje detalje dobavljača samo ako je CONFIRMED."""
        data = {
            'id': self.id,
            'order_number': self.order_number,
            'order_date': self.order_date.isoformat(),
            'status': self.status.value,
            'quantity': self.quantity,
            'unit_price': float(self.unit_price),
            'total_amount': float(self.total_amount),
            'currency': self.currency,
            'item': self.price_list_item.to_public_dict() if self.price_list_item else None,
            'buyer_notes': self.buyer_notes,
            'supplier_notes': self.supplier_notes,
            'messages_count': len(self.messages),
        }

        # Prikaži detalje dobavljača SAMO nakon potvrde
        if self.status in (PartOrderStatus.CONFIRMED, PartOrderStatus.COMPLETED):
            data['supplier'] = {
                'name': self.supplier_tenant.name,
                'company_name': self.supplier_tenant.company_name,
                'address': self.supplier_tenant.address,
                'city': self.supplier_tenant.city,
                'phone': self.supplier_tenant.phone,
                'email': self.supplier_tenant.email,
                'pib': self.supplier_tenant.pib,
            }

        return data

    def to_supplier_dict(self):
        """Za dobavljača - prikazuje detalje kupca samo ako je CONFIRMED."""
        data = {
            'id': self.id,
            'order_number': self.order_number,
            'order_date': self.order_date.isoformat(),
            'status': self.status.value,
            'quantity': self.quantity,
            'unit_price': float(self.unit_price),
            'total_amount': float(self.total_amount),
            'currency': self.currency,
            'item': self.price_list_item.to_full_dict() if self.price_list_item else None,
            'buyer_notes': self.buyer_notes,
            'supplier_notes': self.supplier_notes,
            'messages_count': len(self.messages),
        }

        # Prikaži detalje kupca SAMO nakon potvrde
        if self.status in (PartOrderStatus.CONFIRMED, PartOrderStatus.COMPLETED):
            data['buyer'] = {
                'name': self.buyer_tenant.name,
                'company_name': self.buyer_tenant.company_name,
                'address': self.buyer_tenant.address,
                'city': self.buyer_tenant.city,
                'phone': self.buyer_tenant.phone,
                'email': self.buyer_tenant.email,
                'ticket_number': self.service_ticket.ticket_number if self.service_ticket else None,
            }

        return data
```

---

### 10.4 Model: PartOrderMessage (Poruke)

```python
class PartOrderMessage(db.Model):
    """Poruka vezana za porudžbinu - omogućava komunikaciju pre/posle potvrde."""
    __tablename__ = 'part_order_message'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(
        db.Integer,
        db.ForeignKey('part_order_request.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Ko šalje
    sender_tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    sender_user_id = db.Column(db.Integer, db.ForeignKey('tenant_user.id'))

    # Poruka
    message = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(20), default='text')  # text, status_change, system

    # Read status
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relacije
    sender_tenant = db.relationship('Tenant')
    sender_user = db.relationship('TenantUser')
```

---

### 10.5 Konfiguracija cene transakcije (Admin Panel)

Cena se čuva u sistemskim podešavanjima i može se menjati u **SHUB Admin → Paketi**.

```python
class MarketplaceSettings(db.Model):
    """Sistemska podešavanja za marketplace."""
    __tablename__ = 'marketplace_settings'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(255))
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    updated_by_id = db.Column(db.Integer)

# Početne vrednosti:
# | key                        | value | description                          |
# |----------------------------|-------|--------------------------------------|
# | part_order_credit_buyer    | 0.5   | Krediti koji se skidaju kupcu        |
# | part_order_credit_supplier | 0.5   | Krediti koji se skidaju dobavljaču   |
# | min_credits_to_order       | 1.0   | Min kredita za kreiranje porudžbine  |
```

**Admin UI (Sidebar → Paketi → Marketplace):**
```
┌─────────────────────────────────────────────────────────────────┐
│ MARKETPLACE PODEŠAVANJA                                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Cena transakcije (krediti):                                     │
│ ┌─────────────────┐  ┌─────────────────┐                       │
│ │ Kupac:    0.5   │  │ Dobavljač: 0.5  │                       │
│ └─────────────────┘  └─────────────────┘                       │
│                                                                 │
│ Min kredita za porudžbinu: [  1.0  ]                           │
│                                                                 │
│ [   SAČUVAJ   ]                                                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

### 10.6 Matching algoritam

Kada tenant kreira servisni nalog, sistem traži matchove u marketplace-u.

```python
def find_marketplace_matches(brand: str, model: str, part_category: str = None) -> list:
    """
    Traži matchove u aktivnim cenovnicima dobavljača.

    Returns: Lista matchova sortirano po ceni (najjeftinije prvo)
    """
    query = db.session.query(SupplierPriceListItem).join(
        SupplierPriceList
    ).filter(
        SupplierPriceList.status == PriceListStatus.ACTIVE,
        SupplierPriceListItem.is_active == True,
        SupplierPriceListItem.in_stock == True,
        db.func.lower(SupplierPriceListItem.brand) == brand.lower()
    )

    if model:
        query = query.filter(
            db.func.lower(SupplierPriceListItem.model).contains(model.lower())
        )

    if part_category:
        query = query.filter(SupplierPriceListItem.part_category == part_category)

    items = query.order_by(SupplierPriceListItem.price.asc()).limit(20).all()
    return [item.to_public_dict() for item in items]
```

---

### 10.7 Kreiranje porudžbine

```python
@bp.route('/api/marketplace/order', methods=['POST'])
@login_required
def create_part_order():
    """Tenant kreira porudžbinu za deo iz marketplace-a."""
    data = request.get_json()
    item_id = data['item_id']
    quantity = data.get('quantity', 1)
    notes = data.get('notes')
    ticket_id = data.get('ticket_id')

    item = SupplierPriceListItem.query.get_or_404(item_id)
    price_list = item.price_list

    # Proveri kredite kupca
    buyer_cost, _ = get_order_credit_cost()
    buyer_credits = get_tenant_credits(current_user.tenant_id)

    if buyer_credits < buyer_cost:
        return jsonify({'error': 'Nemate dovoljno kredita'}), 400

    order = PartOrderRequest(
        order_number=PartOrderRequest.generate_order_number(),
        buyer_tenant_id=current_user.tenant_id,
        supplier_tenant_id=price_list.supplier_tenant_id,
        price_list_item_id=item.id,
        service_ticket_id=ticket_id,
        quantity=quantity,
        unit_price=item.price,
        total_amount=item.price * quantity,
        buyer_notes=notes,
        created_by_id=current_user.id,
    )
    db.session.add(order)
    db.session.commit()

    # TODO: Notifikacija dobavljaču

    return jsonify({'success': True, 'order_number': order.order_number})
```

---

### 10.8 Potvrda od dobavljača + Naplata kredita

```python
@bp.route('/api/marketplace/order/<int:order_id>/confirm', methods=['POST'])
@login_required
def confirm_part_order(order_id):
    """
    Dobavljač potvrđuje porudžbinu.

    Posle potvrde:
    1. Skidaju se krediti sa obe strane
    2. Obe strane dobijaju full detalje jedna o drugoj
    """
    order = PartOrderRequest.query.get_or_404(order_id)

    if order.supplier_tenant_id != current_user.tenant_id:
        return jsonify({'error': 'Nemate pristup'}), 403

    if order.status != PartOrderStatus.PENDING:
        return jsonify({'error': 'Porudžbina nije u PENDING statusu'}), 400

    buyer_cost, supplier_cost = get_order_credit_cost()

    # Proveri kredite obe strane
    if get_tenant_credits(current_user.tenant_id) < supplier_cost:
        return jsonify({'error': 'Nemate dovoljno kredita za potvrdu'}), 400

    if get_tenant_credits(order.buyer_tenant_id) < buyer_cost:
        return jsonify({'error': 'Kupac nema dovoljno kredita'}), 400

    with db.session.begin_nested():
        # Skini kredite
        deduct_credits(order.buyer_tenant_id, buyer_cost, f"Marketplace: {order.order_number}")
        deduct_credits(order.supplier_tenant_id, supplier_cost, f"Marketplace: {order.order_number}")

        # Ažuriraj status
        order.status = PartOrderStatus.CONFIRMED
        order.confirmed_at = datetime.utcnow()
        order.confirmed_by_id = current_user.id
        order.credit_charged = True
        order.credit_amount_buyer = buyer_cost
        order.credit_amount_supplier = supplier_cost
        order.credit_charged_at = datetime.utcnow()

    db.session.commit()

    # TODO: Notifikacija kupcu

    return jsonify({
        'success': True,
        'buyer_details': order.to_supplier_dict()['buyer']
    })
```

---

### 10.9 Slanje poruke

```python
@bp.route('/api/marketplace/order/<int:order_id>/message', methods=['POST'])
@login_required
def send_order_message(order_id):
    """Šalje poruku vezanu za porudžbinu."""
    order = PartOrderRequest.query.get_or_404(order_id)

    if current_user.tenant_id not in (order.buyer_tenant_id, order.supplier_tenant_id):
        return jsonify({'error': 'Nemate pristup'}), 403

    message_text = request.get_json().get('message', '').strip()

    msg = PartOrderMessage(
        order_id=order.id,
        sender_tenant_id=current_user.tenant_id,
        sender_user_id=current_user.id,
        message=message_text,
    )
    db.session.add(msg)
    db.session.commit()

    return jsonify({'success': True})
```

---

### 10.10 Upload cenovnika (CSV/Excel)

```python
@bp.route('/api/supplier/price-list/<int:list_id>/import', methods=['POST'])
@login_required
def import_price_list(list_id):
    """
    Import artikala u cenovnik iz CSV/Excel.

    Format:
    | brand | model | part_category | part_name | quality_grade | price | in_stock |
    """
    import pandas as pd

    price_list = SupplierPriceList.query.get_or_404(list_id)

    if price_list.supplier_tenant_id != current_user.tenant_id:
        return jsonify({'error': 'Nemate pristup'}), 403

    file = request.files.get('file')
    df = pd.read_csv(file) if file.filename.endswith('.csv') else pd.read_excel(file)

    imported = 0
    for idx, row in df.iterrows():
        item = SupplierPriceListItem(
            price_list_id=price_list.id,
            brand=str(row['brand']).strip(),
            model=str(row.get('model', '')).strip() or None,
            part_name=str(row['part_name']).strip(),
            quality_grade=str(row.get('quality_grade', '')).strip() or None,
            price=Decimal(str(row['price'])),
            in_stock=bool(row.get('in_stock', True)),
        )
        item.search_text = f"{item.brand} {item.model or ''} {item.part_name}".lower()
        db.session.add(item)
        imported += 1

    price_list.total_items += imported
    price_list.last_import_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'success': True, 'imported': imported})
```

---

### 10.11 Načini Dostave (Delivery Options) ⭐ NOVO

Dobavljač definiše svoje načine dostave u admin panelu. Pri potvrdi porudžbine bira način i tenant vidi procenjeno vreme isporuke.

**Model: SupplierDeliveryOption**

```python
class SupplierDeliveryOption(db.Model):
    """Načini dostave koje nudi dobavljač."""
    __tablename__ = 'supplier_delivery_option'

    id = db.Column(db.Integer, primary_key=True)

    # Dobavljač
    supplier_tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Naziv opcije
    name = db.Column(db.String(100), nullable=False)  # "Lična dostava", "Kurirska služba", "Preuzimanje"
    description = db.Column(db.Text)  # Dodatni opis

    # Procenjeno vreme (u danima)
    estimated_days_min = db.Column(db.Integer, default=1)  # Minimum
    estimated_days_max = db.Column(db.Integer, default=3)  # Maximum

    # Cena dostave (opciono)
    delivery_cost = db.Column(db.Numeric(10, 2), default=0)
    currency = db.Column(db.String(3), default='RSD')

    # Uslovi
    is_free_above = db.Column(db.Numeric(10, 2))  # Besplatna dostava iznad X RSD
    min_order_amount = db.Column(db.Numeric(10, 2))  # Min iznos za ovu opciju

    # Status
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_default = db.Column(db.Boolean, default=False)  # Default opcija

    # Redosled prikaza
    sort_order = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    __table_args__ = (
        db.Index('ix_delivery_supplier_active', 'supplier_tenant_id', 'is_active'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'estimated_days': f"{self.estimated_days_min}-{self.estimated_days_max}" if self.estimated_days_min != self.estimated_days_max else str(self.estimated_days_min),
            'delivery_cost': float(self.delivery_cost) if self.delivery_cost else 0,
            'currency': self.currency,
            'is_free_above': float(self.is_free_above) if self.is_free_above else None,
            'is_default': self.is_default,
        }
```

**Proširenje PartOrderRequest za dostavu:**

```python
# Dodati u PartOrderRequest model:
delivery_option_id = db.Column(
    db.Integer,
    db.ForeignKey('supplier_delivery_option.id', ondelete='SET NULL'),
    nullable=True
)
delivery_option_name = db.Column(db.String(100))  # Snapshot naziva
delivery_cost = db.Column(db.Numeric(10, 2), default=0)
estimated_delivery_date = db.Column(db.Date)  # Procenjeni datum isporuke
actual_delivery_date = db.Column(db.Date)  # Stvarni datum isporuke

# Relacija
delivery_option = db.relationship('SupplierDeliveryOption')
```

**Potvrda porudžbine sa izborom dostave:**

```python
@bp.route('/api/marketplace/order/<int:order_id>/confirm', methods=['POST'])
@login_required
def confirm_part_order(order_id):
    """
    Dobavljač potvrđuje porudžbinu i bira način dostave.
    """
    order = PartOrderRequest.query.get_or_404(order_id)

    if order.supplier_tenant_id != current_user.tenant_id:
        return jsonify({'error': 'Nemate pristup'}), 403

    if order.status != PartOrderStatus.PENDING:
        return jsonify({'error': 'Porudžbina nije u PENDING statusu'}), 400

    data = request.get_json()
    delivery_option_id = data.get('delivery_option_id')

    if not delivery_option_id:
        return jsonify({'error': 'Izaberite način dostave'}), 400

    delivery_option = SupplierDeliveryOption.query.get(delivery_option_id)
    if not delivery_option or delivery_option.supplier_tenant_id != current_user.tenant_id:
        return jsonify({'error': 'Neispravan način dostave'}), 400

    # Izračunaj procenjeni datum isporuke
    from datetime import timedelta
    estimated_date = date.today() + timedelta(days=delivery_option.estimated_days_max)

    # Krediti check...
    buyer_cost, supplier_cost = get_order_credit_cost()
    # ...

    with db.session.begin_nested():
        # Skini kredite...

        # Postavi dostavu
        order.delivery_option_id = delivery_option.id
        order.delivery_option_name = delivery_option.name
        order.delivery_cost = delivery_option.delivery_cost
        order.estimated_delivery_date = estimated_date

        order.status = PartOrderStatus.CONFIRMED
        order.confirmed_at = datetime.utcnow()
        order.confirmed_by_id = current_user.id
        # ...

    db.session.commit()

    return jsonify({
        'success': True,
        'estimated_delivery_date': estimated_date.isoformat(),
        'delivery_method': delivery_option.name,
    })
```

**Endpoints za upravljanje načinima dostave:**

| Ruta | Metoda | Opis |
|------|--------|------|
| `/api/supplier/delivery-options` | GET | Lista mojih opcija dostave |
| `/api/supplier/delivery-options` | POST | Dodaj novu opciju |
| `/api/supplier/delivery-options/<id>` | PUT | Izmeni opciju |
| `/api/supplier/delivery-options/<id>` | DELETE | Obriši opciju |
| `/api/supplier/delivery-options/<id>/default` | POST | Postavi kao default |

**UI za dobavljača - Podešavanja dostave:**

```
┌─────────────────────────────────────────────────────────────────────────┐
│ NAČINI DOSTAVE                                            [+ DODAJ]    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ ⭐ Kurirska služba (default)                                           │
│    Rok: 1-2 dana  │  Cena: 300 RSD  │  Besplatno iznad: 5.000 RSD      │
│    [IZMENI]  [OBRIŠI]                                                   │
│                                                                         │
│ Lična dostava                                                           │
│    Rok: Isti dan  │  Cena: 500 RSD  │  Samo za Beograd                 │
│    [IZMENI]  [OBRIŠI]  [POSTAVI KAO DEFAULT]                           │
│                                                                         │
│ Preuzimanje u magacinu                                                  │
│    Rok: Odmah  │  Besplatno                                            │
│    [IZMENI]  [OBRIŠI]  [POSTAVI KAO DEFAULT]                           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**UI za dobavljača - Potvrda porudžbine:**

```
┌─────────────────────────────────────────────────────────────────────────┐
│ POTVRDA PORUDŽBINE: MKT-2026-00042                                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ Artikal: Display iPhone 12 Pro OLED Original                            │
│ Količina: 1  │  Cena: 12.500 RSD                                        │
│                                                                         │
│ KUPAC: Rating 92% (25)                                                  │
│                                                                         │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━│
│                                                                         │
│ IZABERITE NAČIN DOSTAVE:                                                │
│                                                                         │
│ (●) Kurirska služba - 1-2 dana - 300 RSD                               │
│ ( ) Lična dostava - Isti dan - 500 RSD                                 │
│ ( ) Preuzimanje - Odmah - Besplatno                                    │
│                                                                         │
│ Procenjeni datum isporuke: 08.02.2026.                                  │
│                                                                         │
│ [POTVRDI PORUDŽBINU]    [ODBIJ]                                         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**UI za tenanta - Praćenje isporuke:**

```
┌─────────────────────────────────────────────────────────────────────────┐
│ PORUDŽBINA: MKT-2026-00042                           Status: POTVRĐENO  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ Artikal: Display iPhone 12 Pro OLED Original                            │
│ Količina: 1  │  Cena: 12.500 RSD                                        │
│                                                                         │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━│
│                                                                         │
│ DOSTAVA:                                                                │
│ 📦 Kurirska služba                                                      │
│ 📅 Očekivani datum: 08.02.2026.                                         │
│ 💰 Cena dostave: 300 RSD                                                │
│                                                                         │
│ DOBAVLJAČ:                                                              │
│ Ime: Servis Parts DOO                                                   │
│ Adresa: Bulevar Mihajla Pupina 10, Novi Sad                             │
│ Telefon: 021/555-1234                                                   │
│                                                                         │
│ [POŠALJI PORUKU]  [OZNAČI KAO PRIMLJENO]                                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### 10.12 Migracije za FAZU 10

| Verzija | Fajl | Opis |
|---------|------|------|
| v338 | `v338_create_supplier_price_list.py` | SupplierPriceList + Items |
| v339 | `v339_create_part_order.py` | PartOrderRequest + Messages |
| v340 | `v340_create_marketplace_settings.py` | MarketplaceSettings |
| v341 | `v341_create_marketplace_rating.py` | MarketplaceRating |
| v342 | `v342_create_tenant_favorites.py` | TenantFavoriteSupplier |
| v343 | `v343_add_tenant_location.py` | city, lat, lng u Tenant |
| v344 | `v344_add_tenant_rating_cache.py` | Rating cache polja u Tenant |
| v345 | `v345_create_delivery_options.py` | SupplierDeliveryOption |
| v346 | `v346_add_order_delivery_fields.py` | Delivery polja u PartOrderRequest |

---

### 10.13 UI Komponente

**Za dobavljača:**
- "Moji cenovnici" stranica sa CRUD
- Import iz CSV/Excel dugme
- "Dolazne porudžbine" tab
- "Načini dostave" podešavanja u admin panelu
- Izbor dostave pri potvrdi porudžbine
- Dugmad "Potvrdi" / "Odbij"
- Chat za svaku porudžbinu

**Za tenanta (servis):**
- Widget u servisnom nalogu "Marketplace delovi"
- Automatsko pretraživanje po brand/model telefona
- Lista rezultata: ime + cena + "Poruči" dugme
- "Moje porudžbine" stranica
- Chat za svaku porudžbinu

---

### 10.13 Audit Trail

Sve akcije se loguju:
- Kreiranje porudžbine
- Potvrda/Odbijanje
- Sve poruke
- Skidanje kredita
- Promena statusa

---

### 10.14 Sistem Ocenjivanja (Ratings) ⭐ NOVO

Nakon završene transakcije (status = COMPLETED), obe strane mogu da se međusobno ocene.

**Model: MarketplaceRating**

```python
class RatingType(enum.Enum):
    POSITIVE = 'POSITIVE'   # 👍 Pozitivna ocena
    NEGATIVE = 'NEGATIVE'   # 👎 Negativna ocena


class MarketplaceRating(db.Model):
    """
    Obostrane ocene nakon marketplace transakcije.

    - Tenant ocenjuje dobavljača
    - Dobavljač ocenjuje tenanta
    - Ocene su javne i utiču na prikaz u rezultatima
    """
    __tablename__ = 'marketplace_rating'

    id = db.Column(db.Integer, primary_key=True)

    # Porudžbina za koju se daje ocena
    order_id = db.Column(
        db.Integer,
        db.ForeignKey('part_order_request.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Ko ocenjuje
    rater_tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    rater_user_id = db.Column(db.Integer, db.ForeignKey('tenant_user.id'))

    # Koga ocenjuje
    rated_tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Tip ocene: da li je ocenjivač kupac ili dobavljač
    rating_role = db.Column(db.String(20), nullable=False)  # 'buyer', 'supplier'

    # Ocena
    rating_type = db.Column(
        db.Enum(RatingType),
        nullable=False
    )

    # Komentar (opciono)
    comment = db.Column(db.Text)

    # Timestamp
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relacije
    order = db.relationship('PartOrderRequest', backref='ratings')
    rater_tenant = db.relationship('Tenant', foreign_keys=[rater_tenant_id])
    rated_tenant = db.relationship('Tenant', foreign_keys=[rated_tenant_id])

    __table_args__ = (
        # Jedna ocena po ulozi po porudžbini
        db.UniqueConstraint('order_id', 'rater_tenant_id', name='uq_rating_order_rater'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'order_number': self.order.order_number if self.order else None,
            'rating_role': self.rating_role,
            'rating_type': self.rating_type.value,
            'comment': self.comment,
            'created_at': self.created_at.isoformat(),
        }
```

**Agregirana statistika ratinga - Cache u Tenant modelu:**

```python
# Dodati u Tenant model (ili kreirati TenantRatingStats tabelu):
supplier_positive_ratings = db.Column(db.Integer, default=0)
supplier_negative_ratings = db.Column(db.Integer, default=0)
buyer_positive_ratings = db.Column(db.Integer, default=0)
buyer_negative_ratings = db.Column(db.Integer, default=0)

@property
def supplier_rating_score(self):
    """Procenat pozitivnih ocena kao dobavljač (0-100)."""
    total = self.supplier_positive_ratings + self.supplier_negative_ratings
    if total == 0:
        return None  # Nema ocena
    return round((self.supplier_positive_ratings / total) * 100)

@property
def buyer_rating_score(self):
    """Procenat pozitivnih ocena kao kupac (0-100)."""
    total = self.buyer_positive_ratings + self.buyer_negative_ratings
    if total == 0:
        return None
    return round((self.buyer_positive_ratings / total) * 100)
```

**Endpoint za ocenjivanje:**

```python
@bp.route('/api/marketplace/order/<int:order_id>/rate', methods=['POST'])
@login_required
def rate_order(order_id):
    """
    Oceni drugu stranu nakon završene transakcije.

    Može se oceniti samo jednom, samo ako je COMPLETED.
    """
    order = PartOrderRequest.query.get_or_404(order_id)

    if order.status != PartOrderStatus.COMPLETED:
        return jsonify({'error': 'Možete oceniti samo završene transakcije'}), 400

    # Odredi ko ocenjuje koga
    if current_user.tenant_id == order.buyer_tenant_id:
        rating_role = 'buyer'
        rated_tenant_id = order.supplier_tenant_id
    elif current_user.tenant_id == order.supplier_tenant_id:
        rating_role = 'supplier'
        rated_tenant_id = order.buyer_tenant_id
    else:
        return jsonify({'error': 'Nemate pristup'}), 403

    # Proveri da li već postoji ocena
    existing = MarketplaceRating.query.filter_by(
        order_id=order.id,
        rater_tenant_id=current_user.tenant_id
    ).first()

    if existing:
        return jsonify({'error': 'Već ste ocenili ovu transakciju'}), 400

    data = request.get_json()
    rating_type = RatingType.POSITIVE if data.get('positive', True) else RatingType.NEGATIVE

    rating = MarketplaceRating(
        order_id=order.id,
        rater_tenant_id=current_user.tenant_id,
        rater_user_id=current_user.id,
        rated_tenant_id=rated_tenant_id,
        rating_role=rating_role,
        rating_type=rating_type,
        comment=data.get('comment', '').strip()[:500],  # Max 500 chars
    )
    db.session.add(rating)

    # Ažuriraj cache na rated_tenant
    rated_tenant = Tenant.query.get(rated_tenant_id)
    if rating_role == 'buyer':
        # Kupac ocenjuje dobavljača
        if rating_type == RatingType.POSITIVE:
            rated_tenant.supplier_positive_ratings += 1
        else:
            rated_tenant.supplier_negative_ratings += 1
    else:
        # Dobavljač ocenjuje kupca
        if rating_type == RatingType.POSITIVE:
            rated_tenant.buyer_positive_ratings += 1
        else:
            rated_tenant.buyer_negative_ratings += 1

    db.session.commit()

    return jsonify({'success': True})
```

**Prikaz ratinga:**

- **Pre transakcije (kupac vidi):** supplier_rating_score pored cene artikla
- **Pre potvrde (dobavljač vidi):** buyer_rating_score kupca
- **U listi ocena:** Sve ocene sa komentarima

---

### 10.15 Omiljeni Dobavljači (Favorites) ⭐ NOVO

Tenant može da označi dobavljača kao omiljenog. Favoriti imaju prioritet u prikazu.

**Model: TenantFavoriteSupplier**

```python
class TenantFavoriteSupplier(db.Model):
    """Omiljeni dobavljači tenanta - prioritet u prikazu."""
    __tablename__ = 'tenant_favorite_supplier'

    id = db.Column(db.Integer, primary_key=True)

    # Ko ima favorita
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Ko je favorit (dobavljač)
    supplier_tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Kada dodat
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_id = db.Column(db.Integer, db.ForeignKey('tenant_user.id'))

    # Relacije
    tenant = db.relationship('Tenant', foreign_keys=[tenant_id], backref='favorite_suppliers')
    supplier_tenant = db.relationship('Tenant', foreign_keys=[supplier_tenant_id])

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'supplier_tenant_id', name='uq_tenant_favorite_supplier'),
    )
```

**Endpoints:**

```python
@bp.route('/api/marketplace/favorites', methods=['GET'])
@login_required
def list_favorites():
    """Lista omiljenih dobavljača."""
    favorites = TenantFavoriteSupplier.query.filter_by(
        tenant_id=current_user.tenant_id
    ).all()

    return jsonify([{
        'supplier_id': f.supplier_tenant_id,
        'supplier_name': f.supplier_tenant.name,
        'supplier_rating': f.supplier_tenant.supplier_rating_score,
        'created_at': f.created_at.isoformat(),
    } for f in favorites])


@bp.route('/api/marketplace/favorites/<int:supplier_id>', methods=['POST'])
@login_required
def add_favorite(supplier_id):
    """Dodaj dobavljača u favorite."""
    existing = TenantFavoriteSupplier.query.filter_by(
        tenant_id=current_user.tenant_id,
        supplier_tenant_id=supplier_id
    ).first()

    if existing:
        return jsonify({'error': 'Već je u favoritima'}), 400

    fav = TenantFavoriteSupplier(
        tenant_id=current_user.tenant_id,
        supplier_tenant_id=supplier_id,
        created_by_id=current_user.id,
    )
    db.session.add(fav)
    db.session.commit()

    return jsonify({'success': True})


@bp.route('/api/marketplace/favorites/<int:supplier_id>', methods=['DELETE'])
@login_required
def remove_favorite(supplier_id):
    """Ukloni dobavljača iz favorita."""
    fav = TenantFavoriteSupplier.query.filter_by(
        tenant_id=current_user.tenant_id,
        supplier_tenant_id=supplier_id
    ).first()

    if not fav:
        return jsonify({'error': 'Nije u favoritima'}), 404

    db.session.delete(fav)
    db.session.commit()

    return jsonify({'success': True})
```

---

### 10.16 Lokacija i Blizina ⭐ NOVO

Za sortiranje po blizini potrebna je lokacija (grad) tenanta.

**Dodati u Tenant model:**

```python
# Lokacija za izračun blizine
city = db.Column(db.String(100))  # Beograd, Novi Sad, Niš...
latitude = db.Column(db.Float)     # Opciono za tačnije računanje
longitude = db.Column(db.Float)
```

**Lista gradova u Srbiji sa koordinatama** (za dropdown i distance calculation):

```python
SERBIAN_CITIES = {
    'Beograd': (44.8176, 20.4633),
    'Novi Sad': (45.2551, 19.8448),
    'Niš': (43.3209, 21.8958),
    'Kragujevac': (44.0128, 20.9114),
    'Subotica': (46.1003, 19.6658),
    'Zrenjanin': (45.3816, 20.3903),
    'Pančevo': (44.8708, 20.6403),
    'Čačak': (43.8914, 20.3497),
    'Novi Pazar': (43.1367, 20.5122),
    'Kraljevo': (43.7258, 20.6897),
    # ... ostali gradovi
}

def calculate_distance(city1: str, city2: str) -> float:
    """Računa udaljenost između dva grada u km (Haversine formula)."""
    from math import radians, sin, cos, sqrt, atan2

    if city1 not in SERBIAN_CITIES or city2 not in SERBIAN_CITIES:
        return 9999  # Nepoznat grad = maksimalna udaljenost

    lat1, lon1 = SERBIAN_CITIES[city1]
    lat2, lon2 = SERBIAN_CITIES[city2]

    R = 6371  # Radius Zemlje u km

    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))

    return R * c  # Udaljenost u km
```

---

### 10.17 Poboljšani Matching Algoritam ⭐ KRITIČNO

Redosled sortiranja rezultata:

```
1. FAVORITI PRVO - Ako je dobavljač u favoritima kupca
2. NAJBOLJI RATING - Viši procenat pozitivnih ocena
3. NAJBLIŽI - Manja udaljenost (isti grad = 0)
4. NAJNIŽA CENA - Ako je sve ostalo isto
```

**Ažurirani algoritam:**

```python
def find_marketplace_matches(
    brand: str,
    model: str,
    part_category: str = None,
    buyer_tenant_id: int = None,
    buyer_city: str = None,
    limit: int = 20
) -> list:
    """
    Traži matchove u aktivnim cenovnicima dobavljača.

    Sortiranje:
    1. Favoriti kupca (uvek na vrhu)
    2. Najbolji supplier rating (%)
    3. Najbliži geografski
    4. Najniža cena

    Returns: Lista matchova sa rating-om, distancom i favorite flagom
    """
    from sqlalchemy import case, func

    # Dohvati favorite kupca
    favorite_ids = []
    if buyer_tenant_id:
        favorites = TenantFavoriteSupplier.query.filter_by(
            tenant_id=buyer_tenant_id
        ).all()
        favorite_ids = [f.supplier_tenant_id for f in favorites]

    # Base query
    query = db.session.query(
        SupplierPriceListItem,
        SupplierPriceList,
        Tenant
    ).join(
        SupplierPriceList,
        SupplierPriceListItem.price_list_id == SupplierPriceList.id
    ).join(
        Tenant,
        SupplierPriceList.supplier_tenant_id == Tenant.id
    ).filter(
        SupplierPriceList.status == PriceListStatus.ACTIVE,
        SupplierPriceListItem.is_active == True,
        SupplierPriceListItem.in_stock == True,
        db.func.lower(SupplierPriceListItem.brand) == brand.lower()
    )

    if model:
        query = query.filter(
            db.func.lower(SupplierPriceListItem.model).contains(model.lower())
        )

    if part_category:
        query = query.filter(SupplierPriceListItem.part_category == part_category)

    # Dohvati sve matchove
    raw_results = query.all()

    # Enrichuj sa dodatnim podacima i sortiraj
    enriched = []
    for item, price_list, supplier in raw_results:
        # Da li je favorit
        is_favorite = supplier.id in favorite_ids

        # Rating score (0-100, None ako nema)
        rating_score = supplier.supplier_rating_score or 0
        total_ratings = supplier.supplier_positive_ratings + supplier.supplier_negative_ratings

        # Distanca
        distance = 9999
        if buyer_city and supplier.city:
            distance = calculate_distance(buyer_city, supplier.city)

        enriched.append({
            'item': item,
            'supplier': supplier,
            'price_list': price_list,
            'is_favorite': is_favorite,
            'rating_score': rating_score,
            'total_ratings': total_ratings,
            'distance_km': distance,
            'price': float(item.price),
        })

    # Sortiraj: favoriti → rating → distanca → cena
    enriched.sort(key=lambda x: (
        not x['is_favorite'],  # Favoriti prvo (False < True, pa negiramo)
        -x['rating_score'],     # Viši rating prvo (negativno za desc)
        x['distance_km'],       # Manja distanca prvo
        x['price'],             # Niža cena prvo
    ))

    # Limitiraj na top N
    enriched = enriched[:limit]

    # Formatiraj za response
    return [{
        'id': r['item'].id,
        'part_name': r['item'].part_name,
        'brand': r['item'].brand,
        'model': r['item'].model,
        'quality_grade': r['item'].quality_grade,
        'is_original': r['item'].is_original,
        'price': r['price'],
        'currency': r['item'].currency,
        'in_stock': r['item'].in_stock,
        'lead_time_days': r['item'].lead_time_days,
        # Dodatni podaci za prikaz
        'supplier_rating': r['rating_score'] if r['total_ratings'] > 0 else None,
        'supplier_total_ratings': r['total_ratings'],
        'supplier_city': r['supplier'].city,
        'distance_km': round(r['distance_km']) if r['distance_km'] < 9999 else None,
        'is_favorite': r['is_favorite'],
        # NE uključuje: supplier ime, kontakt, itd. (pre potvrde)
    } for r in enriched]
```

**UI Prikaz u rezultatima:**

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 🛒 SUPPLIER MARKETPLACE                                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ ⭐ Display iPhone 12 Pro OLED Original                                  │
│    Cena: 12.500 RSD  │  ⭐ Favorit  │  Rating: 95% (42)  │  Beograd     │
│    [PORUČI]  [UKLONI IZ FAVORITA]                                       │
│                                                                         │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━│
│                                                                         │
│ Display iPhone 12 Pro LCD AAA                                           │
│    Cena: 8.000 RSD  │  Rating: 87% (15)  │  Novi Sad (80 km)           │
│    [PORUČI]  [DODAJ U FAVORITE]                                         │
│                                                                         │
│ Display iPhone 12 Pro LCD                                               │
│    Cena: 8.000 RSD  │  Rating: 72% (8)  │  Niš (238 km)                │
│    [PORUČI]  [DODAJ U FAVORITE]                                         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Legenda:**
- ⭐ = Favorit dobavljač (uvek na vrhu ako ima isti artikal)
- Rating: XX% (N) = procenat pozitivnih ocena (ukupan broj ocena)
- Grad (XX km) = lokacija dobavljača i udaljenost

---

### 10.18 Prikaz Ratinga Kupca Dobavljaču

Pre nego što dobavljač potvrdi porudžbinu, vidi rating kupca:

```python
def to_supplier_dict(self):
    """Za dobavljača - prikazuje detalje kupca samo ako je CONFIRMED."""
    data = {
        'id': self.id,
        'order_number': self.order_number,
        'status': self.status.value,
        'quantity': self.quantity,
        'total_amount': float(self.total_amount),
        # ...
    }

    # UVEK prikaži rating kupca (i pre potvrde!)
    data['buyer_rating'] = {
        'score': self.buyer_tenant.buyer_rating_score,
        'positive': self.buyer_tenant.buyer_positive_ratings,
        'negative': self.buyer_tenant.buyer_negative_ratings,
    }

    # Prikaži kontakt detalje kupca SAMO nakon potvrde
    if self.status in (PartOrderStatus.CONFIRMED, PartOrderStatus.COMPLETED):
        data['buyer'] = {
            'name': self.buyer_tenant.name,
            'company_name': self.buyer_tenant.company_name,
            'address': self.buyer_tenant.address,
            'city': self.buyer_tenant.city,
            'phone': self.buyer_tenant.phone,
            'email': self.buyer_tenant.email,
        }

    return data
```

**UI za dobavljača pri odobrenju:**

```
┌─────────────────────────────────────────────────────────────────────────┐
│ NOVA PORUDŽBINA: MKT-2026-00042                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ Artikal: Display iPhone 12 Pro OLED Original                            │
│ Količina: 1                                                             │
│ Cena: 12.500 RSD                                                        │
│                                                                         │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━│
│                                                                         │
│ KUPAC:                                                                  │
│ Rating: 92% pozitivnih (25 ukupno)                                      │
│ 👍 23 pozitivnih  │  👎 2 negativnih                                    │
│                                                                         │
│ ⚠️ Kontakt detalji će biti dostupni nakon potvrde                      │
│                                                                         │
│ [POTVRDI PORUDŽBINU]    [ODBIJ]                                         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### 10.19 Dodatne Migracije (Rating, Favoriti, Dostava)

| Verzija | Fajl | Opis |
|---------|------|------|
| v341 | `v341_create_marketplace_rating.py` | MarketplaceRating |
| v342 | `v342_create_tenant_favorites.py` | TenantFavoriteSupplier |
| v343 | `v343_add_tenant_location.py` | city, lat, lng u Tenant |
| v344 | `v344_add_tenant_rating_cache.py` | Rating cache polja u Tenant |
| v345 | `v345_create_delivery_options.py` | SupplierDeliveryOption |
| v346 | `v346_add_order_delivery_fields.py` | Delivery polja u PartOrderRequest |

---

### 10.20 CHECKLIST za FAZU 10

**Modeli (Cenovnici):**
- [ ] Kreiraj SupplierPriceList + SupplierPriceListItem modele
- [ ] Kreiraj migraciju v338
- [ ] Kreiraj PartOrderRequest + PartOrderMessage modele
- [ ] Kreiraj migraciju v339
- [ ] Kreiraj MarketplaceSettings model
- [ ] Kreiraj migraciju v340

**Modeli (Rating i Favoriti):**
- [ ] Kreiraj MarketplaceRating model
- [ ] Kreiraj migraciju v341
- [ ] Kreiraj TenantFavoriteSupplier model
- [ ] Kreiraj migraciju v342
- [ ] Dodaj city, latitude, longitude u Tenant
- [ ] Kreiraj migraciju v343
- [ ] Dodaj rating cache polja u Tenant (supplier_positive_ratings, etc.)
- [ ] Kreiraj migraciju v344

**Cenovnici:**
- [ ] Endpoint za CRUD cenovnika
- [ ] Endpoint za import iz CSV/Excel
- [ ] UI za upravljanje cenovnicima (dobavljač)
- [ ] VERIFIKACIJA: Import 100+ artikala radi

**Matching (sa sortiranjem):**
- [ ] Implementiraj find_marketplace_matches() sa novim sortiranjem
- [ ] Endpoint /api/marketplace/search
- [ ] Widget u servisnom nalogu koji prikazuje matchove
- [ ] VERIFIKACIJA: Favoriti su UVEK na vrhu
- [ ] VERIFIKACIJA: Viši rating dolazi pre nižeg
- [ ] VERIFIKACIJA: Bliži dobavljač dolazi pre daljeg (ista cena/rating)
- [ ] VERIFIKACIJA: Match prikazuje rating i distancu (bez kontakt detalja)

**Porudžbine:**
- [ ] Endpoint za kreiranje porudžbine
- [ ] Endpoint za potvrdu/odbijanje
- [ ] Endpoint za poruke
- [ ] Lista porudžbina za kupca ("Moje porudžbine")
- [ ] Lista porudžbina za dobavljača ("Dolazne porudžbine")
- [ ] VERIFIKACIJA: Pre potvrde - nema kontakt detalja
- [ ] VERIFIKACIJA: Pre potvrde - dobavljač VIDI buyer rating
- [ ] VERIFIKACIJA: Posle potvrde - full detalji + skinuti krediti

**Rating sistem:**
- [ ] Endpoint za ocenjivanje `/api/marketplace/order/<id>/rate`
- [ ] UI za ocenjivanje nakon COMPLETED statusa
- [ ] Prikaz ratinga u rezultatima pretrage
- [ ] Prikaz buyer ratinga dobavljaču pre potvrde
- [ ] Cache ratinga u Tenant modelu se ažurira
- [ ] VERIFIKACIJA: Ocena može biti samo jednom
- [ ] VERIFIKACIJA: Ocena samo za COMPLETED porudžbine

**Favoriti:**
- [ ] Endpoint za dodavanje/uklanjanje favorita
- [ ] Endpoint za listu favorita
- [ ] UI dugme "Dodaj u favorite" / "Ukloni iz favorita"
- [ ] VERIFIKACIJA: Favorit dobavljač je UVEK u top 3

**Lokacija/Blizina:**
- [ ] Dropdown za izbor grada pri registraciji/edit tenanta
- [ ] Haversine formula za računanje udaljenosti
- [ ] Prikaz grada i distance u rezultatima
- [ ] VERIFIKACIJA: Bliži dobavljač ima prednost

**Krediti:**
- [ ] MarketplaceSettings u SHUB admin panelu (Sidebar → Paketi)
- [ ] Integracija sa postojećim credit sistemom (deduct_credits)
- [ ] VERIFIKACIJA: Krediti se skidaju tačno po podešavanju (0.5 + 0.5)
- [ ] VERIFIKACIJA: Bez kredita = ne može potvrditi

**Načini Dostave:**
- [ ] Kreiraj SupplierDeliveryOption model
- [ ] Kreiraj migraciju v345
- [ ] Dodaj delivery polja u PartOrderRequest
- [ ] Kreiraj migraciju v346
- [ ] Endpoint za CRUD delivery opcija
- [ ] UI za podešavanje načina dostave (dobavljač admin panel)
- [ ] Izbor dostave pri potvrdi porudžbine
- [ ] Prikaz procenjenog datuma isporuke tenantu
- [ ] VERIFIKACIJA: Potvrda zahteva izbor dostave
- [ ] VERIFIKACIJA: Tenant vidi očekivani datum

**Audit:**
- [ ] Sve akcije se loguju
- [ ] Poruke se čuvaju sa timestamp-om
- [ ] Status promene su vidljive u istoriji
- [ ] Sve ocene se čuvaju sa komentarima

---

---

## FRONTEND SPECIFIKACIJA ⭐ KOMPLETNO

### Tehnologija

| Stack | Opis |
|-------|------|
| **Template Engine** | Jinja2 |
| **CSS Framework** | Tailwind CSS (CDN) |
| **JS Framework** | Alpine.js (CDN) |
| **Icons** | Heroicons / Lucide |
| **Charts** | Chart.js 4.x |
| **Tables** | Custom sa sortiranjem/filtriranjem |

### Folder Struktura

```
app/templates/
├── tenant/
│   ├── inventory/           # NOVO - Lager stranice
│   │   ├── goods_list.html      # Lista robe
│   │   ├── goods_form.html      # Dodaj/izmeni robu
│   │   ├── parts_list.html      # Lista rezervnih delova
│   │   ├── parts_form.html      # Dodaj/izmeni deo
│   │   ├── stock_overview.html  # Pregled stanja po lokacijama
│   │   ├── stock_card.html      # Lager kartica (history)
│   │   ├── receive_form.html    # Prijem robe
│   │   ├── import.html          # Import iz Excel-a
│   │   └── low_stock.html       # Artikli ispod min. nivoa
│   │
│   ├── suppliers/           # NOVO - Dobavljači
│   │   ├── list.html            # Lista dobavljača
│   │   ├── form.html            # Dodaj/izmeni dobavljača
│   │   ├── detail.html          # Detalji sa istorijom
│   │   └── buyback/
│   │       ├── list.html        # Lista otkupnih ugovora
│   │       ├── form.html        # Kreiranje otkupa
│   │       ├── detail.html      # Pregled ugovora
│   │       └── print.html       # PDF za štampu
│   │
│   ├── transfers/           # NOVO - Interni transferi
│   │   ├── list.html            # Lista zahteva (dolazni/odlazni)
│   │   ├── create.html          # Kreiranje zahteva
│   │   ├── detail.html          # Detalji sa akcijama
│   │   └── stock_lookup.html    # Pregled stanja drugih lokacija
│   │
│   ├── marketplace/         # NOVO - B2B Marketplace
│   │   ├── search.html          # Pretraga delova
│   │   ├── my_orders.html       # Moje porudžbine (tenant)
│   │   ├── order_detail.html    # Detalji + chat
│   │   ├── favorites.html       # Omiljeni dobavljači
│   │   └── rate_order.html      # Modal za ocenu
│   │
│   ├── pos/                 # Postojeće + izmene
│   │   ├── register.html        # Kasa (postojeće)
│   │   ├── sell_modal.html      # IZMENA: dodati goods + services
│   │   ├── daily_report.html    # Dnevni izveštaj
│   │   └── receipts.html        # Istorija računa
│   │
│   ├── tickets/             # Postojeće + izmene
│   │   ├── list.html            # Lista naloga (postojeće)
│   │   ├── detail.html          # IZMENA: widget za dostupne delove
│   │   └── add_part_modal.html  # NOVO: modal sa 3 izvora delova
│   │
│   ├── services/            # NOVO - Usluge (ServiceItem)
│   │   ├── list.html            # Lista usluga
│   │   └── form.html            # Dodaj/izmeni uslugu
│   │
│   └── reports/             # NOVO - Izveštaji
│       ├── daily_sales.html     # Dnevni pazar
│       ├── stock_movements.html # Pregled pokreta
│       ├── profit_by_ticket.html # Profit po nalogu
│       └── abc_analysis.html    # Pareto 80/20
│
├── supplier/                # Panel za dobavljače
│   ├── price_lists/
│   │   ├── list.html            # Moji cenovnici
│   │   ├── form.html            # Kreiranje/izmena
│   │   ├── import.html          # Import iz CSV/Excel
│   │   └── items.html           # Stavke cenovnika
│   │
│   ├── orders/
│   │   ├── incoming.html        # Dolazne porudžbine
│   │   ├── detail.html          # Detalji + potvrda + dostava
│   │   └── history.html         # Istorija
│   │
│   ├── delivery/
│   │   └── options.html         # Podešavanje načina dostave
│   │
│   └── ratings/
│       └── my_ratings.html      # Moje ocene (primljene)
│
└── admin/                   # SHUB Admin panel
    ├── marketplace/
    │   └── settings.html        # Cena kredita za transakcije
    └── reports/
        └── marketplace_stats.html # Statistika marketplace-a
```

---

### STRANICE PO FAZAMA

#### FAZA 1-2: Lager Osnova

**1. Lista Robe** (`/inventory/goods`)
```
┌─────────────────────────────────────────────────────────────────────────┐
│ ROBA NA STANJU                                    [+ Dodaj] [Import]   │
├─────────────────────────────────────────────────────────────────────────┤
│ 🔍 Pretraga: [____________]  Kategorija: [Sve ▼]  Lokacija: [Sve ▼]   │
├─────────────────────────────────────────────────────────────────────────┤
│ ⚠️ Low stock: 5 artikala                                               │
├─────────────────────────────────────────────────────────────────────────┤
│ Barkod    │ Naziv              │ Kategorija │ Stanje │ Cena   │ Akcije │
├───────────┼────────────────────┼────────────┼────────┼────────┼────────┤
│ 123456789 │ Futrola iPhone 14  │ Futrole    │ 15     │ 1.200  │ ✏️ 📊  │
│ 987654321 │ Zaštitno staklo    │ Stakla     │ 3 ⚠️  │ 800    │ ✏️ 📊  │
└───────────┴────────────────────┴────────────┴────────┴────────┴────────┘
```

**2. Forma za Robu** (`/inventory/goods/add` | `/inventory/goods/<id>/edit`)
```
┌─────────────────────────────────────────────────────────────────────────┐
│ DODAJ NOVU ROBU                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ Barkod: [____________] [Skeniraj]                                       │
│                                                                         │
│ Naziv: [____________________________]                                   │
│                                                                         │
│ Kategorija: [Izaberi ▼]  SKU: [________]                               │
│                                                                         │
│ ─────────────────────────────────────────────────────────────          │
│ CENE                                                                    │
│ Nabavna: [______] RSD    Prodajna: [______] RSD                        │
│ Marža: 25% (automatski)                                                │
│                                                                         │
│ ─────────────────────────────────────────────────────────────          │
│ ZALIHE                                                                  │
│ Početno stanje: [___]    Min. nivo: [___]                              │
│ Lokacija: [Glavna lokacija ▼]                                          │
│                                                                         │
│ ─────────────────────────────────────────────────────────────          │
│ FISKALNO                                                                │
│ PDV oznaka: [A - 20% ▼]    Jedinica: [kom ▼]                           │
│                                                                         │
│ [SAČUVAJ]  [Otkaži]                                                    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**3. Pregled Stanja po Lokacijama** (`/inventory/stock-overview/<item_type>/<id>`)
```
┌─────────────────────────────────────────────────────────────────────────┐
│ STANJE: Futrola iPhone 14 Pro Max                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ UKUPNO NA SVIM LOKACIJAMA: 45 kom                                      │
│                                                                         │
│ ┌─────────────────────────────────────────────────────────────────┐    │
│ │ Lokacija          │ Stanje │ Min │ Status      │ Akcije        │    │
│ ├───────────────────┼────────┼─────┼─────────────┼───────────────┤    │
│ │ Glavni servis     │ 25     │ 5   │ ✅ OK       │ [Prijem] [+]  │    │
│ │ Poslovnica Centar │ 15     │ 5   │ ✅ OK       │ [Prijem] [+]  │    │
│ │ Poslovnica NBG    │ 5      │ 5   │ ⚠️ Low      │ [Prijem] [+]  │    │
│ └───────────────────┴────────┴─────┴─────────────┴───────────────┘    │
│                                                                         │
│ [Lager Kartica]  [Korekcija (Admin)]                                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**4. Lager Kartica** (`/inventory/stock-card/<item_type>/<id>`)
```
┌─────────────────────────────────────────────────────────────────────────┐
│ LAGER KARTICA: Futrola iPhone 14 Pro Max                               │
├─────────────────────────────────────────────────────────────────────────┤
│ Lokacija: [Sve ▼]  Period: [01.01.2026] - [06.02.2026]                 │
├─────────────────────────────────────────────────────────────────────────┤
│ Datum       │ Tip         │ Količina │ Stanje │ Referenca    │ Korisnik │
├─────────────┼─────────────┼──────────┼────────┼──────────────┼──────────┤
│ 06.02.2026  │ SALE        │ -1       │ 45     │ RČ-2026-0124 │ Marko    │
│ 05.02.2026  │ RECEIVE     │ +10      │ 46     │ UF-2026-0015 │ Ana      │
│ 03.02.2026  │ USE_TICKET  │ -2       │ 36     │ SN-2026-0089 │ Petar    │
│ 01.02.2026  │ INITIAL     │ +38      │ 38     │ Import       │ Admin    │
└─────────────┴─────────────┴──────────┴────────┴──────────────┴──────────┘
```

---

#### FAZA 3: Dobavljači i Otkup

**5. Lista Dobavljača** (`/suppliers`)
```
┌─────────────────────────────────────────────────────────────────────────┐
│ DOBAVLJAČI                                      [+ Firma] [+ Fizičko]  │
├─────────────────────────────────────────────────────────────────────────┤
│ Tip: [Svi ▼]  Pretraga: [____________]                                 │
├─────────────────────────────────────────────────────────────────────────┤
│ Naziv              │ Tip     │ PIB/JMBG     │ Telefon    │ Akcije      │
├────────────────────┼─────────┼──────────────┼────────────┼─────────────┤
│ Parts Centar DOO   │ 🏢 Firma│ 123456789    │ 011/123456 │ ✏️ 📋       │
│ Marko Marković     │ 👤 Lice │ 0101990...   │ 064/123456 │ ✏️ 📋       │
└────────────────────┴─────────┴──────────────┴────────────┴─────────────┘
```

**6. Otkupni Ugovor - Forma** (`/buyback/add`)
```
┌─────────────────────────────────────────────────────────────────────────┐
│ NOVI OTKUPNI UGOVOR                                                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ PODACI O PRODAVCU                                                       │
│ ─────────────────────────────────────────────────────────────          │
│ Ime i prezime: [____________________] *                                 │
│ JMBG: [_____________] *    Br. LK: [__________] *                      │
│ Adresa: [________________________________] *                            │
│ Grad: [__________]    Telefon: [______________]                        │
│                                                                         │
│ ARTIKLI                                                          [+ Red]│
│ ─────────────────────────────────────────────────────────────          │
│ │ Opis artikla      │ Brand  │ Model    │ IMEI     │ Kol│ Cena  │ ✕   │
│ ├────────────────────┼────────┼──────────┼──────────┼────┼───────┼─────┤
│ │ Display iPhone 12  │ Apple  │ iPhone12 │ 123456.. │ 1  │ 8.000 │  ✕  │
│ │ Baterija Samsung   │ Samsung│ S21      │          │ 2  │ 1.500 │  ✕  │
│ └────────────────────┴────────┴──────────┴──────────┴────┴───────┴─────┘
│                                                                         │
│ UKUPNO: 11.000 RSD                                                      │
│                                                                         │
│ Način isplate: (●) Gotovina  ( ) Prenos na račun                       │
│ Žiro račun: [____________________] (ako je prenos)                     │
│                                                                         │
│ [SAČUVAJ UGOVOR]                                                        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**7. Otkupni Ugovor - Detalji** (`/buyback/<id>`)
```
┌─────────────────────────────────────────────────────────────────────────┐
│ OTKUPNI UGOVOR: OTK-2026-00015                    Status: 📝 DRAFT     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ PRODAVAC: Marko Marković                                               │
│ JMBG: 0101990123456 │ LK: 123456789 │ Tel: 064/1234567                 │
│ Adresa: Nemanjina 15, Beograd                                          │
│                                                                         │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                                                         │
│ ARTIKLI:                                                                │
│ 1. Display iPhone 12 Pro - Apple - 1 kom - 8.000 RSD                   │
│ 2. Baterija Galaxy S21 - Samsung - 2 kom - 3.000 RSD                   │
│                                                                         │
│ UKUPNO: 11.000 RSD (gotovina)                                          │
│                                                                         │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                                                         │
│ [🖨️ ŠTAMPAJ PDF]  [✍️ POTPIŠI]  [❌ OTKAŽI]                            │
│                                                                         │
│ ℹ️ Po potpisivanju, artikli će biti automatski dodati na lager.        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

#### FAZA 7: POS

**8. POS Prodaja sa Robom i Uslugama** (`/pos/register`)
```
┌─────────────────────────────────────────────────────────────────────────┐
│ KASA - Glavni servis                                   [Zatvori smenu] │
├────────────────────────────────────────┬────────────────────────────────┤
│                                        │                                │
│ 🔍 [Skeniraj ili pretraži...]         │  KORPA                         │
│                                        │  ──────────────────────────    │
│ BRZE KATEGORIJE:                       │  Futrola iPhone 14    1.200    │
│ [Futrole] [Stakla] [Punjači] [Usluge] │  Zaštitno staklo        800    │
│                                        │  Dijagnostika           500    │
│ REZULTATI:                             │  ──────────────────────────    │
│ ┌────────────────────────────────────┐ │                                │
│ │ 📦 Futrola iPhone 14 - 1.200 RSD   │ │  UKUPNO:            2.500 RSD │
│ │ 📦 Futrola iPhone 15 - 1.500 RSD   │ │                                │
│ │ 🔧 Dijagnostika - 500 RSD          │ │  Plaćanje:                     │
│ │ 🔧 Zamena ekrana - 2.000 RSD       │ │  (●) Gotovina  ( ) Kartica    │
│ └────────────────────────────────────┘ │                                │
│                                        │  [     NAPLATI     ]           │
│ 📦 = Roba (GoodsItem)                  │                                │
│ 🔧 = Usluga (ServiceItem)              │                                │
│                                        │                                │
└────────────────────────────────────────┴────────────────────────────────┘
```

---

#### FAZA 9: Transferi

**9. Lista Transfer Zahteva** (`/transfers`)
```
┌─────────────────────────────────────────────────────────────────────────┐
│ TRANSFER ZAHTEVI                                         [+ Novi zahtev]│
├─────────────────────────────────────────────────────────────────────────┤
│ [DOLAZNI] [ODLAZNI]  Status: [Svi ▼]                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ DOLAZNI ZAHTEVI (čekaju moju akciju):                                  │
│ ┌─────────────────────────────────────────────────────────────────┐    │
│ │ TR-2026-00042 │ Od: Centar │ 3 artikla │ ⏳ PENDING │ [Pregledaj]│    │
│ │ TR-2026-00041 │ Od: NBG    │ 1 artikal │ ✅ APPROVED│ [Pošalji]  │    │
│ └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│ ODLAZNI ZAHTEVI (moji zahtevi):                                        │
│ ┌─────────────────────────────────────────────────────────────────┐    │
│ │ TR-2026-00040 │ Ka: Centar │ 2 artikla │ 📦 SHIPPED │ [Čeka prijem]│  │
│ │ TR-2026-00039 │ Ka: NBG    │ 1 artikal │ ✅ RECEIVED│ [Detalji]  │    │
│ └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**10. Kreiranje Transfer Zahteva** (`/transfers/create`)
```
┌─────────────────────────────────────────────────────────────────────────┐
│ NOVI ZAHTEV ZA TRANSFER                                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ Tražim od lokacije: [Poslovnica Centar ▼]                              │
│                                                                         │
│ DOSTUPNI ARTIKLI NA TOJ LOKACIJI:                                      │
│ 🔍 [Pretraži...]                                                       │
│ ┌─────────────────────────────────────────────────────────────────┐    │
│ │ ☐ Display iPhone 12 Pro OLED     │ Qty: 5  │ [Traži: 1]         │    │
│ │ ☐ Baterija iPhone 12             │ Qty: 10 │ [Traži: 2]         │    │
│ │ ☐ Charging port iPhone 12        │ Qty: 3  │ [Traži: 1]         │    │
│ └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│ Razlog: [Hitno potrebno za nalog SN-2026-0089__________]               │
│                                                                         │
│ [POŠALJI ZAHTEV]                                                        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

#### FAZA 10: Marketplace

**11. Dostupni Delovi u Servisnom Nalogu** (`/tickets/<id>` - widget)
```
┌─────────────────────────────────────────────────────────────────────────┐
│ DOSTUPNI DELOVI ZA: iPhone 12 Pro - Display                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ 📍 MOJA LOKACIJA (Glavni servis)                                       │
│ ┌──────────────────────────────────────────────────────────────────┐   │
│ │ Display iPhone 12 Pro OLED Original    Qty: 3    [DODAJ NA NALOG]│   │
│ │ Display iPhone 12 Pro LCD AAA          Qty: 5    [DODAJ NA NALOG]│   │
│ └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│ 🏢 DRUGE LOKACIJE                                                      │
│ ┌──────────────────────────────────────────────────────────────────┐   │
│ │ 📍 Poslovnica Centar                                             │   │
│ │    Display iPhone 12 Pro OLED    Qty: 2    [ZATRAŽI TRANSFER]    │   │
│ └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│ 🛒 SUPPLIER MARKETPLACE                                                │
│ ┌──────────────────────────────────────────────────────────────────┐   │
│ │ ⭐ Display iPhone 12 Pro OLED Original                           │   │
│ │    12.500 RSD │ ⭐ Favorit │ Rating: 95% │ Beograd   [PORUČI]    │   │
│ │                                                                   │   │
│ │ Display iPhone 12 Pro LCD AAA                                     │   │
│ │    8.000 RSD │ Rating: 87% │ Novi Sad (80km)        [PORUČI]     │   │
│ └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**12. Moje Marketplace Porudžbine** (`/marketplace/orders`)
```
┌─────────────────────────────────────────────────────────────────────────┐
│ MOJE PORUDŽBINE                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│ Status: [Svi ▼]                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│ Broj         │ Artikal                │ Cena    │ Status    │ Akcije   │
├──────────────┼────────────────────────┼─────────┼───────────┼──────────┤
│ MKT-2026-042 │ Display iPhone 12 Pro  │ 12.500  │ ✅ POTVRĐ │ Detalji  │
│ MKT-2026-041 │ Baterija Galaxy S21    │ 3.000   │ ⏳ ČEKA   │ Detalji  │
│ MKT-2026-040 │ Charging port iPhone   │ 1.500   │ ✔️ ZAVRŠ  │ [Oceni]  │
└──────────────┴────────────────────────┴─────────┴───────────┴──────────┘
```

**13. Detalji Porudžbine sa Chat-om** (`/marketplace/orders/<id>`)
```
┌─────────────────────────────────────────────────────────────────────────┐
│ PORUDŽBINA: MKT-2026-00042                          Status: ✅ POTVRĐENO│
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ ARTIKAL: Display iPhone 12 Pro OLED Original                           │
│ Količina: 1  │  Cena: 12.500 RSD                                       │
│                                                                         │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                                                         │
│ DOSTAVA:                                                                │
│ 📦 Kurirska služba                                                      │
│ 📅 Očekivani datum: 08.02.2026.                                        │
│ 💰 Cena dostave: 300 RSD                                               │
│                                                                         │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                                                         │
│ DOBAVLJAČ:                                                              │
│ Servis Parts DOO  │  Bulevar Mihajla Pupina 10, Novi Sad               │
│ 📞 021/555-1234   │  📧 info@servisparts.rs                            │
│                                                                         │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                                                         │
│ PORUKE:                                                                 │
│ ┌─────────────────────────────────────────────────────────────────┐    │
│ │ 👤 Vi (05.02. 14:30): Može li preuzimanje lično?                │    │
│ │ 🏢 Dobavljač (05.02. 14:45): Da, od 9-17h radnim danima.        │    │
│ └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│ [Unesite poruku...________________________] [Pošalji]                  │
│                                                                         │
│ [OZNAČI KAO PRIMLJENO]                                                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**14. Modal za Ocenjivanje** (posle COMPLETED statusa)
```
┌─────────────────────────────────────────────────────────────────────────┐
│ OCENITE TRANSAKCIJU: MKT-2026-00042                              [✕]   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ Kako biste ocenili ovu transakciju?                                    │
│                                                                         │
│     [  👍 POZITIVNO  ]     [  👎 NEGATIVNO  ]                          │
│                                                                         │
│ Komentar (opciono):                                                     │
│ ┌─────────────────────────────────────────────────────────────────┐    │
│ │ Brza dostava, artikal kao što je opisano. Preporučujem!         │    │
│ └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│ [POŠALJI OCENU]                                                         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**15. Omiljeni Dobavljači** (`/marketplace/favorites`)
```
┌─────────────────────────────────────────────────────────────────────────┐
│ OMILJENI DOBAVLJAČI                                                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ ⭐ Servis Parts DOO                                                     │
│    Rating: 95% (42 ocene)  │  Beograd  │  [Ukloni iz favorita]         │
│                                                                         │
│ ⭐ Mobile Delovi                                                        │
│    Rating: 88% (15 ocena)  │  Novi Sad │  [Ukloni iz favorita]         │
│                                                                         │
│ ℹ️ Favoriti se uvek prikazuju na vrhu rezultata pretrage.              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### SUPPLIER PANEL STRANICE

**16. Moji Cenovnici** (`/supplier/price-lists`)
```
┌─────────────────────────────────────────────────────────────────────────┐
│ MOJI CENOVNICI                                          [+ Novi cenovnik]│
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ ┌─────────────────────────────────────────────────────────────────┐    │
│ │ Ekrani za iPhone                                                │    │
│ │ 45 artikala  │  Status: ✅ AKTIVAN  │  Poslednji import: 01.02. │    │
│ │ [Stavke]  [Import CSV]  [Pauziraj]                              │    │
│ └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│ ┌─────────────────────────────────────────────────────────────────┐    │
│ │ Baterije Samsung                                                │    │
│ │ 28 artikala  │  Status: 📝 DRAFT   │  Poslednji import: -      │    │
│ │ [Stavke]  [Import CSV]  [Aktiviraj]                             │    │
│ └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**17. Dolazne Porudžbine - Potvrda sa Dostavom** (`/supplier/orders/incoming`)
```
┌─────────────────────────────────────────────────────────────────────────┐
│ NOVA PORUDŽBINA: MKT-2026-00042                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ Artikal: Display iPhone 12 Pro OLED Original                            │
│ Količina: 1  │  Cena: 12.500 RSD                                       │
│                                                                         │
│ KUPAC:                                                                  │
│ Rating: 92% pozitivnih (25 ukupno)                                     │
│ 👍 23 pozitivnih  │  👎 2 negativnih                                   │
│                                                                         │
│ ⚠️ Kontakt detalji će biti dostupni nakon potvrde                      │
│                                                                         │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                                                         │
│ IZABERITE NAČIN DOSTAVE:                                                │
│                                                                         │
│ (●) Kurirska služba - 1-2 dana - 300 RSD                               │
│ ( ) Lična dostava - Isti dan - 500 RSD                                 │
│ ( ) Preuzimanje u magacinu - Odmah - Besplatno                         │
│                                                                         │
│ Procenjeni datum isporuke: 08.02.2026.                                  │
│                                                                         │
│ [POTVRDI PORUDŽBINU]    [ODBIJ]                                         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**18. Podešavanje Načina Dostave** (`/supplier/delivery-options`)
```
┌─────────────────────────────────────────────────────────────────────────┐
│ NAČINI DOSTAVE                                               [+ DODAJ] │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ ⭐ Kurirska služba (default)                                           │
│    Rok: 1-2 dana  │  Cena: 300 RSD  │  Besplatno iznad: 5.000 RSD      │
│    [IZMENI]  [OBRIŠI]                                                   │
│                                                                         │
│ Lična dostava                                                           │
│    Rok: Isti dan  │  Cena: 500 RSD  │  Samo za Beograd                 │
│    [IZMENI]  [OBRIŠI]  [POSTAVI KAO DEFAULT]                           │
│                                                                         │
│ Preuzimanje u magacinu                                                  │
│    Rok: Odmah  │  Besplatno                                            │
│    [IZMENI]  [OBRIŠI]  [POSTAVI KAO DEFAULT]                           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### IZVEŠTAJI

**19. Dnevni Pazar** (`/reports/daily-sales`)
```
┌─────────────────────────────────────────────────────────────────────────┐
│ DNEVNI PAZAR                                                            │
├─────────────────────────────────────────────────────────────────────────┤
│ Datum: [06.02.2026]  Lokacija: [Sve ▼]                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ ┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐    │
│ │  UKUPNO PAZARA    │  │  GOTOVINA         │  │  KARTICA          │    │
│ │  125.500 RSD      │  │  85.500 RSD       │  │  40.000 RSD       │    │
│ │  32 računa        │  │  20 računa        │  │  12 računa        │    │
│ └───────────────────┘  └───────────────────┘  └───────────────────┘    │
│                                                                         │
│ PO KATEGORIJAMA:                                                        │
│ ┌────────────────────────────────────────────────────────────────┐     │
│ │ Roba (GoodsItem)      │ 65.500 RSD  │ ████████████████░░░ 52%  │     │
│ │ Usluge (ServiceItem)  │ 60.000 RSD  │ ███████████████░░░░ 48%  │     │
│ └────────────────────────────────────────────────────────────────┘     │
│                                                                         │
│ [Štampaj]  [Export CSV]                                                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**20. Profit po Nalogu** (`/reports/ticket-profit`)
```
┌─────────────────────────────────────────────────────────────────────────┐
│ PROFIT PO SERVISNIM NALOZIMA                                           │
├─────────────────────────────────────────────────────────────────────────┤
│ Period: [01.02.2026] - [06.02.2026]                                    │
├─────────────────────────────────────────────────────────────────────────┤
│ Nalog        │ Naplata  │ Nabavka delova │ Profit   │ Marža  │         │
├──────────────┼──────────┼────────────────┼──────────┼────────┼─────────┤
│ SN-2026-0089 │ 15.000   │ 8.000          │ 7.000    │ 46.7%  │ Detalji │
│ SN-2026-0088 │ 8.500    │ 3.500          │ 5.000    │ 58.8%  │ Detalji │
│ SN-2026-0087 │ 12.000   │ 6.000          │ 6.000    │ 50.0%  │ Detalji │
├──────────────┼──────────┼────────────────┼──────────┼────────┼─────────┤
│ UKUPNO       │ 35.500   │ 17.500         │ 18.000   │ 50.7%  │         │
└──────────────┴──────────┴────────────────┴──────────┴────────┴─────────┘
```

---

### KOMPONENTE (Reusable)

| Komponenta | Fajl | Upotreba |
|------------|------|----------|
| Stock Badge | `_stock_badge.html` | Low/Out of stock indicator |
| Status Badge | `_status_badge.html` | PENDING/CONFIRMED/COMPLETED |
| Rating Stars | `_rating_display.html` | 95% (42) prikaz |
| Empty State | `_empty_state.html` | Kada nema podataka |
| Pagination | `_pagination.html` | Straničenje tabela |
| Search Input | `_search_input.html` | Debounced pretraga |
| Modal Base | `_modal_base.html` | Glassmorphism modal |
| Toast | `_toast.html` | Notifikacije (success/error) |

---

### ALPINE.JS KOMPONENTE

```javascript
// Korpa za POS
Alpine.data('posCart', () => ({
    items: [],
    addItem(item) { ... },
    removeItem(index) { ... },
    get total() { return this.items.reduce((sum, i) => sum + i.price * i.qty, 0) },
    checkout(paymentMethod) { ... }
}))

// Pretraga sa debounce
Alpine.data('searchInput', () => ({
    query: '',
    results: [],
    loading: false,
    async search() {
        if (this.query.length < 2) return;
        this.loading = true;
        this.results = await fetch(`/api/search?q=${this.query}`).then(r => r.json());
        this.loading = false;
    }
}))

// Rating modal
Alpine.data('ratingModal', () => ({
    isPositive: null,
    comment: '',
    submit() { ... }
}))

// Transfer form
Alpine.data('transferForm', () => ({
    sourceLocation: null,
    items: [],
    toggleItem(id, qty) { ... },
    submit() { ... }
}))
```

---

### FRONTEND CHECKLIST

**Lager (FAZE 1-6):**
- [ ] `goods_list.html` - lista robe sa filterima
- [ ] `goods_form.html` - dodaj/izmeni robu
- [ ] `parts_list.html` - lista rezervnih delova
- [ ] `parts_form.html` - dodaj/izmeni deo
- [ ] `stock_overview.html` - stanje po lokacijama
- [ ] `stock_card.html` - lager kartica (istorija)
- [ ] `receive_form.html` - prijem robe
- [ ] `import.html` - import iz Excel-a
- [ ] `low_stock.html` - artikli ispod min. nivoa
- [ ] `services_list.html` - lista usluga
- [ ] `services_form.html` - dodaj/izmeni uslugu

**Dobavljači (FAZA 3):**
- [ ] `suppliers_list.html` - lista dobavljača
- [ ] `supplier_form.html` - dodaj/izmeni
- [ ] `buyback_list.html` - lista otkupnih ugovora
- [ ] `buyback_form.html` - kreiranje otkupa
- [ ] `buyback_detail.html` - pregled + akcije
- [ ] `buyback_print.html` - PDF za štampu

**POS (FAZA 7):**
- [ ] Izmena `register.html` - dodati GoodsItem + ServiceItem
- [ ] `daily_report.html` - dnevni pazar

**Transfer (FAZA 9):**
- [ ] `transfers_list.html` - dolazni/odlazni
- [ ] `transfer_create.html` - kreiranje zahteva
- [ ] `transfer_detail.html` - akcije (approve/ship/receive)

**Marketplace (FAZA 10):**
- [ ] `available_parts_widget.html` - widget u nalogu (3 izvora)
- [ ] `marketplace_search.html` - pretraga delova
- [ ] `my_orders.html` - moje porudžbine
- [ ] `order_detail.html` - detalji + chat
- [ ] `rate_modal.html` - ocenjivanje
- [ ] `favorites.html` - omiljeni dobavljači

**Supplier Panel:**
- [ ] `price_lists.html` - moji cenovnici
- [ ] `price_list_items.html` - stavke
- [ ] `import_price_list.html` - CSV/Excel import
- [ ] `incoming_orders.html` - dolazne porudžbine
- [ ] `order_confirm.html` - potvrda sa dostavom
- [ ] `delivery_options.html` - podešavanje dostave
- [ ] `my_ratings.html` - primljene ocene

**Izveštaji (FAZA 8):**
- [ ] `daily_sales.html` - dnevni pazar
- [ ] `stock_movements.html` - pregled pokreta
- [ ] `ticket_profit.html` - profit po nalogu

---

## BUDUĆE FAZE (vidi ARCHIVE_servishub_full_erp_plan.md)

Kada MVP bude stabilan i u produkciji:

1. **Popis/Inventura** - brojanje sa automatskom korekcijom
2. **Više magacina po lokaciji** - Warehouse model (MAIN, RETAIL, CONSUMABLE)
3. **Potrošni materijal** - USE_INTERNAL za interni utrošak
4. **Osnovna sredstva** - amortizacija, registar, specijalni tretman
5. **Proizvodnja/BOM** - kreiranje artikla od više artikala (Bill of Materials)
6. **VP magacin** - veleprodajna logika sa posebnim cenama
7. **E-Fakture** - SEF integracija
8. **Knjigovodstvo** - kontni plan, knjiženje, izveštaji

---

## NAPOMENE

### Kritična pravila za StockMovement:

1. **NIKAD direktno menjati `LocationStock.quantity`!**
   - Uvek koristiti `create_stock_movement()` helper
   - LocationStock.quantity se automatski ažurira

2. **NIKAD UPDATE/DELETE na `stock_movement` tabeli!**
   - Za ispravku: novi red sa suprotnim predznakom
   - Čuva kompletan audit trail

3. **Transakcije:**
   ```python
   with db.session.begin_nested():
       movement = create_stock_movement(
           tenant_id=...,
           location_id=...,  # OBAVEZNO - na kojoj lokaciji
           user_id=...,
           ...
       )
   db.session.commit()
   ```

4. **Razlog je obavezan za ADJUST, DAMAGE i INITIAL_BALANCE:**
   - Sistem odbija korekciju bez reason parametra

5. **Validacija stanja:**
   - `balance_after >= 0` je DB constraint
   - Prodaja/utrošak sa nedovoljnim stanjem → ValueError

6. **Stanje po lokaciji:**
   - Svaki artikal može biti na više lokacija
   - LocationStock čuva stanje po (location_id, item_id)
   - Za ukupno stanje: SUM(quantity) FROM location_stock WHERE goods_item_id=X

### RBAC za lager:

| Akcija | Staff | Manager | Admin |
|--------|-------|---------|-------|
| RECEIVE | ✅ | ✅ | ✅ |
| SALE | ✅ | ✅ | ✅ |
| USE_TICKET | ✅ | ✅ | ✅ |
| INITIAL_BALANCE | ❌ | ❌ | ✅ |
| RETURN | ❌ | ✅ | ✅ |
| ADJUST | ❌ | ❌ | ✅ |
| DAMAGE | ❌ | ✅ | ✅ |
| TRANSFER_OUT/IN | ❌ | ✅ | ✅ |

### RBAC za transfer i marketplace:

| Akcija | Staff | Manager | Admin |
|--------|-------|---------|-------|
| Kreiranje TransferRequest | ✅ | ✅ | ✅ |
| Odobravanje TransferRequest | ❌ | ✅ | ✅ |
| Slanje TransferRequest | ❌ | ✅ | ✅ |
| Prijem TransferRequest | ✅ | ✅ | ✅ |
| Upload cenovnika (dobavljač) | ❌ | ❌ | ✅ |
| Kreiranje PartOrderRequest | ✅ | ✅ | ✅ |
| Potvrda PartOrderRequest (dobavljač) | ❌ | ❌ | ✅ |

### Ostalo:

- Fiskalizacija zavisi od ESIR integracije (postojeća?)
- Full ERP plan sačuvan u `ARCHIVE_servishub_full_erp_plan.md`
