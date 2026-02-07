"""
Admin API - Upravljanje dobavljačima (suppliers).

Endpointi za platformske administratore za kreiranje i upravljanje
dobavljačima rezervnih delova.
"""

from datetime import datetime
from flask import Blueprint, request, jsonify, g
from sqlalchemy import func, or_

from app.extensions import db
from app.models.supplier import Supplier, SupplierUser, SupplierListing, SupplierStatus
from app.models.admin_activity import AdminActivityLog, AdminActionType
from app.api.middleware.auth import platform_admin_required
from slugify import slugify


def generate_slug(text: str) -> str:
    """Generiše URL-friendly slug iz teksta."""
    return slugify(text, lowercase=True, separator='-')

bp = Blueprint('admin_suppliers', __name__, url_prefix='/suppliers')


# ============================================================================
# LISTA I PRETRAGA DOBAVLJAČA
# ============================================================================

@bp.route('', methods=['GET'])
@platform_admin_required
def list_suppliers():
    """
    Lista svih dobavljača sa filterima i paginacijom.

    Query params:
        - page: broj stranice (default 1)
        - per_page: broj po stranici (default 20, max 100)
        - status: filter po statusu (PENDING, ACTIVE, SUSPENDED, CANCELLED)
        - search: pretraga po imenu, email-u ili PIB-u
        - sort: polje za sortiranje (created_at, name, status)
        - order: asc ili desc
    """
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)
    status = request.args.get('status')
    search = request.args.get('search', '').strip()
    sort = request.args.get('sort', 'created_at')
    order = request.args.get('order', 'desc')

    # Bazni query
    query = Supplier.query

    # Filter po statusu
    if status:
        try:
            status_enum = SupplierStatus[status.upper()]
            query = query.filter(Supplier.status == status_enum)
        except KeyError:
            pass

    # Pretraga
    if search:
        search_term = f'%{search}%'
        query = query.filter(
            or_(
                Supplier.name.ilike(search_term),
                Supplier.email.ilike(search_term),
                Supplier.pib.ilike(search_term),
                Supplier.city.ilike(search_term)
            )
        )

    # Sortiranje
    sort_column = getattr(Supplier, sort, Supplier.created_at)
    if order == 'desc':
        sort_column = sort_column.desc()
    query = query.order_by(sort_column)

    # Paginacija
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    suppliers_data = []
    for supplier in pagination.items:
        # Broj korisnika
        user_count = SupplierUser.query.filter_by(supplier_id=supplier.id).count()

        # Broj aktivnih artikala
        listings_count = SupplierListing.query.filter_by(
            supplier_id=supplier.id,
            is_active=True
        ).count()

        suppliers_data.append({
            'id': supplier.id,
            'name': supplier.name,
            'slug': supplier.slug,
            'email': supplier.email,
            'phone': supplier.phone,
            'city': supplier.city,
            'pib': supplier.pib,
            'status': supplier.status.value if supplier.status else None,
            'is_verified': supplier.is_verified,
            'verified_at': supplier.verified_at.isoformat() if supplier.verified_at else None,
            'rating': float(supplier.rating) if supplier.rating else None,
            'rating_count': supplier.rating_count,
            'commission_rate': float(supplier.commission_rate) if supplier.commission_rate else 0.05,
            'total_sales': float(supplier.total_sales) if supplier.total_sales else 0,
            'user_count': user_count,
            'listings_count': listings_count,
            'created_at': supplier.created_at.isoformat() if supplier.created_at else None,
        })

    return jsonify({
        'suppliers': suppliers_data,
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
        'pages': pagination.pages
    })


