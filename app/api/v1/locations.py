"""
Service Locations API
"""
from flask import Blueprint, request, g
from app.extensions import db
from app.models import ServiceLocation, TenantUser, UserLocation
from app.api.middleware.auth import jwt_required
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

bp = Blueprint('locations', __name__, url_prefix='/locations')


# ============== Pydantic Schemas ==============

class LocationCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    address: Optional[str] = Field(None, max_length=300)
    city: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    phone: Optional[str] = Field(None, max_length=30)
    email: Optional[EmailStr] = None
    is_primary: Optional[bool] = False


class LocationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    address: Optional[str] = Field(None, max_length=300)
    city: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    phone: Optional[str] = Field(None, max_length=30)
    email: Optional[EmailStr] = None
    working_hours_json: Optional[dict] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    coverage_radius_km: Optional[int] = None
    is_active: Optional[bool] = None


# ============== Routes ==============

@bp.route('', methods=['GET'])
@jwt_required
def list_locations():
    """List all locations for tenant"""
    include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'

    query = ServiceLocation.query.filter_by(tenant_id=g.tenant_id)

    if not include_inactive:
        query = query.filter_by(is_active=True)

    locations = query.order_by(ServiceLocation.is_primary.desc(), ServiceLocation.name).all()

    return {
        'locations': [{
            'id': loc.id,
            'name': loc.name,
            'address': loc.address,
            'city': loc.city,
            'postal_code': loc.postal_code,
            'phone': loc.phone,
            'email': loc.email,
            'is_primary': loc.is_primary,
            'is_active': loc.is_active,
            'has_separate_inventory': loc.has_separate_inventory,
            'working_hours': loc.working_hours_json,
            'created_at': loc.created_at.isoformat()
        } for loc in locations],
        'total': len(locations)
    }


@bp.route('/<int:location_id>', methods=['GET'])
@jwt_required
def get_location(location_id):
    """Get single location details"""
    location = ServiceLocation.query.filter_by(
        id=location_id,
        tenant_id=g.tenant_id
    ).first()

    if not location:
        return {'error': 'Location not found'}, 404

    # Get users assigned to this location
    user_locations = UserLocation.query.filter_by(
        location_id=location_id,
        is_active=True
    ).all()

    users = []
    for ul in user_locations:
        user = TenantUser.query.get(ul.user_id)
        if user and user.is_active:
            users.append({
                'id': user.id,
                'ime': user.ime,
                'prezime': user.prezime,
                'role': user.role.value,
                'is_primary': ul.is_primary,
                'can_manage': ul.can_manage
            })

    return {
        'id': location.id,
        'name': location.name,
        'address': location.address,
        'city': location.city,
        'postal_code': location.postal_code,
        'phone': location.phone,
        'email': location.email,
        'is_primary': location.is_primary,
        'is_active': location.is_active,
        'has_separate_inventory': location.has_separate_inventory,
        'working_hours': location.working_hours_json,
        'latitude': location.latitude,
        'longitude': location.longitude,
        'coverage_radius_km': location.coverage_radius_km,
        'created_at': location.created_at.isoformat(),
        'users': users
    }


@bp.route('', methods=['POST'])
@jwt_required
def create_location():
    """Create new location (admin only)"""
    user = TenantUser.query.get(g.user_id)
    if not user or user.role.value not in ['OWNER', 'ADMIN', 'MANAGER']:
        return {'error': 'Permission denied'}, 403

    try:
        data = LocationCreate(**request.json)
    except Exception as e:
        return {'error': str(e)}, 400

    # If this is primary, remove primary from others
    if data.is_primary:
        ServiceLocation.query.filter_by(
            tenant_id=g.tenant_id,
            is_primary=True
        ).update({'is_primary': False})

    location = ServiceLocation(
        tenant_id=g.tenant_id,
        name=data.name,
        address=data.address,
        city=data.city,
        postal_code=data.postal_code,
        phone=data.phone,
        email=data.email,
        is_primary=data.is_primary,
        is_active=True,
        has_separate_inventory=False
    )

    db.session.add(location)
    db.session.commit()

    return {
        'message': 'Location created',
        'location_id': location.id
    }, 201


