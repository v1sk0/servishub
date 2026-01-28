"""Import goods from 'lager servis.csv' into GoodsItem for tenant 68."""
import csv
import math
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from app.extensions import db
from app.models.goods import GoodsItem
from decimal import Decimal

TENANT_ID = 68
LOCATION_ID = 68  # tenant 68 default location
CSV_PATH = os.path.join(os.path.dirname(__file__), 'lager_servis.csv')
MARGIN_PCT = Decimal('35.00')


def suggest_selling_price(purchase_price):
    raw = float(purchase_price) * 1.35
    if raw <= 500:
        round_to = 10
    elif raw <= 2000:
        round_to = 50
    else:
        round_to = 100
    return Decimal(str(math.ceil(raw / round_to) * round_to))


def parse_decimal(s):
    """Parse Serbian decimal format: 2.781,00 -> 2781.00"""
    if not s or not s.strip():
        return Decimal('0')
    s = s.strip()
    # Remove thousand separator (.), replace decimal comma with dot
    s = s.replace('.', '').replace(',', '.')
    try:
        return Decimal(s)
    except Exception:
        return Decimal('0')


def main():
    app = create_app()
    with app.app_context():
        # Check existing count
        existing = GoodsItem.query.filter_by(tenant_id=TENANT_ID).count()
        print(f"Existing GoodsItem for tenant {TENANT_ID}: {existing}")

        with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f, delimiter=';')
            rows = list(reader)

        # Find header row (starts with Šifra or Sifra)
        header_idx = None
        for i, row in enumerate(rows):
            if row and row[0].strip().lower() in ('šifra', 'sifra', '\x8aifra'):
                header_idx = i
                break

        if header_idx is None:
            # Try to find by content pattern
            for i, row in enumerate(rows):
                if row and 'ifra' in row[0]:
                    header_idx = i
                    break

        if header_idx is None:
            print("ERROR: Could not find header row")
            print("First 10 rows:")
            for i, row in enumerate(rows[:10]):
                print(f"  {i}: {row}")
            return

        print(f"Header found at row {header_idx}: {rows[header_idx]}")
        data_rows = rows[header_idx + 1:]

        imported = 0
        skipped = 0
        errors = 0

        for row in data_rows:
            if len(row) < 7:
                continue

            sifra = row[0].strip()
            naziv = row[1].strip()
            jm = row[2].strip() if row[2].strip() else 'kom'
            stanje_str = row[5].strip() if len(row) > 5 else '0'
            cena_str = row[6].strip() if len(row) > 6 else '0'

            # Skip empty/summary rows
            if not sifra or not naziv:
                skipped += 1
                continue

            # Skip if it looks like a total row
            try:
                float(sifra.replace('.', '').replace(',', '.'))
                if not naziv:
                    skipped += 1
                    continue
            except ValueError:
                pass

            try:
                stanje = int(stanje_str) if stanje_str else 0
            except ValueError:
                stanje = 0

            purchase_price = parse_decimal(cena_str)
            if purchase_price <= 0:
                skipped += 1
                continue

            selling_price = suggest_selling_price(purchase_price)

            try:
                item = GoodsItem(
                    tenant_id=TENANT_ID,
                    location_id=LOCATION_ID,
                    name=naziv,
                    sku=sifra.upper().strip(),
                    barcode=sifra.upper().strip(),
                    category=None,
                    purchase_price=purchase_price,
                    selling_price=selling_price,
                    default_margin_pct=MARGIN_PCT,
                    currency='RSD',
                    current_stock=stanje,
                    min_stock_level=0,
                    tax_label='A',
                    unit_of_measure=jm.lower(),
                    is_active=True,
                )
                db.session.add(item)
                imported += 1
            except Exception as e:
                print(f"ERROR on row {sifra}: {e}")
                errors += 1

        db.session.commit()
        print(f"\nDone! Imported: {imported}, Skipped: {skipped}, Errors: {errors}")

        # Verify
        total = GoodsItem.query.filter_by(tenant_id=TENANT_ID).count()
        print(f"Total GoodsItem for tenant {TENANT_ID}: {total}")

        # Show sample
        samples = GoodsItem.query.filter_by(tenant_id=TENANT_ID).limit(5).all()
        for s in samples:
            print(f"  {s.sku} | {s.name[:40]} | stock={s.current_stock} | nab={s.purchase_price} | prod={s.selling_price}")


if __name__ == '__main__':
    main()