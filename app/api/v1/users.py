"""
Team Users Management API
"""
from flask import Blueprint, request, g
from app.extensions import db
from app.models import TenantUser, UserRole, UserLocation, ServiceLocation
from app.api.middleware.auth import jwt_required
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime

bp = Blueprint('users', __name__, url_prefix='/users')


# ============== Pydantic Schemas ==============

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)  # Obavezno za login
    password: str = Field(..., min_length=6)
    email: Optional[EmailStr] = None  # Opciono - za notifikacije
    ime: str = Field(..., min_length=2, max_length=50)
    prezime: str = Field(..., min_length=2, max_length=50)
    phone: Optional[str] = Field(None, max_length=30)
    role: str = Field(default='TECHNICIAN')
    location_ids: Optional[List[int]] = None


class UserUpdate(BaseModel):
    ime: Optional[str] = Field(None, min_length=2, max_length=50)
    prezime: Optional[str] = Field(None, min_length=2, max_length=50)
    phone: Optional[str] = Field(None, max_length=30)
    role: Optional[str] = None
    is_active: Optional[bool] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6)


class PasswordReset(BaseModel):
    new_password: str = Field(..., min_length=6)


# ============== Routes ==============

@bp.route('', methods=['GET'])
@jwt_required
def list_users():
    """List all users for tenant"""
    include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'
    role_filter = request.args.get('role')
    location_id = request.args.get('location_id', type=int)

    query = TenantUser.query.filter_by(tenant_id=g.tenant_id)

    if not include_inactive:
        query = query.filter_by(is_active=True)

    if role_filter:
        try:
            role = UserRole[role_filter.upper()]
            query = query.filter_by(role=role)
        except KeyError:
            pass

    users = query.order_by(TenantUser.ime).all()

    # Filter by location if specified
    if location_id:
        user_ids = [ul.user_id for ul in UserLocation.query.filter_by(
            location_id=location_id, is_active=True
        ).all()]
        users = [u for u in users if u.id in user_ids]

    result = []
    for user in users:
        # Get user locations
        user_locs = UserLocation.query.filter_by(user_id=user.id, is_active=True).all()
        locations = []
        for ul in user_locs:
            loc = ServiceLocation.query.get(ul.location_id)
            if loc:
                locations.append({
                    'id': loc.id,
                    'name': loc.name,
                    'is_primary': ul.is_primary,
                    'can_manage': ul.can_manage
                })

        result.append({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'ime': user.ime,
            'prezime': user.prezime,
            'phone': user.phone,
            'role': user.role.value,
            'is_active': user.is_active,
            'last_login_at': user.last_login_at.isoformat() if user.last_login_at else None,
            'created_at': user.created_at.isoformat(),
            'locations': locations
        })

    return {
        'users': result,
        'total': len(result)
    }


@bp.route('/<int:user_id>', methods=['GET'])
@jwt_required
def get_user(user_id):
    """Get single user details"""
    user = TenantUser.query.filter_by(
        id=user_id,
        tenant_id=g.tenant_id
    ).first()

    if not user:
        return {'error': 'User not found'}, 404

    # Get user locations
    user_locs = UserLocation.query.filter_by(user_id=user.id, is_active=True).all()
    locations = []
    for ul in user_locs:
        loc = ServiceLocation.query.get(ul.location_id)
        if loc:
            locations.append({
                'id': loc.id,
                'name': loc.name,
                'city': loc.city,
                'is_primary': ul.is_primary,
                'can_manage': ul.can_manage
            })

    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'ime': user.ime,
        'prezime': user.prezime,
        'phone': user.phone,
        'role': user.role.value,
        'is_active': user.is_active,
        'last_login_at': user.last_login_at.isoformat() if user.last_login_at else None,
        'created_at': user.created_at.isoformat(),
        'locations': locations
    }


@bp.route('', methods=['POST'])
@jwt_required
def create_user():
    """Create new user (admin only)"""
    current_user = TenantUser.query.get(g.user_id)
    if not current_user or current_user.role.value not in ['OWNER', 'ADMIN']:
        return {'error': 'Admin access required'}, 403

    try:
        data = UserCreate(**request.json)
    except Exception as e:
        return {'error': str(e)}, 400

    # Check username uniqueness within tenant
    existing = TenantUser.query.filter_by(
        tenant_id=g.tenant_id,
        username=data.username
    ).first()

    if existing:
        return {'error': 'Korisničko ime već postoji'}, 400

    # Check email uniqueness within tenant (if provided)
    if data.email:
        existing_email = TenantUser.query.filter_by(
            tenant_id=g.tenant_id,
            email=data.email
        ).first()
        if existing_email:
            return {'error': 'Email već postoji'}, 400

    # Validate role
    try:
        role = UserRole[data.role.upper()]
    except KeyError:
        return {'error': f'Invalid role. Must be one of: {[r.value for r in UserRole]}'}, 400

    # Owner can only create lower roles
    if role == UserRole.OWNER and current_user.role != UserRole.OWNER:
        return {'error': 'Only owner can create owner accounts'}, 403

    user = TenantUser(
        tenant_id=g.tenant_id,
        username=data.username,
        email=data.email,  # Može biti None
        ime=data.ime,
        prezime=data.prezime,
        phone=data.phone,
        role=role,
        is_active=True
    )
    user.set_password(data.password)

    db.session.add(user)
    db.session.flush()  # Get ID

    # Assign to locations
    if data.location_ids:
        for loc_id in data.location_ids:
            loc = ServiceLocation.query.filter_by(
                id=loc_id,
                tenant_id=g.tenant_id
            ).first()
            if loc:
                user_loc = UserLocation(
                    user_id=user.id,
                    location_id=loc_id,
                    is_primary=len(data.location_ids) == 1,
                    can_manage=role.value in ['OWNER', 'ADMIN', 'MANAGER'],
                    is_active=True
                )
                db.session.add(user_loc)

    db.session.commit()

    return {
        'message': 'User created',
        'user_id': user.id
    }, 201


