"""
Standardni brendovi uredjaja i njihovi aliasi.

Koristi se za normalizaciju brenda pri unosu i pretrazivanju.
"""

STANDARD_BRANDS = {
    'Apple': ['apple', 'iphone', 'ipad', 'appple', 'aplle'],
    'Samsung': ['samsung', 'samsang', 'sumsung', 'galaxy', 'samung'],
    'Xiaomi': ['xiaomi', 'redmi', 'poco', 'mi', 'xiami', 'shaomi'],
    'Huawei': ['huawei', 'hauwei', 'honor', 'huawai'],
    'Motorola': ['motorola', 'moto', 'motorolla'],
    'OnePlus': ['oneplus', 'one plus', '1+', 'one+'],
    'Google': ['google', 'pixel'],
    'Nokia': ['nokia', 'hmd'],
    'Sony': ['sony', 'xperia'],
    'LG': ['lg'],
    'Oppo': ['oppo'],
    'Vivo': ['vivo'],
    'Realme': ['realme'],
    'Nothing': ['nothing'],
    'Asus': ['asus', 'rog'],
    'Lenovo': ['lenovo'],
    'TCL': ['tcl', 'alcatel'],
    'ZTE': ['zte'],
}

# Reverse lookup: alias -> standard name
_ALIAS_MAP = {}
for brand, aliases in STANDARD_BRANDS.items():
    for alias in aliases:
        _ALIAS_MAP[alias.lower()] = brand


def normalize_brand(raw):
    """
    Normalizuje brend iz korisnickog unosa u standardni oblik.

    'samsang' -> 'Samsung'
    'iphone' -> 'Apple'
    'XIAOMI' -> 'Xiaomi'
    """
    if not raw:
        return raw
    cleaned = raw.strip().lower()
    return _ALIAS_MAP.get(cleaned, raw.strip())


def validate_brand(raw):
    """
    Normalizuje brend ili vraca original ako nije prepoznat.
    Nikad ne odbija unos - samo pokusava da normalizuje.
    """
    return normalize_brand(raw)


def get_brand_list():
    """Vraca sortiranu listu standardnih brendova za dropdown."""
    return sorted(STANDARD_BRANDS.keys())
