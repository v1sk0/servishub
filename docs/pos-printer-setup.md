# ServisHub POS Print Agent - Uputstvo za instalaciju

## Pregled

POS Print Agent je lokalni program koji prima podatke o racunu sa ServisHub web aplikacije i direktno stampa na POS termalni stampac (ESC/POS protokol). Eliminise potrebu za browser print dijalogom.

```
Browser (shub.rs)                    Lokalni racunar
+------------------+                  +---------------------+
|  POS Kasa        |  POST /print    |  pos_print_agent.py |
|  ----------      | --------------> |  (localhost:9100)    |
|  Potvrda placanja|  receipt JSON    |                     |
|                  |                  |  python-escpos       |
|  Fallback:       |  GET /status    |  ----------------->  |
|  window.print()  | <-------------- |  POS Stampac (USB)   |
+------------------+                  +---------------------+
```

**Kako radi:**
1. Korisnik konfigurize stampac u POS Podesavanja (ESC/POS Agent mod)
2. Kad stampa racun: web app POST-uje receipt JSON na `localhost:9100/print`
3. Agent formatira ESC/POS komande i salje na stampac
4. Ako agent ne radi → automatski fallback na browser print dijalog

---

## 1. Instalacija na macOS (CUPS mod - preporuceno)

### Preduslov: Python 3

macOS Catalina i noviji imaju Python 3 preinstaliran. Proverite:

```bash
python3 --version
# Trebalo bi: Python 3.8.x ili noviji
```

> **VAZNO:** Na macOS-u koristite `python3`, NE `python` (koji moze biti Python 2).

### Korak 1: Instalacija python-escpos

```bash
pip3 install python-escpos
```

Ako `pip3` nije pronadjen:

```bash
python3 -m pip install python-escpos
```

> Za CUPS mod (macOS) ne treba `pyusb` niti `libusb` - sve ide preko sistemskog `lp` komanda.

### Korak 2: Dodavanje stampaca u System Preferences

1. Otvorite **System Preferences** → **Printers & Scanners**
2. Kliknite **+** da dodate stampac
3. Stampac bi trebalo da se pojavi kao USB uredaj (npr. "POS891", "TM-T20II")
4. Dodajte ga sa podrazumevanim drajverom ("Generic")

### Korak 3: Pronalazenje imena stampaca

```bash
# Opcija A: Koristite agent
python3 pos_print_agent.py --list-printers

# Opcija B: Rucno
lpstat -p
# Output primer: printer POS891 is idle. enabled since ...
```

Ime stampaca je rec posle "printer" (npr. `POS891`).

### Korak 4: Pokretanje agenta

```bash
python3 pos_print_agent.py --cups POS891
```

Ocekivani output:

```
Printer: CUPS 'POS891' (via lp -o raw)
CUPS printer 'POS891': OK

ServisHub POS Print Agent running on http://localhost:9100
  GET  /status  - Health check
  POST /print   - Print receipt
  POST /test    - Test print

Press Ctrl+C to stop
```

### Korak 5: Konfiguracija u ServisHub

1. Otvorite **POS Podesavanja** u ServisHub-u
2. Kliknite **Dodaj stampac**
3. Popunite:
   - **Naziv:** POS891 (ili ime vaseg stampaca)
   - **Sirina papira:** 80mm
   - **Nacin stampe:** ESC/POS Agent (direktno)
   - **Agent URL:** `http://localhost:9100`
   - Vendor ID i Product ID ostavite prazno (za CUPS mod nisu potrebni)
4. Kliknite **Test konekciju** - trebalo bi da pokaze "Povezan"
5. Kliknite **Test stampe** - stampac bi trebalo da odstampa test stranicu
6. Sacuvajte stampac

---

## 2. Instalacija na Windows (USB mod)

### Korak 1: Instalacija

```cmd
pip install python-escpos pyusb
```