@bp.route('/<int:user_id>', methods=['PUT'])
@jwt_required
def update_user(user_id):
    """Update user"""
    current_user = TenantUser.query.get(g.user_id)
    if not current_user:
        return {'error': 'Unauthorized'}, 401

    user = TenantUser.query.filter_by(
        id=user_id,
        tenant_id=g.tenant_id
    ).first()

    if not user:
        return {'error': 'User not found'}, 404

    # Check permissions
    is_self = user_id == g.user_id
    is_admin = current_user.role.value in ['OWNER', 'ADMIN']

    if not is_self and not is_admin:
        return {'error': 'Permission denied'}, 403

    try:
        data = UserUpdate(**request.json)
    except Exception as e:
        return {'error': str(e)}, 400

    # Update fields
    if data.ime is not None:
        user.ime = data.ime
    if data.prezime is not None:
        user.prezime = data.prezime
    if data.phone is not None:
        user.phone = data.phone

    # Only admin can change role and active status
    if is_admin:
        if data.role is not None:
            try:
                new_role = UserRole[data.role.upper()]
                # Can't change owner role unless you're owner
                if user.role == UserRole.OWNER and current_user.role != UserRole.OWNER:
                    return {'error': 'Cannot change owner role'}, 403
                user.role = new_role
            except KeyError:
                return {'error': 'Invalid role'}, 400

        if data.is_active is not None:
            # Can't deactivate yourself
            if not data.is_active and is_self:
                return {'error': 'Cannot deactivate yourself'}, 400
            # Can't deactivate owner
            if not data.is_active and user.role == UserRole.OWNER:
                return {'error': 'Cannot deactivate owner'}, 400
            user.is_active = data.is_active

    db.session.commit()

    return {'message': 'User updated', 'user_id': user.id}


@bp.route('/<int:user_id>', methods=['DELETE'])
@jwt_required
def delete_user(user_id):
    """Delete user (soft delete)"""
    current_user = TenantUser.query.get(g.user_id)
    if not current_user or current_user.role.value not in ['OWNER', 'ADMIN']:
        return {'error': 'Admin access required'}, 403

    if user_id == g.user_id:
        return {'error': 'Cannot delete yourself'}, 400

    user = TenantUser.query.filter_by(
        id=user_id,
        tenant_id=g.tenant_id
    ).first()

    if not user:
        return {'error': 'User not found'}, 404

    if user.role == UserRole.OWNER:
        return {'error': 'Cannot delete owner'}, 400

    # Soft delete
    user.is_active = False
    db.session.commit()

    return {'message': 'User deleted'}


@bp.route('/me', methods=['GET'])
@jwt_required
def get_current_user():
    """Get current user profile"""
    user = TenantUser.query.get(g.user_id)
    if not user:
        return {'error': 'User not found'}, 404

    # Get user locations
    user_locs = UserLocation.query.filter_by(user_id=user.id, is_active=True).all()
    locations = []
    for ul in user_locs:
        loc = ServiceLocation.query.get(ul.location_id)
        if loc:
            locations.append({
                'id': loc.id,
                'name': loc.name,
                'city': loc.city,
                'is_primary': ul.is_primary,
                'can_manage': ul.can_manage
            })

    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'ime': user.ime,
        'prezime': user.prezime,
        'phone': user.phone,
        'role': user.role.value,
        'locations': locations,
        'last_login_at': user.last_login_at.isoformat() if user.last_login_at else None,
        'created_at': user.created_at.isoformat()
    }


@bp.route('/me/password', methods=['PUT'])
@jwt_required
def change_password():
    """Change own password"""
    user = TenantUser.query.get(g.user_id)
    if not user:
        return {'error': 'User not found'}, 404

    try:
        data = PasswordChange(**request.json)
    except Exception as e:
        return {'error': str(e)}, 400

    if not user.check_password(data.current_password):
        return {'error': 'Current password is incorrect'}, 400

    user.set_password(data.new_password)
    db.session.commit()

    return {'message': 'Password changed'}


@bp.route('/<int:user_id>/reset-password', methods=['POST'])
@jwt_required
def reset_user_password(user_id):
    """Reset user password (admin only)"""
    current_user = TenantUser.query.get(g.user_id)
    if not current_user or current_user.role.value not in ['OWNER', 'ADMIN']:
        return {'error': 'Admin access required'}, 403

    user = TenantUser.query.filter_by(
        id=user_id,
        tenant_id=g.tenant_id
    ).first()

    if not user:
        return {'error': 'User not found'}, 404

    try:
        data = PasswordReset(**request.json)
    except Exception as e:
        return {'error': str(e)}, 400

    user.set_password(data.new_password)
    db.session.commit()

    return {'message': 'Password reset'}


@bp.route('/roles', methods=['GET'])
@jwt_required
def list_roles():
    """List available roles"""
    return {
        'roles': [
            {'value': 'OWNER', 'label': 'Vlasnik', 'description': 'Full access'},
            {'value': 'ADMIN', 'label': 'Administrator', 'description': 'Manage users, settings'},
            {'value': 'MANAGER', 'label': 'Menadžer', 'description': 'Manage location'},
            {'value': 'TECHNICIAN', 'label': 'Serviser', 'description': 'Work on tickets'},
            {'value': 'RECEPTIONIST', 'label': 'Recepcionar', 'description': 'Create tickets'}
        ]
    }
