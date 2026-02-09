"""
Part matching servis - pronalazenje delova kod dobavljaca za servisni nalog.

Koristi se u Smart Part Offers flow-u (Paket E):
- Pronalazi aktivne listinge za brand+model+category
- Grupise po quality (original vs kopija)
- Vraca prosecne cene za summary tabelu
"""

import sys
from decimal import Decimal
from sqlalchemy import func, or_
from ..extensions import db
from ..models.supplier import Supplier, SupplierListing, SupplierStatus
from ..constants.brands import normalize_brand


def _log(msg):
    print(f'[PartMatch] {msg}', flush=True)


# Quality grupe za prikaz u summary tabeli
QUALITY_GROUPS = {
    'original': {
        'label': 'Original',
        'grades': ['service_pack', 'original'],
    },
    'kopija': {
        'label': 'Kopija',
        'grades': ['oled_hard', 'oled_soft', 'oem', 'tft_incell', 'aaa', 'copy'],
    },
}

# Sufiksi modela za fallback pretragu
MODEL_SUFFIXES = ['pro max', 'pro', 'max', 'ultra', 'plus', 'lite', 'fe', 'mini', 'note']


def strip_model_suffix(model):
    """
    Uklanja sufiks modela za siru pretragu.

    'iPhone 14 Pro Max' -> 'iPhone 14'
    'Galaxy S24 Ultra' -> 'Galaxy S24'
    'Redmi Note 12 Pro' -> 'Redmi Note 12'
    """
    if not model:
        return model

    lower = model.strip().lower()
    for suffix in MODEL_SUFFIXES:
        if lower.endswith(suffix):
            stripped = model[:len(model) - len(suffix)].strip()
            if stripped:
                return stripped
    return model.strip()


def _extract_model_number(model, brand=None):
    """
    Izvlaci broj modela bez brand prefiksa.

    'Galaxy S21' -> 'S21'
    'iPhone 14 Pro' -> '14 Pro'
    'Redmi Note 12' -> 'Note 12'
    """
    if not model:
        return model

    # Poznati prefiksi za uklanjanje
    prefixes = ['galaxy', 'iphone', 'ipad', 'pixel', 'xperia', 'redmi', 'poco', 'moto']
    if brand:
        prefixes.append(brand.lower())

    lower = model.strip().lower()
    for prefix in prefixes:
        if lower.startswith(prefix + ' '):
            return model[len(prefix):].strip()
        if lower.startswith(prefix):
            rest = model[len(prefix):].strip()
            if rest:
                return rest

    return model.strip()


