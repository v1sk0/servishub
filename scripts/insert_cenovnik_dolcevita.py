#!/usr/bin/env python
"""
Skripta za unos cenovnika za Dolce Vita tenant (ID: 68).
Pokreni sa: heroku run python scripts/insert_cenovnik_dolcevita.py -a servicehubdolce
"""

import os
import sys

# Dodaj parent folder u path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models.tenant import Tenant
from app.models.service import ServiceItem

TENANT_ID = 68

# Cenovnik data - Standardne popravke (Telefon/Tablet)
CENOVNIK = [
    # 1) Dijagnostika i softver
    {"category": "Dijagnostika i softver", "name": "Dijagnostika kvara", "price": 1000, "price_note": "od", "description": "Vreme: 0–24h"},
    {"category": "Dijagnostika i softver", "name": "Čišćenje memorije / ubrzanje (optimizacija)", "price": 1500, "price_note": "od", "description": "Vreme: 30–60 min"},
    {"category": "Dijagnostika i softver", "name": "Reinstalacija softvera (flash / reset / podešavanje)", "price": 2500, "price_note": "od", "description": "Vreme: 1–2h"},
    {"category": "Dijagnostika i softver", "name": "Otklanjanje bagova / bootloop (softverski)", "price": 3000, "price_note": "od", "description": "Vreme: 1–3h"},
    {"category": "Dijagnostika i softver", "name": "Prebacivanje podataka na novi uređaj", "price": 3500, "price_note": "od", "description": "Vreme: 1–24h"},

    # 2) Ekran i kućište
    {"category": "Ekran i kućište", "name": "Zamena ekrana (LCD/OLED + touch)", "price": 5000, "price_note": "od", "description": "Vreme: 1–4h"},
    {"category": "Ekran i kućište", "name": "Zamena stakla (samo na modelima gde je moguće)", "price": 6000, "price_note": "od", "description": "Vreme: 1–3 dana"},
    {"category": "Ekran i kućište", "name": "Zamena zadnjeg stakla/poklopca", "price": 3500, "price_note": "od", "description": "Vreme: 1–4h"},
    {"category": "Ekran i kućište", "name": "Zamena okvira/kućišta (housing/frame swap)", "price": 6000, "price_note": "od", "description": "Vreme: 2–6h"},
    {"category": "Ekran i kućište", "name": "Zamena kamere (prednja/zadnja)", "price": 3000, "price_note": "od", "description": "Vreme: 1–2h"},

    # 3) Baterija i punjenje
    {"category": "Baterija i punjenje", "name": "Zamena baterije", "price": 3500, "price_note": "od", "description": "Vreme: 1–4h"},
    {"category": "Baterija i punjenje", "name": "Zamena konektora punjenja (USB-C/Lightning)", "price": 3500, "price_note": "od", "description": "Vreme: 1–4h"},
    {"category": "Baterija i punjenje", "name": "Zamena donjeg modula/flex-a punjenja", "price": 3500, "price_note": "od", "description": "Vreme: 1–4h. Za modele gde postoji"},
    {"category": "Baterija i punjenje", "name": "Rešavanje problema brzog punjenja", "price": 2000, "price_note": "od", "description": "Vreme: 30–90 min"},
    {"category": "Baterija i punjenje", "name": "Čišćenje konektora punjenja", "price": 1000, "price_note": "od", "description": "Vreme: 15–30 min"},
    {"category": "Baterija i punjenje", "name": "Zamena + sanacija oksidacije/linija", "price": 6000, "price_note": "od", "description": "Vreme: 1 dan"},

    # 4) Zvuk i komunikacije
    {"category": "Zvuk i komunikacije", "name": "Zamena donjeg zvučnika", "price": 2500, "price_note": "od", "description": "Vreme: 1–4h"},
    {"category": "Zvuk i komunikacije", "name": "Zamena slušalice (earpiece) / slab zvuk u pozivu", "price": 2500, "price_note": "od", "description": "Vreme: 1–4h"},
    {"category": "Zvuk i komunikacije", "name": "Zamena mikrofona", "price": 2500, "price_note": "od", "description": "Vreme: 1–4h"},
    {"category": "Zvuk i komunikacije", "name": "Zamena vibra motora", "price": 2000, "price_note": "od", "description": "Vreme: 1–4h"},
    {"category": "Zvuk i komunikacije", "name": "Zamena SIM ležišta", "price": 2500, "price_note": "od", "description": "Vreme: 1–2h"},

    # 5) Dugmad i senzori
    {"category": "Dugmad i senzori", "name": "Zamena power/volume flex-a", "price": 2500, "price_note": "od", "description": "Vreme: 1–4h"},
    {"category": "Dugmad i senzori", "name": "Rešavanje problema senzora (proximity/ambient)", "price": 3500, "price_note": "od", "description": "Vreme: 30–90 min"},
    {"category": "Dugmad i senzori", "name": "Zamena tastera / home / fingerprint", "price": 3000, "price_note": "od", "description": "Vreme: 1–3h. Gde je moguće"},

    # 6) Voda / oksidacija
    {"category": "Voda / oksidacija", "name": "Čišćenje nakon kvašenja (ultrazvučno) + dijagnostika", "price": 3500, "price_note": "od", "description": "Vreme: 0–24h"},
    {"category": "Voda / oksidacija", "name": "Sanacija oksidacije na ploči", "price": 5000, "price_note": "od", "description": "Vreme: 1–3 dana. Cena zavisi od stanja"},

    # 7) Matična ploča (mikro-lemljenje)
    {"category": "Matična ploča (mikro-lemljenje)", "name": "Zamena IC/komponenti (controller itd.)", "price": 10000, "price_note": "od", "description": "Vreme: 1–5 dana. Cena posle dijagnostike"},
    {"category": "Matična ploča (mikro-lemljenje)", "name": "Napredne intervencije (rework/reball)", "price": 12000, "price_note": "od", "description": "Vreme: 2–7 dana. Cena posle dijagnostike"},

    # 8) Dodatne usluge
    {"category": "Dodatne usluge", "name": "Ugradnja zaštitnog stakla/folije", "price": 600, "price_note": "od", "description": "Vreme: 10–20 min"},
    {"category": "Dodatne usluge", "name": "Čišćenje zvučnika i portova (prašina/nečistoće)", "price": 800, "price_note": "od", "description": "Vreme: 15–30 min"},
    {"category": "Dodatne usluge", "name": "Zamena termalne paste/padova", "price": 2000, "price_note": "od", "description": "Vreme: 1–2h. Za modele gde ima smisla"},
]


