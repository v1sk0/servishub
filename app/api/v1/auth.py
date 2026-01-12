"""
Auth API endpoints - autentifikacija za tenant korisnike.

Ovaj blueprint pruza endpointe za:
- Registraciju novog servisa
- Login korisnika
- Refresh tokena
- Pregled trenutnog korisnika (/me)
- Promenu lozinke
"""

from flask import Blueprint, request, jsonify, g
from pydantic import ValidationError

from ..schemas.auth import (
    RegisterRequest, LoginRequest, RefreshTokenRequest,
    ChangePasswordRequest, LoginResponse, RegisterResponse,
    MeResponse, UserResponse, TenantResponse, TokenResponse
)
from ..middleware.auth import jwt_required, tenant_required
from ...services.auth_service import auth_service, AuthError
from ...models import ServiceLocation

# Blueprint za auth endpoints
bp = Blueprint('auth', __name__, url_prefix='/auth')


@bp.route('/register', methods=['POST'])
def register():
    """
    Registracija novog servisa (tenanta).

    Kreira preduzece, prvu lokaciju i owner korisnika.
    Preduzece ostaje u PENDING statusu dok admin ne odobri.

    Request body:
        - company_name: Naziv preduzeca
        - company_email: Email preduzeca
        - company_phone: Telefon (opciono)
        - pib: PIB (opciono)
        - location_name: Naziv lokacije
        - location_address: Adresa (opciono)
        - location_city: Grad
        - owner_email: Email vlasnika
        - owner_password: Lozinka
        - owner_ime: Ime
        - owner_prezime: Prezime
        - owner_phone: Telefon (opciono)

    Returns:
        201: Uspesna registracija
        400: Validaciona greska
        409: Email/PIB vec postoji
    """
    try:
        # Validiraj request body
        data = RegisterRequest(**request.get_json())
    except ValidationError as e:
        return jsonify({
            'error': 'Validation Error',
            'details': e.errors()
        }), 400

    try:
        tenant, user = auth_service.register_tenant(
            company_name=data.company_name,
            company_email=data.company_email,
            company_phone=data.company_phone,
            pib=data.pib,
            location_name=data.location_name,
            location_address=data.location_address,
            location_city=data.location_city,
            owner_email=data.owner_email,
            owner_password=data.owner_password,
            owner_ime=data.owner_ime,
            owner_prezime=data.owner_prezime,
            owner_phone=data.owner_phone
        )

        return jsonify({
            'message': 'Registracija uspesna. Vas nalog ceka odobrenje.',
            'tenant': {
                'id': tenant.id,
                'slug': tenant.slug,
                'name': tenant.name,
                'email': tenant.email,
                'status': tenant.status.value
            },
            'user': {
                'id': user.id,
                'email': user.email,
                'ime': user.ime,
                'prezime': user.prezime,
                'full_name': user.full_name,
                'role': user.role.value,
                'is_active': user.is_active
            }
        }), 201

    except AuthError as e:
        return jsonify({
            'error': 'Registration Error',
            'message': e.message
        }), e.code


@bp.route('/login', methods=['POST'])
def login():
    """
    Login korisnika.

    Request body:
        - email: Email za login
        - password: Lozinka

    Returns:
        200: Uspesni login sa tokenima
        401: Pogresan email ili lozinka
        403: Nalog nije aktivan
    """
    try:
        data = LoginRequest(**request.get_json())
    except ValidationError as e:
        return jsonify({
            'error': 'Validation Error',
            'details': e.errors()
        }), 400

    try:
        user, tenant, tokens = auth_service.login(data.email, data.password)

        return jsonify({
            'user': {
                'id': user.id,
                'email': user.email,
                'ime': user.ime,
                'prezime': user.prezime,
                'full_name': user.full_name,
                'role': user.role.value,
                'is_active': user.is_active
            },
            'tenant': {
                'id': tenant.id,
                'slug': tenant.slug,
                'name': tenant.name,
                'email': tenant.email,
                'status': tenant.status.value
            },
            'tokens': {
                'access_token': tokens['access_token'],
                'refresh_token': tokens['refresh_token'],
                'token_type': 'Bearer',
                'expires_in': tokens['expires_in']
            }
        }), 200

    except AuthError as e:
        return jsonify({
            'error': 'Login Error',
            'message': e.message
        }), e.code


