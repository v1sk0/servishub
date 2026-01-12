"""
Admin Auth API - autentifikacija za platform admine.

Odvojen od tenant auth-a jer platform admini imaju
pristup celom ekosistemu, ne samo jednom preduzecu.
"""

from flask import Blueprint, request, jsonify, g
from pydantic import ValidationError

from ..schemas.auth import AdminLoginRequest, RefreshTokenRequest
from ..middleware.auth import jwt_required, admin_required
from ...services.auth_service import auth_service, AuthError
from ...models import AuditLog, AuditAction
from ...extensions import db

# Blueprint za admin auth
bp = Blueprint('admin_auth', __name__, url_prefix='/auth')


@bp.route('/login', methods=['POST'])
def admin_login():
    """
    Login platform admina.

    Request body:
        - email: Admin email
        - password: Admin lozinka

    Returns:
        200: Uspesni login sa tokenima
        401: Pogresan email ili lozinka
        403: Admin nalog nije aktivan
    """
    try:
        data = AdminLoginRequest(**request.get_json())
    except ValidationError as e:
        return jsonify({
            'error': 'Validation Error',
            'details': e.errors()
        }), 400

    try:
        admin, tokens = auth_service.admin_login(data.email, data.password)

        return jsonify({
            'admin': admin.to_dict(),
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
def admin_refresh():
    """
    Osvezavanje admin tokena.

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
@admin_required
def admin_me():
    """
    Podaci o trenutno ulogovanom adminu.

    Returns:
        200: Podaci admina
        401: Neispravan token
        403: Nije admin token
    """
    admin = g.current_admin

    return jsonify({
        'admin': admin.to_dict()
    }), 200


@bp.route('/logout', methods=['POST'])
@jwt_required
@admin_required
def admin_logout():
    """
    Odjava admina.

    Returns:
        200: Uspesna odjava
    """
    admin = g.current_admin

    AuditLog.log(
        entity_type='admin_auth',
        entity_id=admin.id,
        action=AuditAction.LOGOUT,
        changes={}
    )
    db.session.commit()

    return jsonify({
        'message': 'Uspesna odjava'
    }), 200