def find_matching_listings(brand, model, part_category=None):
    """
    Pronalazi aktivne listinge za brand+model+category.

    1. normalize_brand(brand)
    2. ILIKE match na model_compatibility
    3. Fallback 1: strip brand prefix (Galaxy S21 -> S21)
    4. Fallback 2: strip model suffix (S21 Pro -> S21)
    Filter: is_active=True, stock > 0, supplier.status=ACTIVE
    """
    normalized_brand = normalize_brand(brand)
    _log(f' brand={brand!r} -> normalized={normalized_brand!r}, model={model!r}, category={part_category!r}')

    # Debug: count all active listings for this brand
    debug_count = (
        db.session.query(func.count(SupplierListing.id))
        .join(Supplier, SupplierListing.supplier_id == Supplier.id)
        .filter(SupplierListing.is_active.is_(True))
        .scalar()
    )
    _log(f' Total active listings in DB: {debug_count}')

    # Debug: count suppliers with ACTIVE status
    active_suppliers = (
        db.session.query(func.count(Supplier.id))
        .filter(Supplier.status == SupplierStatus.ACTIVE)
        .scalar()
    )
    _log(f' Active suppliers: {active_suppliers}')

    query = (
        db.session.query(SupplierListing)
        .join(Supplier, SupplierListing.supplier_id == Supplier.id)
        .filter(
            SupplierListing.is_active.is_(True),
            Supplier.status == SupplierStatus.ACTIVE,
            or_(
                SupplierListing.stock_quantity.is_(None),  # NULL = neograniceno
                SupplierListing.stock_quantity > 0,
            ),
        )
    )

    # Brand filter (case-insensitive)
    if normalized_brand:
        # Debug: check brand values in DB
        brand_listings = (
            db.session.query(SupplierListing.brand, func.count(SupplierListing.id))
            .join(Supplier, SupplierListing.supplier_id == Supplier.id)
            .filter(
                SupplierListing.is_active.is_(True),
                Supplier.status == SupplierStatus.ACTIVE,
            )
            .group_by(SupplierListing.brand)
            .all()
        )
        _log(f' Brands in DB: {[(b, c) for b, c in brand_listings]}')

        query = query.filter(
            func.upper(SupplierListing.brand) == normalized_brand.upper()
        )

    # Category filter (supports comma-separated list)
    if part_category:
        cats = [c.strip().lower() for c in part_category.split(',') if c.strip()]
        if len(cats) == 1:
            query = query.filter(
                func.lower(SupplierListing.part_category) == cats[0]
            )
        elif cats:
            query = query.filter(
                func.lower(SupplierListing.part_category).in_(cats)
            )

    # Debug: show what model_compatibility values exist for this brand
    if normalized_brand:
        compat_values = (
            db.session.query(SupplierListing.model_compatibility, SupplierListing.part_category, SupplierListing.quality_grade)
            .join(Supplier, SupplierListing.supplier_id == Supplier.id)
            .filter(
                SupplierListing.is_active.is_(True),
                Supplier.status == SupplierStatus.ACTIVE,
                func.upper(SupplierListing.brand) == normalized_brand.upper(),
            )
            .all()
        )
        _log(f' Listings for brand {normalized_brand}: {[(c, cat, q) for c, cat, q in compat_values]}')

    # Model matching - ILIKE na model_compatibility
    if model:
        model_pattern = f'%{model}%'
        _log(f' Trying primary match: ILIKE {model_pattern!r}')
        primary = query.filter(
            SupplierListing.model_compatibility.ilike(model_pattern)
        ).all()
        _log(f' Primary match results: {len(primary)}')

        if primary:
            return primary

        # Fallback 1: strip brand prefix (Galaxy S21 -> S21)
        model_number = _extract_model_number(model, normalized_brand)
        _log(f' Fallback 1: model_number={model_number!r} (from {model!r})')
        if model_number != model:
            prefix_pattern = f'%{model_number}%'
            result = query.filter(
                SupplierListing.model_compatibility.ilike(prefix_pattern)
            ).all()
            _log(f' Fallback 1 results: {len(result)}')
            if result:
                return result

        # Fallback 2: strip suffix (S21 Pro -> S21)
        stripped = strip_model_suffix(model)
        if stripped != model:
            fallback_pattern = f'%{stripped}%'
            result = query.filter(
                SupplierListing.model_compatibility.ilike(fallback_pattern)
            ).all()
            if result:
                return result

        # Fallback 3: strip prefix + suffix combined
        if model_number != model:
            stripped_number = strip_model_suffix(model_number)
            if stripped_number != model_number:
                combined_pattern = f'%{stripped_number}%'
                return query.filter(
                    SupplierListing.model_compatibility.ilike(combined_pattern)
                ).all()

        return primary  # Prazan rezultat

    return query.all()


def get_quality_group(quality_grade):
    """Vraca quality grupu za dati grade."""
    if not quality_grade:
        return None
    grade_lower = quality_grade.lower()
    for group_key, group in QUALITY_GROUPS.items():
        if grade_lower in group['grades']:
            return group_key
    return None


def get_stock_hint(stock_quantity):
    """
    Vraca stock hint za anonimnu listu.
    - 'available' (stock > 3 ili NULL/neograniceno)
    - 'low' (stock 1-3)
    - 'last_one' (stock == 1)
    """
    if stock_quantity is None:
        return 'available'
    if stock_quantity <= 0:
        return 'out_of_stock'
    if stock_quantity == 1:
        return 'last_one'
    if stock_quantity <= 3:
        return 'low'
    return 'available'


def build_summary(listings):
    """
    Gradi summary tabelu: prosecne cene po quality grupi.

    Vraca: {
        'original': {'avg_eur': Decimal, 'avg_rsd': Decimal, 'count': int},
        'kopija': {'avg_eur': Decimal, 'avg_rsd': Decimal, 'count': int},
    }
    """
    groups = {}

    for listing in listings:
        group_key = get_quality_group(listing.quality_grade)
        if not group_key:
            continue

        if group_key not in groups:
            groups[group_key] = {
                'label': QUALITY_GROUPS[group_key]['label'],
                'prices_eur': [],
                'prices_rsd': [],
                'count': 0,
                'suppliers': set(),
            }

        g = groups[group_key]
        if listing.price_eur:
            g['prices_eur'].append(listing.price_eur)
        if listing.price_rsd:
            g['prices_rsd'].append(listing.price_rsd)
        g['count'] += 1
        g['suppliers'].add(listing.supplier_id)

    result = {}
    for key, g in groups.items():
        result[key] = {
            'label': g['label'],
            'avg_eur': (
                sum(g['prices_eur']) / len(g['prices_eur'])
                if g['prices_eur'] else None
            ),
            'avg_rsd': (
                sum(g['prices_rsd']) / len(g['prices_rsd'])
                if g['prices_rsd'] else None
            ),
            'count': g['count'],
            'supplier_count': len(g['suppliers']),
        }

    return result
