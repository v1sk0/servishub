# ServisHub Ticket UI - Dolce Vita Style Implementation

> Poslednje ažuriranje: 20. Januar 2026

---

## Overview

Ovaj dokument opisuje sve izmene implementirane na stranici servisnih naloga (`/tickets`) kako bi se uskladila sa Dolce Vita sistemom. Cilj je bio postići identičan vizuelni dizajn i funkcionalnost.

---

## 1. Animirani Progress Bar

### Lokacija
`app/templates/tenant/tickets/list.html` - CSS sekcija

### Opis
Progress bar koji prikazuje koliko dana je nalog otvoren sada ima:
- Animirane dijagonalne pruge koje se pomeraju
- Glow efekat (box-shadow) za svaku boju
- Promenjeni pragovi za boje

### CSS Implementacija

```css
@keyframes stripes-move {
    0% { background-position: 0 0; }
    100% { background-position: 40px 0; }
}

.duration-fill {
    height: 100%;
    border-radius: 12px;
    transition: width 0.3s ease;
    background-size: 40px 40px;
    animation: stripes-move 1.5s linear infinite;
}

.duration-fill.green {
    background-color: #34a853;
    background-image: linear-gradient(135deg,
        rgba(255,255,255,0.15) 25%, transparent 25%,
        transparent 50%, rgba(255,255,255,0.15) 50%,
        rgba(255,255,255,0.15) 75%, transparent 75%, transparent);
    box-shadow: 0 0 12px rgba(52, 168, 83, 0.5),
                inset 0 1px 0 rgba(255,255,255,0.3);
}
/* Isto za .yellow i .red sa odgovarajućim bojama */
```

### Pragovi za boje

| Stanje | Stari prag | Novi prag (Dolce Vita) |
|--------|-----------|------------------------|
| Zeleno | ≤3 dana   | ≤10 dana              |
| Žuto   | 3-7 dana  | 10-18 dana            |
| Crveno | >7 dana   | >18 dana              |

---

## 2. Notification System

### Komponente

#### A) "Obavesti" dugme
- Pojavljuje se na pending tiketima
- Prikazuje badge sa brojem obaveštenja
- Pulsira kada je prvo obaveštenje (first-notify animacija)
- Disabled kada nije moguće obaveštenje (15 dana cooldown)

#### B) Notification Modal
- Prikazuje info o tiketu (broj, klijent, uređaj)
- Istorija prethodnih obaveštenja
- Quick reply dugmad:
  - "Klijent će doći"
  - "Ne javlja se"
  - "Ostavljena poruka"
- Textarea za custom komentar
- "Otpiši nalog" dugme (nakon 5+ obaveštenja)

### API Endpoints

```
GET  /api/v1/tickets/{id}/notifications  - Lista obaveštenja
POST /api/v1/tickets/{id}/notify         - Novo obaveštenje
POST /api/v1/tickets/{id}/write-off      - Otpis naloga
```

### JavaScript funkcije

```javascript
// State
showNotifyModal: false,
notifyTicket: null,
notifyComment: '',
notificationHistory: [],

// Funkcije
openNotifyModal(ticket)   - Otvara modal
confirmNotify()           - Šalje obaveštenje
writeOffTicket()          - Otpisuje nalog
```

---

## 3. Collect Modal

### Opis
Umesto prostog `confirm()` dialoga, naplata sada koristi modal sa:
- Info karticom (broj naloga, klijent, uređaj)
- Input za iznos naplate
- Select za valutu (RSD/EUR)

### JavaScript State

```javascript
showCollectModal: false,
collectTicketData: null,
collectPrice: '',
collectCurrency: 'RSD',
```

### Funkcije

```javascript
collectTicket(ticket)  - Otvara modal sa predefinisanom cenom
confirmCollect()       - Potvrđuje naplatu i šalje PATCH request
```

---

## 4. Pending Tickets Duration Bar

### Opis
Nova kolona "Čeka" u tabeli tiketa za naplatu koja prikazuje koliko dana tiket čeka preuzimanje od zatvaranja.

### Pragovi

| Stanje | Dani    |
|--------|---------|
| Zeleno | ≤7 dana |
| Žuto   | 7-15 dana |
| Crveno | >15 dana |

### JavaScript funkcije

```javascript
getDaysWaiting(ticket)           - Računa dane od closed_at
getWaitingDurationClass(ticket)  - Vraća CSS klasu
getWaitingDurationPercent(ticket) - Vraća procenat za width
```

---

## 5. Action Buttons Glow Effect

### Opis
Sva action dugmad na hover dobijaju:
- Gradient background
- Box-shadow glow efekat
- Transform translateY(-1px) za "podizanje"

### CSS Primer

```css
.action-btn.complete:hover {
    background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
    color: white;
    box-shadow: 0 0 15px rgba(34, 197, 94, 0.4);
    transform: translateY(-1px);
}
```

### Dugmad sa glow efektom
- `.action-btn.complete` - Zeleni glow
- `.action-btn.reject` - Crveni glow
- `.action-btn.print` - Plavi glow
- `.action-btn.collect` - Ljubičasti glow
- `.action-btn.notify` - Crveni glow

---

## 6. Glass Theme Support

Sve nove komponente imaju podršku za glass (dark) temu:
- Notification modal stilovi
- Collect modal stilovi
- Duration bar stilovi
- Badge stilovi

---

## Verifikaciona Lista

- [x] Progress bar ima animirane dijagonalne pruge
- [x] Progress bar ima glow efekat
- [x] Boje se menjaju na ≤10, 10-18, >18 dana
- [x] "Obavesti" dugme se pojavljuje na pending tiketima
- [x] Badge prikazuje broj obaveštenja
- [x] Notification modal prikazuje istoriju
- [x] Quick reply dugmad rade
- [x] Write-off opcija se pojavljuje nakon 5+ poziva
- [x] Collect modal ima input za cenu i valutu
- [x] Pending tabela ima "Čeka" kolonu sa duration barom
- [x] Action dugmad imaju glow na hover

---

## Fajlovi

| Fajl | Izmene |
|------|--------|
| `app/templates/tenant/tickets/list.html` | CSS, HTML modali, JavaScript funkcije |

---

## Napomene

1. API za notifikacije već postoji u `app/api/v1/tickets.py`
2. Ticket model već ima `can_notify`, `can_write_off`, `notification_count` properties
3. Glass tema je automatski podržana kroz CSS klase