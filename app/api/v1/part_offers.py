"""
Part Offers API - Smart Part Offers + 2-Step Anonymous Order Flow (Paket E)

Endpoints:
- GET  /part-offers/ticket/<ticket_id>/summary   - Summary tabela (prosecne cene)
- GET  /part-offers/ticket/<ticket_id>/offers     - Anonimna lista (top 3 po ceni)
- POST /part-offers/order                         - Kreiranje anonimne narudzbine
- POST /part-offers/orders/<id>/confirm           - Tenant potvrda + kredit + reveal
- POST /part-offers/orders/<id>/cancel            - Tenant cancel + opcioni komentar
"""
import hmac
import hashlib
from datetime import datetime, timedelta, date
from decimal import Decimal
from zoneinfo import ZoneInfo

from flask import Blueprint, request, g, current_app
from app.extensions import db
from app.models import (
    PartOrder, PartOrderItem, OrderStatus, SellerType,
    Supplier, SupplierListing, SupplierStatus,
    ServiceTicket, SupplierReveal,
    generate_order_number,
)
from app.models.credits import OwnerType, CreditTransactionType
from app.api.middleware.auth import jwt_required
from app.services.part_matching import (
    find_matching_listings, build_summary, get_stock_hint, QUALITY_GROUPS,
)
from app.models.tenant import Tenant
from app.constants.brands import normalize_brand

bp = Blueprint('part_offers', __name__, url_prefix='/part-offers')


# ============== Delivery Helpers ==============

def _can_deliver_today(rounds):
    """Proverava da li dobavljac moze danas da isporuci."""
    now = datetime.now(tz=ZoneInfo('Europe/Belgrade'))
    day = now.weekday()
    day_key = 'weekday' if day < 5 else ('saturday' if day == 5 else 'sunday')
    for r in rounds.get(day_key, []):
        cutoff = r.get('cutoff', '')
        if cutoff and now.strftime('%H:%M') < cutoff:
            return True
    return False


def _get_delivery_info(supplier, tenant_city):
    """Odredjuje nacin dostave i vraca label string za anonimni prikaz."""
    cities = [c.lower().strip() for c in (supplier.delivery_cities or [])]
    tenant_lower = (tenant_city or '').lower().strip()

    if tenant_lower and tenant_lower in cities:
        rounds = supplier.delivery_rounds or {}
        if _can_deliver_today(rounds):
            return {'type': 'own_delivery', 'label': 'Dostava: Danas'}
        else:
            return {'type': 'own_delivery', 'label': 'Dostava sledeci radni dan'}

    if supplier.courier_services_config:
        return {'type': 'courier', 'label': 'Brza posta, 1-2 radna dana'}

    if supplier.allows_pickup:
        return {'type': 'pickup', 'label': 'Licno preuzimanje'}

    return {'type': None, 'label': None}


# ============== Helpers ==============

def _generate_offer_token(tenant_id, listing_id, ticket_id):
    """HMAC-SHA256 token - nepredvidiv, dnevni, vezan za tenant+listing+ticket."""
    secret = current_app.config.get('SECRET_KEY', 'fallback-key')
    raw = f"{tenant_id}:{listing_id}:{ticket_id}:{date.today()}"
    return hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()[:16]


def _validate_ticket(ticket_id):
    """Validira da ticket pripada g.tenant_id."""
    ticket = ServiceTicket.query.get(ticket_id)
    if not ticket or ticket.tenant_id != g.tenant_id:
        return None
    return ticket


def decrement_stock(order):
    """
    Smanjuje stock pri CONFIRMED. Vraca False ako nema dovoljno.
    Stock decrement se radi samo na CONFIRMED (ne na OFFERED).
    """
    for item in order.items.all():
        if item.supplier_listing_id:
            listing = SupplierListing.query.with_for_update().get(item.supplier_listing_id)
            if listing and listing.stock_quantity is not None:
                if listing.stock_quantity < item.quantity:
                    return False  # Stock conflict!
                listing.stock_quantity -= item.quantity
                if listing.stock_quantity == 0:
                    listing.stock_status = 'OUT_OF_STOCK'
                elif listing.stock_quantity <= 3:
                    listing.stock_status = 'LOW'
    return True