Takodje instalirajte [libusb](https://libusb.info/) ili [Zadig](https://zadig.akeo.ie/) za USB pristup.

### Korak 2: Pronalazenje Vendor/Product ID

1. Otvorite **Device Manager**
2. Pronadjite stampac pod **Universal Serial Bus controllers** ili **Printers**
3. Desni klik → **Properties** → **Details** → **Hardware Ids**
4. ID format: `USB\VID_0483&PID_5720` → Vendor: `0x0483`, Product: `0x5720`

### Korak 3: Pokretanje agenta

```cmd
python pos_print_agent.py --vendor 0x0483 --product 0x5720
```

### Korak 4: Konfiguracija u ServisHub

Isto kao macOS Korak 5, ali unesite Vendor ID i Product ID u formu.

---

## 3. Instalacija za mrezni stampac (LAN/WiFi)

```bash
python3 pos_print_agent.py --network 192.168.1.100
```

Gde je `192.168.1.100` IP adresa stampaca na mrezi.

---

## 4. Troubleshooting

### Agent se ne pokrece

**Problem:** `ModuleNotFoundError: No module named 'escpos'`
**Resenje:** `pip3 install python-escpos`

**Problem:** `SyntaxError: Non-ASCII character` ili `invalid syntax`
**Resenje:** Koristite `python3` umesto `python` (macOS Catalina ima Python 2 kao default)

### Web app ne moze da se poveze na agent

**Problem:** "Nije dostupan" u POS podesavanjima
**Moguca resenja:**
1. Proverite da li je agent pokrenut (terminal treba biti otvoren)
2. Agent URL mora biti tacno `http://localhost:9100`
3. Proverite da firewall ne blokira port 9100

### Stampac ne stampa

**Problem:** Agent prijavljuje gresku pri stampi
**Moguca resenja:**

Za CUPS (macOS):
```bash
# Proverite da li je stampac online
lpstat -p

# Proverite CUPS red za stampu
lpstat -t

# Ocistite red za stampu ako je zaglavio
cancel -a IME_STAMPACA
```

Za USB (Windows/Linux):
- Proverite da li je stampac ukljucen i povezan
- Proverite Vendor/Product ID (Device Manager)
- Na Linux-u mozda treba `sudo` ili udev pravila za USB pristup

### Racun se stampa, ali format je los

- Proverite da je **Sirina papira** ispravno podesena (80mm ili 58mm)
- Za 58mm stampace, tekst ce se automatski suziti

---

## 5. Automatsko pokretanje agenta

### macOS - Launch Agent (automatski pri loginu)

Kreirajte fajl `~/Library/LaunchAgents/com.servishub.posagent.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.servishub.posagent</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/VAŠE_IME/Desktop/pos_print_agent.py</string>
        <string>--cups</string>
        <string>POS891</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/pos_agent.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/pos_agent.log</string>
</dict>
</plist>
```

Zatim:
```bash
launchctl load ~/Library/LaunchAgents/com.servishub.posagent.plist
```

### Windows - Task Scheduler

1. Otvorite **Task Scheduler**
2. Create Basic Task → "ServisHub POS Agent"
3. Trigger: At logon
4. Action: Start a program
   - Program: `python`
   - Arguments: `pos_print_agent.py --vendor 0x0483 --product 0x5720`
   - Start in: putanja do fajla

---

## 6. Referenca: Agent endpointi

| Metoda | Putanja | Opis |
|--------|---------|------|
| GET | `/status` | Health check, vraca status i verziju agenta |
| POST | `/print` | Stampa racun (prima receipt JSON) |
| POST | `/test` | Stampa test stranicu |

### GET /status - Response

```json
{
  "status": "ok",
  "printer_type": "cups",
  "cups_name": "POS891",
  "agent_version": "1.1.0"
}
```

### POST /print - Request body

```json
{
  "receipt": {
    "receipt_number": "20260212-001",
    "receipt_type": "SALE",
    "total_amount": 2920.00,
    "payment_method": "CASH",
    "cash_received": 3000.00,
    "cash_change": 80.00,
    "issued_at": "2026-02-12T14:30:00",
    "issued_by": "Darko",
    "items": [
      { "item_name": "USB kabal", "quantity": 2, "unit_price": 350, "line_total": 700 }
    ]
  },
  "tenant": {
    "name": "Naziv firme",
    "address": "Adresa",
    "pib": "111565745"
  },
  "footer_message": "Hvala na poseti!",
  "paper_size": "80",
  "auto_cut": true
}
```

---

## 7. Podrzani stampaci

Testiran sa:
- **SPRT POS891** (80mm, USB) - macOS CUPS + Windows USB

Trebalo bi da radi sa svim ESC/POS kompatibilnim stampacima:
- Epson TM-T20II, TM-T88V
- Star TSP143
- HPRT TP806
- Bixolon SRP-350III
- I drugi 80mm/58mm termalni stampaci