@bp.route('/<int:supplier_id>', methods=['GET'])
@platform_admin_required
def get_supplier(supplier_id):
    """Detalji dobavljača."""
    supplier = Supplier.query.get_or_404(supplier_id)

    # Korisnici
    users = [{
        'id': u.id,
        'email': u.email,
        'ime': u.ime,
        'prezime': u.prezime,
        'phone': u.phone,
        'is_admin': u.is_admin,
        'is_active': u.is_active,
        'last_login_at': u.last_login_at.isoformat() if u.last_login_at else None,
        'created_at': u.created_at.isoformat() if u.created_at else None,
    } for u in supplier.users.all()]

    # Statistika artikala
    total_listings = SupplierListing.query.filter_by(supplier_id=supplier.id).count()
    active_listings = SupplierListing.query.filter_by(
        supplier_id=supplier.id, is_active=True
    ).count()

    return jsonify({
        'id': supplier.id,
        'name': supplier.name,
        'slug': supplier.slug,
        'pib': supplier.pib,
        'maticni_broj': supplier.maticni_broj,
        'address': supplier.address,
        'city': supplier.city,
        'email': supplier.email,
        'phone': supplier.phone,
        'website': supplier.website,
        'status': supplier.status.value if supplier.status else None,
        'is_verified': supplier.is_verified,
        'verified_at': supplier.verified_at.isoformat() if supplier.verified_at else None,
        'commission_rate': float(supplier.commission_rate) if supplier.commission_rate else 0.05,
        'total_sales': float(supplier.total_sales) if supplier.total_sales else 0,
        'total_commission': float(supplier.total_commission) if supplier.total_commission else 0,
        'rating': float(supplier.rating) if supplier.rating else None,
        'rating_count': supplier.rating_count,
        'users': users,
        'stats': {
            'total_listings': total_listings,
            'active_listings': active_listings,
        },
        'created_at': supplier.created_at.isoformat() if supplier.created_at else None,
        'updated_at': supplier.updated_at.isoformat() if supplier.updated_at else None,
    })


# ============================================================================
# KREIRANJE DOBAVLJAČA
# ============================================================================