def check_stock_conflicts(listing_id):
    """
    Ako stock padne na 0, revertuj sve OFFERED orders za isti listing na SENT.
    Supplier i tenant ce biti obavesteni da moraju ponovo da provere stanje.
    """
    listing = SupplierListing.query.get(listing_id)
    if not listing or listing.stock_quantity is None or listing.stock_quantity > 0:
        return

    conflicting = (
        PartOrder.query
        .join(PartOrderItem, PartOrder.id == PartOrderItem.order_id)
        .filter(
            PartOrderItem.supplier_listing_id == listing_id,
            PartOrder.status == OrderStatus.OFFERED,
        )
        .all()
    )

    for order in conflicting:
        order.status = OrderStatus.SENT
        order.offered_at = None
        order.expires_at = datetime.utcnow() + timedelta(hours=2)
        order.delivery_method = None
        order.courier_service = None
        order.delivery_cost = None
        order.estimated_delivery_days = None
        order.delivery_cutoff_time = None
        order.seller_notes = None


# ============== Routes ==============

@bp.route('/search', methods=['GET'])
@jwt_required
def search_parts():
    """
    Pretraga dostupnih delova po brand+model (bez ticket_id).
    Koristi se na formi za kreiranje naloga.
    """
    brand = request.args.get('brand')
    model = request.args.get('model')
    category = request.args.get('category')

    if not brand:
        return {'error': 'Brand je obavezan'}, 400

    print(f'[PartOffers] Search: brand={brand!r}, model={model!r}, category={category!r}', flush=True)

    all_listings = find_matching_listings(brand, model, part_category=category)

    print(f'[PartOffers] Search found {len(all_listings)} listings', flush=True)

    if not all_listings:
        return {
            'success': True,
            'categories': [],
            'message': 'Nema dostupnih delova za ovaj uredjaj',
        }

    # Grupisanje po kategorijama
    categories = {}
    for listing in all_listings:
        cat = listing.part_category or 'other'
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(listing)

    result = []
    for cat, listings in categories.items():
        summary = build_summary(listings)
        if summary:
            cat_data = {
                'category': cat,
                'quality_groups': {},
            }
            for group_key, group_data in summary.items():
                cat_data['quality_groups'][group_key] = {
                    'label': group_data['label'],
                    'avg_eur': float(group_data['avg_eur']) if group_data['avg_eur'] else None,
                    'avg_rsd': float(group_data['avg_rsd']) if group_data['avg_rsd'] else None,
                    'count': group_data['count'],
                    'supplier_count': group_data['supplier_count'],
                }
            result.append(cat_data)

    return {
        'success': True,
        'brand': normalize_brand(brand) or brand,
        'model': model,
        'categories': result,
    }


