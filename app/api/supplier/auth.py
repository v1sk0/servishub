"""
Supplier Authentication API
"""
from flask import Blueprint, request, g
from app.extensions import db
from app.models import Supplier, SupplierUser, SupplierStatus
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime, timedelta
import jwt
import os

bp = Blueprint('supplier_auth', __name__, url_prefix='/auth')

# JWT config
JWT_SECRET = os.environ.get('JWT_SUPPLIER_SECRET_KEY', os.environ.get('JWT_SECRET_KEY', 'dev-secret'))
JWT_ALGORITHM = 'HS256'
JWT_ACCESS_EXPIRES = timedelta(hours=8)
JWT_REFRESH_EXPIRES = timedelta(days=30)


# ============== Pydantic Schemas ==============

class SupplierRegister(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(..., min_length=6)
    phone: Optional[str] = Field(None, max_length=30)
    city: Optional[str] = Field(None, max_length=100)
    pib: Optional[str] = Field(None, max_length=20)
    # User info
    ime: str = Field(..., min_length=2, max_length=50)
    prezime: str = Field(..., min_length=2, max_length=50)


class SupplierLogin(BaseModel):
    email: EmailStr
    password: str


# ============== JWT Helpers ==============

def create_supplier_tokens(supplier_id: int, user_id: int):
    """Create access and refresh tokens for supplier user"""
    now = datetime.utcnow()

    access_payload = {
        'type': 'supplier_access',
        'supplier_id': supplier_id,
        'user_id': user_id,
        'exp': now + JWT_ACCESS_EXPIRES,
        'iat': now
    }

    refresh_payload = {
        'type': 'supplier_refresh',
        'supplier_id': supplier_id,
        'user_id': user_id,
        'exp': now + JWT_REFRESH_EXPIRES,
        'iat': now
    }

    access_token = jwt.encode(access_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    refresh_token = jwt.encode(refresh_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    return access_token, refresh_token


def verify_supplier_token(token: str, token_type: str = 'supplier_access'):
    """Verify supplier JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get('type') != token_type:
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ============== Middleware ==============

def supplier_jwt_required(f):
    """Decorator for supplier-authenticated endpoints"""
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return {'error': 'Missing or invalid authorization header'}, 401

        token = auth_header.split(' ')[1]
        payload = verify_supplier_token(token, 'supplier_access')

        if not payload:
            return {'error': 'Invalid or expired token'}, 401

        # Check if supplier still active
        supplier = Supplier.query.get(payload['supplier_id'])
        if not supplier or supplier.status != SupplierStatus.ACTIVE:
            return {'error': 'Supplier account not active'}, 403

        # Check if user still active
        user = SupplierUser.query.get(payload['user_id'])
        if not user or not user.is_active:
            return {'error': 'User account not active'}, 403

        g.supplier_id = payload['supplier_id']
        g.supplier_user_id = payload['user_id']

        return f(*args, **kwargs)

    return decorated


# ============== Routes ==============

@bp.route('/register', methods=['POST'])
def register():
    """Register new supplier"""
    try:
        data = SupplierRegister(**request.json)
    except Exception as e:
        return {'error': str(e)}, 400

    # Check PIB uniqueness
    if data.pib:
        existing = Supplier.query.filter_by(pib=data.pib).first()
        if existing:
            return {'error': 'Supplier with this PIB already exists'}, 400

    # Check email uniqueness (across all suppliers)
    existing_user = SupplierUser.query.filter_by(email=data.email).first()
    if existing_user:
        return {'error': 'Email already registered'}, 400

    # Create supplier (pending status until verified)
    from slugify import slugify
    slug = slugify(data.company_name)

    # Ensure unique slug
    base_slug = slug
    counter = 1
    while Supplier.query.filter_by(slug=slug).first():
        slug = f'{base_slug}-{counter}'
        counter += 1

    supplier = Supplier(
        name=data.company_name,
        slug=slug,
        email=data.email,
        phone=data.phone,
        city=data.city,
        pib=data.pib,
        status=SupplierStatus.PENDING,
        commission_rate=5.00,  # Default 5%
        total_sales=0,
        total_commission=0,
        rating_count=0
    )
    db.session.add(supplier)
    db.session.flush()

    # Create admin user
    user = SupplierUser(
        supplier_id=supplier.id,
        email=data.email,
        ime=data.ime,
        prezime=data.prezime,
        phone=data.phone,
        is_admin=True,
        is_active=True
    )
    user.set_password(data.password)
    db.session.add(user)
    db.session.commit()

    return {
        'message': 'Registration successful. Please wait for account verification.',
        'supplier_id': supplier.id
    }, 201


@bp.route('/login', methods=['POST'])
def login():
    """Supplier login"""
    try:
        data = SupplierLogin(**request.json)
    except Exception as e:
        return {'error': str(e)}, 400

    user = SupplierUser.query.filter_by(email=data.email).first()

    if not user or not user.check_password(data.password):
        return {'error': 'Invalid email or password'}, 401

    if not user.is_active:
        return {'error': 'Account is disabled'}, 403

    supplier = Supplier.query.get(user.supplier_id)
    if not supplier:
        return {'error': 'Supplier not found'}, 404

    if supplier.status == SupplierStatus.PENDING:
        return {'error': 'Account pending verification'}, 403

    if supplier.status != SupplierStatus.ACTIVE:
        return {'error': 'Supplier account not active'}, 403

    # Update last login
    user.last_login_at = datetime.utcnow()
    db.session.commit()

    access_token, refresh_token = create_supplier_tokens(supplier.id, user.id)

    return {
        'access_token': access_token,
        'refresh_token': refresh_token,
        'token_type': 'Bearer',
        'expires_in': int(JWT_ACCESS_EXPIRES.total_seconds()),
        'supplier': {
            'id': supplier.id,
            'name': supplier.name,
            'status': supplier.status.value
        },
        'user': {
            'id': user.id,
            'email': user.email,
            'ime': user.ime,
            'prezime': user.prezime,
            'is_admin': user.is_admin
        }
    }


@bp.route('/refresh', methods=['POST'])
def refresh():
    """Refresh access token"""
    data = request.json or {}
    refresh_token = data.get('refresh_token')

    if not refresh_token:
        return {'error': 'Refresh token required'}, 400

    payload = verify_supplier_token(refresh_token, 'supplier_refresh')
    if not payload:
        return {'error': 'Invalid or expired refresh token'}, 401

    supplier = Supplier.query.get(payload['supplier_id'])
    if not supplier or supplier.status != SupplierStatus.ACTIVE:
        return {'error': 'Supplier not active'}, 403

    user = SupplierUser.query.get(payload['user_id'])
    if not user or not user.is_active:
        return {'error': 'User not active'}, 403

    access_token, new_refresh_token = create_supplier_tokens(supplier.id, user.id)

    return {
        'access_token': access_token,
        'refresh_token': new_refresh_token,
        'token_type': 'Bearer',
        'expires_in': int(JWT_ACCESS_EXPIRES.total_seconds())
    }


@bp.route('/me', methods=['GET'])
@supplier_jwt_required
def get_me():
    """Get current supplier user info"""
    user = SupplierUser.query.get(g.supplier_user_id)
    supplier = Supplier.query.get(g.supplier_id)

    return {
        'user': {
            'id': user.id,
            'email': user.email,
            'ime': user.ime,
            'prezime': user.prezime,
            'phone': user.phone,
            'is_admin': user.is_admin
        },
        'supplier': {
            'id': supplier.id,
            'name': supplier.name,
            'slug': supplier.slug,
            'email': supplier.email,
            'phone': supplier.phone,
            'city': supplier.city,
            'pib': supplier.pib,
            'status': supplier.status.value,
            'is_verified': supplier.is_verified,
            'rating': float(supplier.rating) if supplier.rating else None,
            'rating_count': supplier.rating_count,
            'total_sales': float(supplier.total_sales) if supplier.total_sales else 0,
            'commission_rate': float(supplier.commission_rate) if supplier.commission_rate else 5.0
        }
    }


@bp.route('/me', methods=['PUT'])
@supplier_jwt_required
def update_profile():
    """Update supplier profile"""
    data = request.json or {}

    user = SupplierUser.query.get(g.supplier_user_id)
    supplier = Supplier.query.get(g.supplier_id)

    # Update user fields
    if 'ime' in data:
        user.ime = data['ime']
    if 'prezime' in data:
        user.prezime = data['prezime']
    if 'phone' in data:
        user.phone = data['phone']

    # Update supplier fields (only admin can update)
    if user.is_admin:
        if 'company_name' in data:
            supplier.name = data['company_name']
        if 'company_email' in data:
            supplier.email = data['company_email']
        if 'company_phone' in data:
            supplier.phone = data['company_phone']
        if 'city' in data:
            supplier.city = data['city']

    db.session.commit()

    return {'message': 'Profile updated'}


@bp.route('/password', methods=['PUT'])
@supplier_jwt_required
def change_password():
    """Change password"""
    data = request.json or {}
    current_password = data.get('current_password')
    new_password = data.get('new_password')

    if not current_password or not new_password:
        return {'error': 'Both current and new password required'}, 400

    if len(new_password) < 6:
        return {'error': 'Password must be at least 6 characters'}, 400

    user = SupplierUser.query.get(g.supplier_user_id)

    if not user.check_password(current_password):
        return {'error': 'Current password is incorrect'}, 400

    user.set_password(new_password)
    db.session.commit()

    return {'message': 'Password changed successfully'}


@bp.route('/logout', methods=['POST'])
@supplier_jwt_required
def logout():
    """Logout (client should discard tokens)"""
    return {'message': 'Logged out successfully'}