def main():
    app = create_app()

    with app.app_context():
        # Pronađi tenant
        tenant = Tenant.query.get(TENANT_ID)
        if not tenant:
            print(f"ERROR: Tenant ID {TENANT_ID} nije pronađen!")
            return 1

        print(f"Tenant pronađen: {tenant.name} (ID: {tenant.id})")

        # Proveri da li već ima usluga
        existing_count = ServiceItem.query.filter_by(tenant_id=tenant.id).count()
        if existing_count > 0:
            print(f"Brisanje {existing_count} postojećih usluga...")
            ServiceItem.query.filter_by(tenant_id=tenant.id).delete()
            db.session.commit()

        # Unesi nove usluge
        display_order = 0
        for item in CENOVNIK:
            service = ServiceItem(
                tenant_id=tenant.id,
                name=item['name'],
                description=item.get('description'),
                category=item['category'],
                price=item['price'],
                currency='RSD',
                price_note=item.get('price_note'),
                display_order=display_order,
                is_active=True
            )
            db.session.add(service)
            display_order += 1

        db.session.commit()
        print(f"\nUspešno uneto {len(CENOVNIK)} usluga!")

        # Prikaži po kategorijama
        categories = {}
        for item in CENOVNIK:
            cat = item['category']
            if cat not in categories:
                categories[cat] = 0
            categories[cat] += 1

        print("\nPo kategorijama:")
        for cat, count in categories.items():
            print(f"  - {cat}: {count} usluga")

        return 0


if __name__ == '__main__':
    sys.exit(main())