@bp.route('/search/offers', methods=['GET'])
@jwt_required
def search_offers():
    """
    Top 3 anonimne ponude po brand+model+category+quality (bez ticket_id).
    """
    brand = request.args.get('brand')
    model = request.args.get('model')
    category = request.args.get('category')
    quality = request.args.get('quality')

    if not brand or not category or not quality:
        return {'error': 'brand, category i quality su obavezni'}, 400

    if quality not in QUALITY_GROUPS:
        return {'error': f'Nevalidan quality: {quality}'}, 400

    listings = find_matching_listings(brand, model, part_category=category)

    # Filter po quality grupi
    quality_grades = QUALITY_GROUPS[quality]['grades']
    filtered = [
        l for l in listings
        if l.quality_grade and l.quality_grade.lower() in quality_grades
    ]

    # Sort po ceni (EUR prioritet, pa RSD)
    def sort_key(l):
        if l.price_eur:
            return float(l.price_eur)
        if l.price_rsd:
            return float(l.price_rsd) / 117.5
        return float('inf')

    filtered.sort(key=sort_key)
    top = filtered[:3]

    # Get tenant city for delivery info
    tenant = Tenant.query.get(g.tenant_id)
    tenant_city = tenant.grad if tenant else None

    offers = []
    for listing in top:
        supplier = Supplier.query.get(listing.supplier_id)
        sup_rating = None
        sup_rating_count = None
        sup_trust_tier = None
        delivery_label = None
        if supplier:
            if (supplier.rating_count or 0) > 0 and supplier.rating is not None:
                sup_rating = round(float(supplier.rating), 1)
            sup_rating_count = supplier.rating_count
            sup_trust_tier = supplier.trust_tier
            delivery = _get_delivery_info(supplier, tenant_city)
            delivery_label = delivery['label']

        offers.append({
            'listing_id': listing.id,
            'price_eur': float(listing.price_eur) if listing.price_eur else None,
            'price_rsd': float(listing.price_rsd) if listing.price_rsd else None,
            'quality_grade': listing.quality_grade,
            'stock_hint': get_stock_hint(listing.stock_quantity),
            'part_name': listing.name,
            'supplier_rating': sup_rating,
            'supplier_rating_count': sup_rating_count,
            'supplier_trust_tier': sup_trust_tier,
            'delivery_label': delivery_label,
        })

    return {
        'success': True,
        'offers': offers,
        'category': category,
        'quality': quality,
        'quality_label': QUALITY_GROUPS[quality]['label'],
    }


@bp.route('/ticket/<int:ticket_id>/summary', methods=['GET'])
@jwt_required
def get_ticket_summary(ticket_id):
    """
    Faza 1: Summary tabela - prosecne cene Original vs Kopija po kategoriji.
    Koristi se na servisnom nalogu za predlog delova.
    """
    ticket = _validate_ticket(ticket_id)
    if not ticket:
        print(f'[PartOffers] Ticket {ticket_id} not found or not owned by tenant {g.tenant_id}', flush=True)
        return {'error': 'Servisni nalog nije pronadjen'}, 404

    brand = ticket.brand
    model = ticket.model

    print(f'[PartOffers] Summary for ticket {ticket_id}: brand={brand!r}, model={model!r}', flush=True)

    if not brand:
        return {'error': 'Servisni nalog nema definisan brend'}, 400

    # Pronalazenje svih listinga za ovaj uredjaj
    all_listings = find_matching_listings(brand, model)

    print(f'[PartOffers] Found {len(all_listings)} matching listings for brand={brand!r}, model={model!r}', flush=True)

    if not all_listings:
        return {
            'success': True,
            'categories': [],
            'message': 'Nema dostupnih delova za ovaj uredjaj',
        }

    # Grupisanje po kategorijama
    categories = {}
    for listing in all_listings:
        cat = listing.part_category or 'other'
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(listing)

    result = []
    for cat, listings in categories.items():
        summary = build_summary(listings)
        if summary:
            cat_data = {
                'category': cat,
                'quality_groups': {},
            }
            for group_key, group_data in summary.items():
                cat_data['quality_groups'][group_key] = {
                    'label': group_data['label'],
                    'avg_eur': float(group_data['avg_eur']) if group_data['avg_eur'] else None,
                    'avg_rsd': float(group_data['avg_rsd']) if group_data['avg_rsd'] else None,
                    'count': group_data['count'],
                    'supplier_count': group_data['supplier_count'],
                }
            result.append(cat_data)

    return {
        'success': True,
        'brand': normalize_brand(brand),
        'model': model,
        'categories': result,
    }