@bp.route('', methods=['POST'])
@platform_admin_required
def create_supplier():
    """
    Kreiranje novog dobavljača.

    Body:
        - name: Naziv dobavljača (obavezno)
        - email: Email (obavezno)
        - pib: PIB (opciono)
        - maticni_broj: Matični broj (opciono)
        - address: Adresa (opciono)
        - city: Grad (opciono)
        - phone: Telefon (opciono)
        - website: Web sajt (opciono)
        - commission_rate: Stopa komisije (default 0.05 = 5%)
        - auto_verify: Da li odmah verifikovati (default false)
        - admin_user: Podaci za admin korisnika dobavljača (opciono)
            - email: Email korisnika
            - password: Lozinka
            - ime: Ime
            - prezime: Prezime
            - phone: Telefon
    """
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # Validacija obaveznih polja
    if not data.get('name'):
        return jsonify({'error': 'Name is required'}), 400
    if not data.get('email'):
        return jsonify({'error': 'Email is required'}), 400

    # Provera da li email već postoji
    if Supplier.query.filter_by(email=data['email']).first():
        return jsonify({'error': 'Supplier with this email already exists'}), 400

    # Provera da li PIB već postoji
    if data.get('pib'):
        if Supplier.query.filter_by(pib=data['pib']).first():
            return jsonify({'error': 'Supplier with this PIB already exists'}), 400

    # Generisanje slug-a
    slug = generate_slug(data['name'])
    base_slug = slug
    counter = 1
    while Supplier.query.filter_by(slug=slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    # Kreiranje dobavljača
    supplier = Supplier(
        name=data['name'],
        slug=slug,
        email=data['email'],
        pib=data.get('pib'),
        maticni_broj=data.get('maticni_broj'),
        address=data.get('address'),
        city=data.get('city'),
        phone=data.get('phone'),
        website=data.get('website'),
        commission_rate=data.get('commission_rate', 0.05),
        status=SupplierStatus.ACTIVE if data.get('auto_verify') else SupplierStatus.PENDING,
        is_verified=data.get('auto_verify', False),
        verified_at=datetime.utcnow() if data.get('auto_verify') else None,
    )

    db.session.add(supplier)
    db.session.flush()  # Da dobijemo ID

    # Kreiranje admin korisnika ako su podaci prosleđeni
    admin_user_data = data.get('admin_user')
    created_user = None
    if admin_user_data:
        if not admin_user_data.get('email'):
            return jsonify({'error': 'Admin user email is required'}), 400
        if not admin_user_data.get('password'):
            return jsonify({'error': 'Admin user password is required'}), 400
        if not admin_user_data.get('ime'):
            return jsonify({'error': 'Admin user first name is required'}), 400
        if not admin_user_data.get('prezime'):
            return jsonify({'error': 'Admin user last name is required'}), 400

        user = SupplierUser(
            supplier_id=supplier.id,
            email=admin_user_data['email'],
            ime=admin_user_data['ime'],
            prezime=admin_user_data['prezime'],
            phone=admin_user_data.get('phone'),
            is_admin=True,
            is_active=True,
        )
        user.set_password(admin_user_data['password'])
        db.session.add(user)
        created_user = {
            'email': user.email,
            'ime': user.ime,
            'prezime': user.prezime,
        }

    # Log aktivnosti
    AdminActivityLog.log(
        action_type=AdminActionType.CREATE_SUPPLIER,
        target_type='supplier',
        target_id=supplier.id,
        target_name=supplier.name,
    )

    db.session.commit()

    return jsonify({
        'message': 'Supplier created successfully',
        'supplier': {
            'id': supplier.id,
            'name': supplier.name,
            'slug': supplier.slug,
            'email': supplier.email,
            'status': supplier.status.value,
            'is_verified': supplier.is_verified,
        },
        'admin_user': created_user,
    }), 201


# ============================================================================
# IZMENA DOBAVLJAČA
# ============================================================================

@bp.route('/<int:supplier_id>', methods=['PUT'])
@platform_admin_required
def update_supplier(supplier_id):
    """Izmena podataka dobavljača."""
    supplier = Supplier.query.get_or_404(supplier_id)
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # Ažuriranje dozvoljenih polja
    allowed_fields = [
        'name', 'email', 'pib', 'maticni_broj', 'address', 'city',
        'phone', 'website', 'commission_rate'
    ]

    for field in allowed_fields:
        if field in data:
            setattr(supplier, field, data[field])

    # Ako se menja ime, ažuriraj slug
    if 'name' in data:
        slug = generate_slug(data['name'])
        base_slug = slug
        counter = 1
        while Supplier.query.filter(
            Supplier.slug == slug,
            Supplier.id != supplier_id
        ).first():
            slug = f"{base_slug}-{counter}"
            counter += 1
        supplier.slug = slug

    # Log aktivnosti
    AdminActivityLog.log(
        action_type=AdminActionType.UPDATE_SUPPLIER,
        target_type='supplier',
        target_id=supplier.id,
        target_name=supplier.name,
    )

    db.session.commit()

    return jsonify({
        'message': 'Supplier updated successfully',
        'supplier': supplier.to_dict(),
    })


# ============================================================================
# STATUS AKCIJE
# ============================================================================

@bp.route('/<int:supplier_id>/verify', methods=['POST'])
@platform_admin_required
def verify_supplier(supplier_id):
    """Verifikacija dobavljača - aktivira nalog."""
    supplier = Supplier.query.get_or_404(supplier_id)

    if supplier.is_verified:
        return jsonify({'error': 'Supplier is already verified'}), 400

    supplier.is_verified = True
    supplier.verified_at = datetime.utcnow()
    supplier.status = SupplierStatus.ACTIVE

    # Log aktivnosti
    AdminActivityLog.log(
        action_type=AdminActionType.VERIFY_SUPPLIER,
        target_type='supplier',
        target_id=supplier.id,
        target_name=supplier.name,
    )

    db.session.commit()

    return jsonify({
        'message': 'Supplier verified successfully',
        'supplier': supplier.to_dict(),
    })


@bp.route('/<int:supplier_id>/suspend', methods=['POST'])
@platform_admin_required
def suspend_supplier(supplier_id):
    """Suspenzija dobavljača."""
    supplier = Supplier.query.get_or_404(supplier_id)
    data = request.get_json() or {}

    if supplier.status == SupplierStatus.SUSPENDED:
        return jsonify({'error': 'Supplier is already suspended'}), 400

    supplier.status = SupplierStatus.SUSPENDED
    reason = data.get('reason', 'No reason provided')

    # Log aktivnosti
    AdminActivityLog.log(
        action_type=AdminActionType.SUSPEND_SUPPLIER,
        target_type='supplier',
        target_id=supplier.id,
        target_name=supplier.name,
        details={'reason': reason},
    )

    db.session.commit()

    return jsonify({
        'message': 'Supplier suspended successfully',
        'supplier': supplier.to_dict(),
    })


@bp.route('/<int:supplier_id>/activate', methods=['POST'])
@platform_admin_required
def activate_supplier(supplier_id):
    """Reaktivacija suspendovanog dobavljača."""
    supplier = Supplier.query.get_or_404(supplier_id)

    if supplier.status == SupplierStatus.ACTIVE:
        return jsonify({'error': 'Supplier is already active'}), 400

    if not supplier.is_verified:
        return jsonify({'error': 'Supplier must be verified first'}), 400

    supplier.status = SupplierStatus.ACTIVE

    # Log aktivnosti
    AdminActivityLog.log(
        action_type=AdminActionType.ACTIVATE_SUPPLIER,
        target_type='supplier',
        target_id=supplier.id,
        target_name=supplier.name,
    )

    db.session.commit()

    return jsonify({
        'message': 'Supplier activated successfully',
        'supplier': supplier.to_dict(),
    })


@bp.route('/<int:supplier_id>/status', methods=['PUT'])
@platform_admin_required
def change_supplier_status(supplier_id):
    """
    Unified status change endpoint za frontend.

    Podržava: PENDING, ACTIVE, SUSPENDED
    """
    supplier = Supplier.query.get_or_404(supplier_id)
    data = request.get_json()

    if not data or 'status' not in data:
        return jsonify({'error': 'Status is required'}), 400

    new_status_str = data['status'].upper()

    try:
        new_status = SupplierStatus[new_status_str]
    except KeyError:
        return jsonify({'error': f'Invalid status: {new_status_str}'}), 400

    old_status = supplier.status

    # Posebna pravila za prelaze statusa
    if new_status == SupplierStatus.ACTIVE:
        if old_status == SupplierStatus.PENDING:
            # Verifikacija - aktivacija iz pending stanja
            supplier.is_verified = True
            supplier.verified_at = datetime.utcnow()
            supplier.status = SupplierStatus.ACTIVE
            action_type = AdminActionType.VERIFY
            description = f"Verifikovan i aktiviran dobavljač: {supplier.name}"
        elif old_status == SupplierStatus.SUSPENDED:
            # Reaktivacija
            supplier.status = SupplierStatus.ACTIVE
            action_type = AdminActionType.ACTIVATE
            description = f"Reaktiviran dobavljač: {supplier.name}"
        else:
            return jsonify({'error': 'Supplier is already active'}), 400

    elif new_status == SupplierStatus.SUSPENDED:
        if old_status == SupplierStatus.SUSPENDED:
            return jsonify({'error': 'Supplier is already suspended'}), 400
        supplier.status = SupplierStatus.SUSPENDED
        action_type = AdminActionType.SUSPEND
        description = f"Suspendovan dobavljač: {supplier.name}"
        if data.get('reason'):
            description += f" - Razlog: {data['reason']}"

    elif new_status == SupplierStatus.PENDING:
        # Obično se ne koristi, ali dozvoljavamo
        supplier.status = SupplierStatus.PENDING
        action_type = AdminActionType.UPDATE
        description = f"Status dobavljača vraćen na čekanje: {supplier.name}"

    else:
        return jsonify({'error': 'Unsupported status change'}), 400

    # Log aktivnosti - mapiranje na nove action tipove
    action_map = {
        AdminActionType.VERIFY: AdminActionType.VERIFY_SUPPLIER,
        AdminActionType.ACTIVATE: AdminActionType.ACTIVATE_SUPPLIER,
        AdminActionType.SUSPEND: AdminActionType.SUSPEND_SUPPLIER,
        AdminActionType.UPDATE: AdminActionType.UPDATE_SUPPLIER,
    }
    mapped_action = action_map.get(action_type, AdminActionType.UPDATE_SUPPLIER)

    AdminActivityLog.log(
        action_type=mapped_action,
        target_type='supplier',
        target_id=supplier.id,
        target_name=supplier.name,
        old_status=old_status.value if old_status else None,
        new_status=new_status.value if new_status else None,
    )

    db.session.commit()

    return jsonify({
        'message': 'Status updated successfully',
        'supplier': supplier.to_dict(),
    })


# ============================================================================
# UPRAVLJANJE KORISNICIMA DOBAVLJAČA
# ============================================================================

@bp.route('/<int:supplier_id>/users', methods=['GET'])
@platform_admin_required
def list_supplier_users(supplier_id):
    """Lista korisnika dobavljača."""
    supplier = Supplier.query.get_or_404(supplier_id)

    users = [{
        'id': u.id,
        'email': u.email,
        'ime': u.ime,
        'prezime': u.prezime,
        'full_name': u.full_name,
        'phone': u.phone,
        'is_admin': u.is_admin,
        'is_active': u.is_active,
        'last_login_at': u.last_login_at.isoformat() if u.last_login_at else None,
        'created_at': u.created_at.isoformat() if u.created_at else None,
    } for u in supplier.users.all()]

    return jsonify({
        'supplier_id': supplier.id,
        'supplier_name': supplier.name,
        'users': users,
    })


@bp.route('/<int:supplier_id>/users', methods=['POST'])
@platform_admin_required
def create_supplier_user(supplier_id):
    """Kreiranje novog korisnika dobavljača."""
    supplier = Supplier.query.get_or_404(supplier_id)
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # Validacija
    required_fields = ['email', 'password', 'ime', 'prezime']
    for field in required_fields:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400

    # Provera da li email već postoji za ovog dobavljača
    existing = SupplierUser.query.filter_by(
        supplier_id=supplier.id,
        email=data['email']
    ).first()
    if existing:
        return jsonify({'error': 'User with this email already exists'}), 400

    user = SupplierUser(
        supplier_id=supplier.id,
        email=data['email'],
        ime=data['ime'],
        prezime=data['prezime'],
        phone=data.get('phone'),
        is_admin=data.get('is_admin', False),
        is_active=True,
    )
    user.set_password(data['password'])
    db.session.add(user)

    # Log aktivnosti
    AdminActivityLog.log(
        action_type=AdminActionType.CREATE_SUPPLIER_USER,
        target_type='supplier_user',
        target_id=user.id,
        target_name=f"{user.email} ({supplier.name})",
    )

    db.session.commit()

    return jsonify({
        'message': 'User created successfully',
        'user': {
            'id': user.id,
            'email': user.email,
            'ime': user.ime,
            'prezime': user.prezime,
            'is_admin': user.is_admin,
        },
    }), 201


@bp.route('/<int:supplier_id>/users/<int:user_id>', methods=['PUT'])
@platform_admin_required
def update_supplier_user(supplier_id, user_id):
    """Izmena korisnika dobavljača."""
    supplier = Supplier.query.get_or_404(supplier_id)
    user = SupplierUser.query.filter_by(
        id=user_id,
        supplier_id=supplier_id
    ).first_or_404()

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # Ažuriranje dozvoljenih polja
    allowed_fields = ['ime', 'prezime', 'phone', 'is_admin', 'is_active']
    for field in allowed_fields:
        if field in data:
            setattr(user, field, data[field])

    # Ako se menja lozinka
    if data.get('password'):
        user.set_password(data['password'])

    # Log aktivnosti
    AdminActivityLog.log(
        action_type=AdminActionType.UPDATE_SUPPLIER_USER,
        target_type='supplier_user',
        target_id=user.id,
        target_name=user.email,
    )

    db.session.commit()

    return jsonify({
        'message': 'User updated successfully',
        'user': {
            'id': user.id,
            'email': user.email,
            'ime': user.ime,
            'prezime': user.prezime,
            'is_admin': user.is_admin,
            'is_active': user.is_active,
        },
    })


@bp.route('/<int:supplier_id>/users/<int:user_id>/reset-password', methods=['POST'])
@platform_admin_required
def reset_supplier_user_password(supplier_id, user_id):
    """Reset lozinke korisnika dobavljača."""
    supplier = Supplier.query.get_or_404(supplier_id)
    user = SupplierUser.query.filter_by(
        id=user_id,
        supplier_id=supplier_id
    ).first_or_404()

    data = request.get_json()
    if not data or not data.get('new_password'):
        return jsonify({'error': 'new_password is required'}), 400

    user.set_password(data['new_password'])

    # Log aktivnosti
    AdminActivityLog.log(
        action_type=AdminActionType.UPDATE_SUPPLIER_USER,
        target_type='supplier_user',
        target_id=user.id,
        target_name=user.email,
        details={'action': 'password_reset'},
    )

    db.session.commit()

    return jsonify({
        'message': 'Password reset successfully',
    })


# ============================================================================
# STATISTIKA
# ============================================================================

@bp.route('/stats', methods=['GET'])
@platform_admin_required
def get_suppliers_stats():
    """Statistika dobavljača."""
    total = Supplier.query.count()
    pending = Supplier.query.filter_by(status=SupplierStatus.PENDING).count()
    active = Supplier.query.filter_by(status=SupplierStatus.ACTIVE).count()
    suspended = Supplier.query.filter_by(status=SupplierStatus.SUSPENDED).count()
    verified = Supplier.query.filter_by(is_verified=True).count()

    # Ukupan broj artikala
    total_listings = SupplierListing.query.count()
    active_listings = SupplierListing.query.filter_by(is_active=True).count()

    # Ukupna prodaja i komisija
    sales_data = db.session.query(
        func.sum(Supplier.total_sales),
        func.sum(Supplier.total_commission)
    ).first()

    return jsonify({
        'suppliers': {
            'total': total,
            'pending': pending,
            'active': active,
            'suspended': suspended,
            'verified': verified,
        },
        'listings': {
            'total': total_listings,
            'active': active_listings,
        },
        'financials': {
            'total_sales': float(sales_data[0] or 0),
            'total_commission': float(sales_data[1] or 0),
        },
    })
