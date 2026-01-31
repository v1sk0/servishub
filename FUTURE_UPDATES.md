# ServisHub - Future Updates & Roadmap

**Poslednje ažurirano:** 2026-01-31

Ovaj fajl sadrži ideje, planove i vizije za buduće verzije ServisHub platforme.
S vremena na vreme čitamo ovaj dokument da usmerimo aktuelni development ka dugoročnim ciljevima.

---

## 📋 SADRŽAJ

1. [Service Category Architecture](#-service-category-architecture)
2. [Ideje za razmatranje](#-ideje-za-razmatranje)
3. [Quick Wins](#-quick-wins)
4. [Tehnički dug](#-tehnički-dug)

---

## 🏗️ SERVICE CATEGORY ARCHITECTURE

**Status:** DRAFT - Potrebno definisati industrije detaljnije
**Prioritet:** HIGH
**Datum kreiranja:** 2026-01-30

### Cilj

Kreirati database-driven sistem kategorija koji omogućava:
1. **Bilo koju servisnu delatnost** - od telefona do traktora
2. **One-click setup** - Template paketi za brzo pokretanje
3. **Auto-optimizacija** - SEO, flash animacije, content automatski
4. **Skalabilnost** - Dodavanje novih industrija bez code promene

### Arhitektura - 4 Nivoa

```
┌─────────────────────────────────────────────────────────────┐
│  LEVEL 1: INDUSTRIJA (Industry)                             │
│  Npr: Electronics Repair, Auto Services, Home Appliances    │
├─────────────────────────────────────────────────────────────┤
│  LEVEL 2: KATEGORIJA (ServiceCategory)                      │
│  Npr: Smartphones, Laptops, Washing Machines                │
├─────────────────────────────────────────────────────────────┤
│  LEVEL 3: SERVICE TEMPLATE                                  │
│  Npr: Zamena ekrana, Zamena baterije, Čišćenje virusa       │
├─────────────────────────────────────────────────────────────┤
│  LEVEL 4: TEMPLATE PACK (One-click setup)                   │
│  Npr: "Phone Repair Shop", "Auto Mechanic", "IT Services"   │
└─────────────────────────────────────────────────────────────┘
```

### Database Schema

| Tabela | Opis |
|--------|------|
| `industry` | Top-level industrije |
| `service_category` | Kategorije unutar industrije |
| `service_template` | Predefinisane usluge sa cenama |
| `template_pack` | One-click setup paketi |
| `tenant_industry` | Tenant ↔ Industry veza |
| `tenant_category` | Tenant ↔ Category sa customization |
| `device_brand` | Brendovi za autocomplete |
| `device_model` | Modeli uređaja |

### Industrije (DRAFT - potrebno definisati)

**Potvrđeno:**
- `mobile_tablets` - Mobilni telefoni i tableti (telefoni, tableti, pametni satovi, slušalice, power bank)

**Za definisanje:**
- Računari i IT
- Gaming oprema
- Kućni aparati
- Klima/Grejanje
- Auto servis
- Električna vozila (trotineti, bicikli) - **NAPOMENA:** "Mikromobilnost" nije dobar termin
- Foto/Video oprema
- Audio oprema
- Medicinska oprema
- Satovi/Nakit
- Muzički instrumenti
- Električni alat
- Nautika
- Poljoprivreda

### Template Paketi

```
Phone Repair Shop:
- Industrija: mobile_tablets
- Kategorije: smartphones, tablets
- Usluge: Zamena ekrana, Zamena baterije, Vađenje podataka...
- Brendovi: Apple, Samsung, Xiaomi, Huawei
- Flash: telefoni, tableti
```

### Onboarding Flow

1. Registracija (email, ime, naziv firme)
2. Izbor industrije (vizuelni picker)
3. Izbor template paketa
4. Auto-setup (kategorije, cenovnik, flash, FAQ, SEO)

### Implementacija - Faze

- [ ] FAZA 1: Database & Models
- [ ] FAZA 2: Seed Data (industrije, kategorije, template-i)
- [ ] FAZA 3: API Endpoints
- [ ] FAZA 4: Settings UI - tab "Tip Servisa"
- [ ] FAZA 5: Flash Integration (DB umesto hardkodovano)

### TODO pre implementacije

- [ ] Definisati sve industrije pitanje-po-pitanje
- [ ] Za svaku industriju definisati kategorije
- [ ] Definisati preporučene cene za svaku uslugu
- [ ] Dizajnirati UI za onboarding

---

## 💡 IDEJE ZA RAZMATRANJE

### Korisničko iskustvo
- [ ] Mobilna aplikacija za klijente (praćenje statusa)
- [ ] Push notifikacije za status promene
- [ ] SMS integracija za obaveštenja
- [ ] WhatsApp Business integracija

### Integracije
- [ ] Fiskalnih kasa
- [ ] Računovodstvenih softvera
- [ ] Kurirskih službi
- [ ] Payment gateway (Stripe, PayPal)

### Analytics
- [ ] Dashboard sa KPI metrikama
- [ ] Prosečno vreme popravke po kategoriji
- [ ] Customer satisfaction tracking
- [ ] Revenue analytics

### Marketing
- [ ] Email kampanje za postojeće klijente
- [ ] Loyalty program
- [ ] Referral sistem
- [ ] Automatski Google Reviews request

---

## ⚡ QUICK WINS

Male stvari koje možemo brzo implementirati:

- [ ] Export izveštaja u PDF/Excel
- [ ] Bulk akcije na servisnim nalozima
- [ ] Keyboard shortcuts
- [ ] Dark/Light mode toggle

---

## 🔧 TEHNIČKI DUG

Stvari koje treba refaktorisati:

- [ ] flash_services.py - prebaciti u DB
- [ ] Centralizovati theme sistem
- [ ] API versioning (v2)
- [ ] Test coverage

---

## 📝 KAKO KORISTITI OVAJ DOKUMENT

1. **Dodavanje ideje:** Dodaj u odgovarajuću sekciju sa `- [ ]` checkbox
2. **Prioritizacija:** Pomeri važnije ideje gore
3. **Implementacija:** Kada kreneš sa radom, označi sa `- [x]` i dodaj datum
4. **Review:** Periodično prolazi kroz dokument i briši zastarele ideje

---

*Poslednji review: 2026-01-31*
