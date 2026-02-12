"""Update barcodes for existing GoodsItem records (XPhone tenant_id=133)."""
import os
os.environ.setdefault('FLASK_APP', 'wsgi:app')

from app import create_app
from app.extensions import db
from app.models.goods import GoodsItem

app = create_app()

SKU_TO_BARCODE = {
    "AD450": "8600356100380",
    "A725": "8600356289351",
    "H505": "8600423867345",
    "H504": "8600423867338",
    "P1263": "8600356288101",
    "P1005": "8600423867055",
    "P1240": "8600356255486",
    "P1009": "8600423867093",
    "P1201": "8600356101936",
    "BAT2683": "8600356287579",
    "BAT2678": "8600356287524",
    "SL1514": "8600356233873",
    "SL1515": "8600356233880",
    "U2003": "8600423867277",
    "U2004": "8600423867284",
    "U2001": "8600423867253",
    "U1989": "8600423867130",
    "U1991": "8600423867154",
    "U1990": "8600423867147",
    "U2101": "8600356235006",
    "AD430": "8600356076630",
    "D1043": "8600356101424",
    "D2059": "8600356288286",
    "FM822": "8600356102001",
    "FM821": "8600356101998",
    "R2263": "8600356264372",
    "R2139": "8600356178242",
    "R2140": "8600356191432",
    "ZV1056": "8600356234719",
    "A720": "8600356264587",
    "A724": "8600356289344",
    "ZV1224": "8600356421713",
    "ZV1225": "8600356421720",
    "ZV1194": "8600356374620",
    "ZV1195": "8600356374637",
    "ZV1049": "8600356234641",
    "ZV1193": "8600356374613",
    "SL1907": "8600356290944",
    "SL1906": "8600356290937",
    "SL1911": "8600356290982",
    "R2149": "8600356214735",
}

TENANT_ID = 133

with app.app_context():
    updated = 0
    not_found = 0
    already_has = 0

    for sku, barcode in SKU_TO_BARCODE.items():
        item = GoodsItem.query.filter_by(tenant_id=TENANT_ID, sku=sku).first()
        if not item:
            print(f"  NOT FOUND: sku={sku}")
            not_found += 1
            continue
        if item.barcode:
            print(f"  ALREADY: {sku} -> {item.barcode}")
            already_has += 1
            continue
        item.barcode = barcode
        updated += 1
        print(f"  UPDATED: {sku} -> {barcode} ({item.name})")

    db.session.commit()
    print(f"\nDone: {updated} updated, {already_has} already had barcode, {not_found} not found")