@bp.route('/ticket/<int:ticket_id>/offers', methods=['GET'])
@jwt_required
def get_ticket_offers(ticket_id):
    """
    Faza 2: Anonimna lista - top 3 po ceni za izabranu kategoriju i quality grupu.
    Vraca offer_token (HMAC), listing_id, cene, stock_hint.
    """
    ticket = _validate_ticket(ticket_id)
    if not ticket:
        return {'error': 'Servisni nalog nije pronadjen'}, 404

    category = request.args.get('category')
    quality = request.args.get('quality')

    if not category or not quality:
        return {'error': 'category i quality parametri su obavezni'}, 400

    if quality not in QUALITY_GROUPS:
        return {'error': f'Nevalidan quality: {quality}. Dozvoljeni: original, kopija'}, 400

    brand = ticket.brand
    model = ticket.model

    listings = find_matching_listings(brand, model, part_category=category)

    # Filter po quality grupi
    quality_grades = QUALITY_GROUPS[quality]['grades']
    filtered = [
        l for l in listings
        if l.quality_grade and l.quality_grade.lower() in quality_grades
    ]

    # Sort po ceni (EUR prioritet, pa RSD)
    def sort_key(l):
        if l.price_eur:
            return float(l.price_eur)
        if l.price_rsd:
            return float(l.price_rsd) / 117.5  # Approx EUR
        return float('inf')

    filtered.sort(key=sort_key)

    # Top 3
    top = filtered[:3]

    # Get tenant city for delivery info
    tenant = Tenant.query.get(g.tenant_id)
    tenant_city = tenant.grad if tenant else None

    offers = []
    for listing in top:
        supplier = Supplier.query.get(listing.supplier_id)
        delivery_label = None
        if supplier:
            delivery = _get_delivery_info(supplier, tenant_city)
            delivery_label = delivery['label']

        offers.append({
            'offer_token': _generate_offer_token(g.tenant_id, listing.id, ticket_id),
            'listing_id': listing.id,
            'price_eur': float(listing.price_eur) if listing.price_eur else None,
            'price_rsd': float(listing.price_rsd) if listing.price_rsd else None,
            'quality_grade': listing.quality_grade,
            'stock_hint': get_stock_hint(listing.stock_quantity),
            'delivery_label': delivery_label,
        })

    return {
        'success': True,
        'offers': offers,
        'category': category,
        'quality': quality,
        'quality_label': QUALITY_GROUPS[quality]['label'],
    }


@bp.route('/order', methods=['POST'])
@jwt_required
def create_order(self=None):
    """
    Faza 3: Kreiranje anonimne narudzbine (SENT status).
    Tenant bira listing iz anonimne liste i kreira narudzbinu.
    service_ticket_id je OBAVEZAN (marker za smart offer order).
    """
    data = request.json or {}
    listing_id = data.get('listing_id')
    quantity = data.get('quantity', 1)
    service_ticket_id = data.get('service_ticket_id')

    if not listing_id or not service_ticket_id:
        return {'error': 'listing_id i service_ticket_id su obavezni'}, 400

    if not isinstance(quantity, int) or quantity < 1:
        return {'error': 'quantity mora biti pozitivan ceo broj'}, 400

    # Validate ticket belongs to tenant
    ticket = _validate_ticket(service_ticket_id)
    if not ticket:
        return {'error': 'Nevazeci servisni nalog'}, 404

    # Validate listing
    listing = SupplierListing.query.get(listing_id)
    if not listing or not listing.is_active:
        return {'error': 'Artikal nije dostupan'}, 404

    # Validate supplier is active
    supplier = Supplier.query.get(listing.supplier_id)
    if not supplier or supplier.status != SupplierStatus.ACTIVE:
        return {'error': 'Dobavljac nije aktivan'}, 400

    # Check stock
    if listing.stock_quantity is not None and listing.stock_quantity < quantity:
        return {'error': 'Nema dovoljno na stanju'}, 400

    # Calculate prices
    unit_price = listing.price_eur or listing.price_rsd or Decimal('0')
    total_price = unit_price * quantity

    # Create order
    order = PartOrder(
        order_number=generate_order_number(),
        buyer_tenant_id=g.tenant_id,
        buyer_user_id=g.user_id,
        seller_type=SellerType.SUPPLIER,
        seller_supplier_id=listing.supplier_id,
        service_ticket_id=service_ticket_id,
        status=OrderStatus.SENT,
        subtotal=total_price,
        commission_amount=total_price * Decimal('0.05'),
        total_amount=total_price,
        currency='EUR' if listing.price_eur else 'RSD',
        sent_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=2),  # Supplier ima 2h
    )
    db.session.add(order)
    db.session.flush()

    # Create order item (snapshot)
    item = PartOrderItem(
        order_id=order.id,
        supplier_listing_id=listing.id,
        part_name=listing.name,
        part_number=listing.part_number,
        brand=listing.brand,
        model=listing.model_compatibility,
        quantity=quantity,
        unit_price=unit_price,
        total_price=total_price,
    )
    db.session.add(item)
    db.session.commit()

    # Email supplier-u (non-blocking)
    try:
        from app.services.email_service import send_supplier_order_email
        send_supplier_order_email(order, 'new_order')
    except (ImportError, Exception):
        pass

    return {
        'success': True,
        'order_id': order.id,
        'order_number': order.order_number,
        'message': 'Narudzbina poslata. Ceka potvrdu dobavljaca.',
        'expires_at': order.expires_at.isoformat(),
    }, 201