@bp.route('/<int:location_id>', methods=['PUT'])
@jwt_required
def update_location(location_id):
    """Update location"""
    user = TenantUser.query.get(g.user_id)
    if not user or user.role.value not in ['OWNER', 'ADMIN', 'MANAGER']:
        return {'error': 'Permission denied'}, 403

    location = ServiceLocation.query.filter_by(
        id=location_id,
        tenant_id=g.tenant_id
    ).first()

    if not location:
        return {'error': 'Location not found'}, 404

    try:
        data = LocationUpdate(**request.json)
    except Exception as e:
        return {'error': str(e)}, 400

    # Update fields
    if data.name is not None:
        location.name = data.name
    if data.address is not None:
        location.address = data.address
    if data.city is not None:
        location.city = data.city
    if data.postal_code is not None:
        location.postal_code = data.postal_code
    if data.phone is not None:
        location.phone = data.phone
    if data.email is not None:
        location.email = data.email
    if data.working_hours_json is not None:
        location.working_hours_json = data.working_hours_json
    if data.latitude is not None:
        location.latitude = data.latitude
    if data.longitude is not None:
        location.longitude = data.longitude
    if data.coverage_radius_km is not None:
        location.coverage_radius_km = data.coverage_radius_km
    if data.is_active is not None:
        location.is_active = data.is_active

    db.session.commit()

    return {'message': 'Location updated', 'location_id': location.id}


@bp.route('/<int:location_id>', methods=['DELETE'])
@jwt_required
def delete_location(location_id):
    """Delete location (soft delete)"""
    user = TenantUser.query.get(g.user_id)
    if not user or user.role.value not in ['OWNER', 'ADMIN']:
        return {'error': 'Admin access required'}, 403

    location = ServiceLocation.query.filter_by(
        id=location_id,
        tenant_id=g.tenant_id
    ).first()

    if not location:
        return {'error': 'Location not found'}, 404

    if location.is_primary:
        return {'error': 'Cannot delete primary location'}, 400

    # Soft delete
    location.is_active = False
    db.session.commit()

    return {'message': 'Location deleted'}


@bp.route('/<int:location_id>/set-primary', methods=['POST'])
@jwt_required
def set_primary_location(location_id):
    """Set location as primary"""
    user = TenantUser.query.get(g.user_id)
    if not user or user.role.value not in ['OWNER', 'ADMIN']:
        return {'error': 'Admin access required'}, 403

    location = ServiceLocation.query.filter_by(
        id=location_id,
        tenant_id=g.tenant_id
    ).first()

    if not location:
        return {'error': 'Location not found'}, 404

    if not location.is_active:
        return {'error': 'Cannot set inactive location as primary'}, 400

    # Remove primary from all
    ServiceLocation.query.filter_by(
        tenant_id=g.tenant_id,
        is_primary=True
    ).update({'is_primary': False})

    # Set this one as primary
    location.is_primary = True
    db.session.commit()

    return {'message': 'Primary location updated', 'location_id': location.id}


@bp.route('/<int:location_id>/users', methods=['POST'])
@jwt_required
def assign_user_to_location(location_id):
    """Assign user to location"""
    user = TenantUser.query.get(g.user_id)
    if not user or user.role.value not in ['OWNER', 'ADMIN', 'MANAGER']:
        return {'error': 'Permission denied'}, 403

    location = ServiceLocation.query.filter_by(
        id=location_id,
        tenant_id=g.tenant_id
    ).first()

    if not location:
        return {'error': 'Location not found'}, 404

    data = request.json or {}
    user_id = data.get('user_id')
    is_primary = data.get('is_primary', False)
    can_manage = data.get('can_manage', False)

    if not user_id:
        return {'error': 'user_id required'}, 400

    target_user = TenantUser.query.filter_by(
        id=user_id,
        tenant_id=g.tenant_id
    ).first()

    if not target_user:
        return {'error': 'User not found'}, 404

    # Check if already assigned
    existing = UserLocation.query.filter_by(
        user_id=user_id,
        location_id=location_id
    ).first()

    if existing:
        existing.is_primary = is_primary
        existing.can_manage = can_manage
        existing.is_active = True
    else:
        user_location = UserLocation(
            user_id=user_id,
            location_id=location_id,
            is_primary=is_primary,
            can_manage=can_manage,
            is_active=True
        )
        db.session.add(user_location)

    db.session.commit()

    return {'message': 'User assigned to location'}


@bp.route('/<int:location_id>/users/<int:user_id>', methods=['DELETE'])
@jwt_required
def remove_user_from_location(location_id, user_id):
    """Remove user from location"""
    current_user = TenantUser.query.get(g.user_id)
    if not current_user or current_user.role.value not in ['OWNER', 'ADMIN', 'MANAGER']:
        return {'error': 'Permission denied'}, 403

    user_location = UserLocation.query.filter_by(
        user_id=user_id,
        location_id=location_id
    ).first()

    if not user_location:
        return {'error': 'User not assigned to this location'}, 404

    user_location.is_active = False
    db.session.commit()

    return {'message': 'User removed from location'}