@bp.route('/refresh', methods=['POST'])
def refresh():
    """
    Osvezavanje tokena.

    Request body:
        - refresh_token: Validan refresh token

    Returns:
        200: Novi access i refresh tokeni
        401: Neispravan refresh token
    """
    try:
        data = RefreshTokenRequest(**request.get_json())
    except ValidationError as e:
        return jsonify({
            'error': 'Validation Error',
            'details': e.errors()
        }), 400

    try:
        tokens = auth_service.refresh_tokens(data.refresh_token)

        return jsonify({
            'access_token': tokens['access_token'],
            'refresh_token': tokens['refresh_token'],
            'token_type': 'Bearer',
            'expires_in': tokens['expires_in']
        }), 200

    except AuthError as e:
        return jsonify({
            'error': 'Refresh Error',
            'message': e.message
        }), e.code


@bp.route('/me', methods=['GET'])
@jwt_required
@tenant_required
def me():
    """
    Podaci o trenutno ulogovanom korisniku.

    Zahteva: Authorization header sa validnim access tokenom

    Returns:
        200: Podaci korisnika, tenanta i lokacija
        401: Neispravan token
    """
    user = g.current_user
    tenant = g.current_tenant

    # Dohvati lokacije kojima korisnik ima pristup
    location_ids = user.get_accessible_location_ids()
    locations = ServiceLocation.query.filter(
        ServiceLocation.id.in_(location_ids),
        ServiceLocation.is_active == True
    ).all()

    return jsonify({
        'user': {
            'id': user.id,
            'email': user.email,
            'ime': user.ime,
            'prezime': user.prezime,
            'full_name': user.full_name,
            'role': user.role.value,
            'is_active': user.is_active
        },
        'tenant': {
            'id': tenant.id,
            'slug': tenant.slug,
            'name': tenant.name,
            'email': tenant.email,
            'status': tenant.status.value
        },
        'locations': [
            {
                'id': loc.id,
                'name': loc.name,
                'city': loc.city,
                'is_primary': loc.is_primary
            }
            for loc in locations
        ]
    }), 200


@bp.route('/change-password', methods=['POST'])
@jwt_required
@tenant_required
def change_password():
    """
    Promena lozinke trenutnog korisnika.

    Request body:
        - current_password: Trenutna lozinka
        - new_password: Nova lozinka (min 8 karaktera, slovo + broj)

    Returns:
        200: Lozinka uspesno promenjena
        400: Validaciona greska ili pogresna trenutna lozinka
    """
    try:
        data = ChangePasswordRequest(**request.get_json())
    except ValidationError as e:
        return jsonify({
            'error': 'Validation Error',
            'details': e.errors()
        }), 400

    try:
        auth_service.change_password(
            user=g.current_user,
            current_password=data.current_password,
            new_password=data.new_password
        )

        return jsonify({
            'message': 'Lozinka uspesno promenjena'
        }), 200

    except AuthError as e:
        return jsonify({
            'error': 'Password Change Error',
            'message': e.message
        }), e.code


@bp.route('/logout', methods=['POST'])
@jwt_required
def logout():
    """
    Odjava korisnika.

    Trenutno samo loguje odjavu - tokeni ostaju validni do isteka.
    Za pravu invalidaciju tokena potreban je Redis blacklist (TODO).

    Returns:
        200: Uspesna odjava
    """
    from ...models import AuditLog, AuditAction
    from ...extensions import db

    # Loguj odjavu
    if hasattr(g, 'current_user_id'):
        AuditLog.log(
            entity_type='auth',
            entity_id=g.current_user_id,
            action=AuditAction.LOGOUT,
            changes={},
            tenant_id=g.token_payload.get('tenant_id')
        )
        db.session.commit()

    return jsonify({
        'message': 'Uspesna odjava'
    }), 200