@bp.route('/orders/<int:order_id>/confirm', methods=['POST'])
@jwt_required
def confirm_order(order_id):
    """
    Faza 5: Tenant potvrdjuje narudzbinu (OFFERED -> CONFIRMED).
    1 kredit oduzet od tenanta + mutual reveal + stock decrement.
    Atomska transakcija: kredit + reveal + stock + status = jedan commit.
    """
    try:
        # Row lock sprecava race condition
        order = PartOrder.query.with_for_update().get(order_id)
        if not order or order.buyer_tenant_id != g.tenant_id:
            return {'error': 'Narudzbina nije pronadjena'}, 404

        # Idempotent: vec CONFIRMED
        if order.status == OrderStatus.CONFIRMED:
            supplier = Supplier.query.get(order.seller_supplier_id)
            return {
                'success': True,
                'supplier': supplier.to_revealed_dict() if supplier else None,
                'message': 'Narudzbina je vec potvrđena.',
            }

        if order.status != OrderStatus.OFFERED:
            return {
                'error': 'Narudzbina nije u statusu za potvrdu',
                'code': 'INVALID_STATUS',
                'current_status': order.status.value,
            }, 409

        # Proveri expiry (lazy check)
        if order.expires_at and order.expires_at < datetime.utcnow():
            order.status = OrderStatus.SENT
            order.offered_at = None
            order.expires_at = datetime.utcnow() + timedelta(hours=2)
            order.delivery_method = None
            order.courier_service = None
            order.delivery_cost = None
            order.estimated_delivery_days = None
            order.delivery_cutoff_time = None
            db.session.commit()
            return {
                'error': 'Ponuda je istekla. Dobavljac mora ponovo da potvrdi.',
                'code': 'OFFER_EXPIRED',
            }, 410

        # 1. Stock decrement (tek na CONFIRMED, ne na OFFERED)
        if not decrement_stock(order):
            # Stock conflict! Revert to SENT
            order.status = OrderStatus.SENT
            order.offered_at = None
            order.expires_at = datetime.utcnow() + timedelta(hours=2)
            order.delivery_method = None
            order.courier_service = None
            order.delivery_cost = None
            order.estimated_delivery_days = None
            order.delivery_cutoff_time = None
            order.seller_notes = None
            db.session.commit()
            return {
                'error': ('Artikal vise nije na stanju kod dobavljaca. '
                          'Narudzbina je vracena na cekanje - '
                          'dobavljac ce ponovo proveriti stanje.'),
                'code': 'STOCK_CONFLICT',
            }, 409

        supplier_id = order.seller_supplier_id

        # 2. Proveri da li je vec revealed (besplatno ako jeste)
        existing_reveal = SupplierReveal.query.filter_by(
            tenant_id=g.tenant_id, supplier_id=supplier_id
        ).first()

        if not existing_reveal:
            # 3. Oduzmi 1 kredit od TENANTA
            from app.services.credit_service import deduct_credits
            txn = deduct_credits(
                owner_type=OwnerType.TENANT,
                owner_id=g.tenant_id,
                amount=1,
                transaction_type=CreditTransactionType.CONNECTION_FEE,
                description=f'Potvrda narudzbine {order.order_number}',
                ref_type='part_order',
                ref_id=order.id,
                idempotency_key=f'order_confirm_{g.tenant_id}_{order.id}',
            )

            if txn is False:
                return {
                    'error': 'Nemate dovoljno kredita',
                    'credits_required': 1,
                }, 402

            # 4. Mutual reveal
            reveal = SupplierReveal(
                tenant_id=g.tenant_id,
                supplier_id=supplier_id,
                credit_transaction_id=txn.id,
            )
            db.session.add(reveal)

        # 5. Potvrdi narudzbinu
        order.status = OrderStatus.CONFIRMED
        order.confirmed_at = datetime.utcnow()
        order.expires_at = None  # Nema vise expiry

        # 6. Stock conflict check - revertuj ostale OFFERED za iste listinge
        for item in order.items.all():
            if item.supplier_listing_id:
                check_stock_conflicts(item.supplier_listing_id)

        db.session.commit()

        # 7. Delivery cutoff warning
        cutoff_warning = None
        try:
            if order.delivery_cutoff_time:
                now_local = datetime.now(tz=ZoneInfo('Europe/Belgrade')).time()
                if now_local > order.delivery_cutoff_time:
                    cutoff_warning = (
                        'Narudzbina je potvrđena nakon roka za slanje danas. '
                        'Verovatno je prebacena za sledecu turu. '
                        'Kontaktirajte dobavljaca za detalje.'
                    )
        except Exception:
            pass

        # 8. Email supplier-u (non-blocking)
        try:
            from app.services.email_service import send_supplier_order_email
            send_supplier_order_email(order, 'confirmed')
        except (ImportError, Exception):
            pass

        # 9. Vrati kompletne supplier podatke
        supplier = Supplier.query.get(supplier_id)
        return {
            'success': True,
            'supplier': supplier.to_revealed_dict() if supplier else None,
            'cutoff_warning': cutoff_warning,
            'message': 'Narudzbina potvrđena. Podaci o dobavljacu su sada vidljivi.',
        }

    except Exception as e:
        db.session.rollback()
        current_app.logger.exception(f'Error in confirm_order({order_id}): {e}')
        return {'error': f'Greska pri potvrdi: {str(e)}'}, 500


@bp.route('/orders/<int:order_id>/cancel', methods=['POST'])
@jwt_required
def cancel_order(order_id):
    """
    Faza 6b: Tenant otkazuje narudzbinu (SENT ili OFFERED -> CANCELLED).
    Opcioni komentar (cancel_reason).
    BEZ stock rollback - stock nije bio dekrementiiran na OFFERED.
    CONFIRMED+ ne moze se cancel-ovati.
    """
    order = PartOrder.query.with_for_update().get(order_id)
    if not order or order.buyer_tenant_id != g.tenant_id:
        return {'error': 'Narudzbina nije pronadjena'}, 404

    # Idempotent: vec CANCELLED
    if order.status == OrderStatus.CANCELLED:
        return {'message': 'Narudzbina je vec otkazana'}

    if order.status not in (OrderStatus.SENT, OrderStatus.OFFERED):
        return {
            'error': 'Narudzbina ne moze biti otkazana iz ovog statusa. Kontaktirajte podrsku.',
            'code': 'INVALID_STATUS',
        }, 409

    reason = (request.json or {}).get('reason')

    order.status = OrderStatus.CANCELLED
    order.cancelled_at = datetime.utcnow()
    order.cancellation_reason = reason
    order.cancelled_by = 'BUYER'
    order.expires_at = None
    order.updated_at = datetime.utcnow()
    db.session.commit()

    # Email supplier-u (non-blocking)
    try:
        from app.services.email_service import send_supplier_order_email
        send_supplier_order_email(order, 'cancelled')
    except (ImportError, Exception):
        pass

    return {'success': True, 'message': 'Narudzbina otkazana'}
