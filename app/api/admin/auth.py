"""
Admin Auth API - autentifikacija za platform admine.

Odvojen od tenant auth-a jer platform admini imaju
pristup celom ekosistemu, ne samo jednom preduzecu.

Podrska za 2FA (TOTP) autentifikaciju.
"""

import io
import base64
from flask import Blueprint, request, jsonify, g, session
from pydantic import ValidationError, BaseModel
from typing import Optional

from ..schemas.auth import AdminLoginRequest, RefreshTokenRequest
from ..middleware.auth import jwt_required, admin_required
from ...services.auth_service import auth_service, AuthError
from ...services.security_service import SecurityEventLogger, SecurityEventType, rate_limit, RateLimits
from ...models import AuditLog, AuditAction, PlatformAdmin
from ...extensions import db

# Blueprint za admin auth
bp = Blueprint('admin_auth', __name__, url_prefix='/auth')


# Pydantic modeli za 2FA
class TwoFactorVerifyRequest(BaseModel):
    """Request za verifikaciju 2FA koda."""
    email: str
    code: str
    use_backup: bool = False


class TwoFactorSetupRequest(BaseModel):
    """Request za setup 2FA."""
    code: str  # Verifikacioni kod


class TwoFactorDisableRequest(BaseModel):
    """Request za onemogucavanje 2FA."""
    password: str  # Potvrda lozinkom


@bp.route('/login', methods=['POST'])
@rate_limit(**RateLimits.LOGIN, endpoint_name='admin_login')
def admin_login():
    """
    Login platform admina (Step 1).

    Ako je 2FA omogucen, vraca requires_2fa=true i email za sledeci korak.

    Request body:
        - email: Admin email
        - password: Admin lozinka

    Returns:
        200: Uspesni login sa tokenima (ako 2FA nije omogucen)
        200: requires_2fa=true (ako je 2FA omogucen)
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
        # Proveri email i lozinku
        admin, tokens = auth_service.admin_login(data.email, data.password)

        # Ako je 2FA omogucen, ne vracaj tokene - zahtevaj 2FA kod
        if admin.is_2fa_enabled:
            SecurityEventLogger.log_event(
                SecurityEventType.ADMIN_LOGIN_SUCCESS,
                details={'step': '1/2', '2fa_required': True},
                user_id=admin.id,
                email=admin.email
            )

            # Sacuvaj email u session za sledeci korak
            session['pending_2fa_admin_email'] = admin.email

            return jsonify({
                'requires_2fa': True,
                'email': admin.email,
                'message': 'Unesite kod iz autentifikator aplikacije'
            }), 200

        # 2FA nije omogucen - vrati tokene direktno
        SecurityEventLogger.log_admin_login(admin.id, admin.email, success=True)

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
        SecurityEventLogger.log_admin_login(0, data.email, success=False)
        return jsonify({
            'error': 'Login Error',
            'message': e.message
        }), e.code


@bp.route('/login/2fa', methods=['POST'])
@rate_limit(**RateLimits.LOGIN, endpoint_name='admin_2fa')
def admin_login_2fa():
    """
    Login platform admina (Step 2 - 2FA verifikacija).

    Request body:
        - email: Admin email
        - code: 6-cifreni TOTP kod ili backup kod
        - use_backup: Da li je backup kod (default: false)

    Returns:
        200: Uspesni login sa tokenima
        401: Neispravan 2FA kod
    """
    try:
        data = TwoFactorVerifyRequest(**request.get_json())
    except ValidationError as e:
        return jsonify({
            'error': 'Validation Error',
            'details': e.errors()
        }), 400

    # Verifikuj da li je isti email kao u prethodnom koraku
    pending_email = session.pop('pending_2fa_admin_email', None)
    if not pending_email or pending_email != data.email:
        SecurityEventLogger.log_event(
            SecurityEventType.ADMIN_LOGIN_FAILED,
            details={'reason': '2fa_session_invalid'},
            email=data.email,
            level='warning'
        )
        return jsonify({
            'error': 'Session Error',
            'message': 'Sesija je istekla. Prijavite se ponovo.'
        }), 401

    # Pronadji admina
    admin = PlatformAdmin.query.filter_by(email=data.email, is_active=True).first()
    if not admin:
        return jsonify({
            'error': 'Login Error',
            'message': 'Admin nije pronadjen'
        }), 401

    # Verifikuj kod
    code_valid = False
    if data.use_backup:
        code_valid = admin.use_backup_code(data.code)
    else:
        code_valid = admin.verify_totp(data.code)

    if not code_valid:
        SecurityEventLogger.log_event(
            SecurityEventType.ADMIN_LOGIN_FAILED,
            details={'reason': '2fa_code_invalid', 'use_backup': data.use_backup},
            user_id=admin.id,
            email=admin.email,
            level='warning'
        )
        return jsonify({
            'error': '2FA Error',
            'message': 'Neispravan kod. Pokusajte ponovo.'
        }), 401

    # Kod je validan - generiši tokene
    admin.update_last_login()
    db.session.commit()

    tokens = auth_service.generate_admin_tokens(admin)

    SecurityEventLogger.log_event(
        SecurityEventType.ADMIN_LOGIN_SUCCESS,
        details={'step': '2/2', '2fa_verified': True, 'used_backup': data.use_backup},
        user_id=admin.id,
        email=admin.email
    )

    return jsonify({
        'admin': admin.to_dict(),
        'tokens': {
            'access_token': tokens['access_token'],
            'refresh_token': tokens['refresh_token'],
            'token_type': 'Bearer',
            'expires_in': tokens['expires_in']
        }
    }), 200


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


# ========================
# 2FA Management Endpoints
# ========================

@bp.route('/2fa/setup', methods=['POST'])
@jwt_required
@admin_required
def setup_2fa():
    """
    Pokrece setup 2FA za admina.
    Generise TOTP secret i vraca QR kod.

    Returns:
        200: QR kod (base64) i manual key
    """
    admin = g.current_admin

    if admin.is_2fa_enabled:
        return jsonify({
            'error': '2FA Error',
            'message': '2FA je vec omogucen'
        }), 400

    # Generiši novi secret
    secret = admin.generate_totp_secret()
    db.session.commit()

    # Generiši QR kod
    totp_uri = admin.get_totp_uri()
    qr_code_base64 = _generate_qr_code(totp_uri)

    SecurityEventLogger.log_event(
        SecurityEventType.ADMIN_ACTION,
        details={'action': '2fa_setup_started'},
        user_id=admin.id,
        email=admin.email
    )

    return jsonify({
        'secret': secret,  # Za manual unos u app
        'qr_code': qr_code_base64,  # Base64 PNG slika
        'message': 'Skenirajte QR kod u autentifikator aplikaciji (Google Authenticator, Authy, itd.)'
    }), 200


@bp.route('/2fa/enable', methods=['POST'])
@jwt_required
@admin_required
def enable_2fa():
    """
    Omogucava 2FA nakon verifikacije koda.

    Request body:
        - code: 6-cifreni TOTP kod za verifikaciju

    Returns:
        200: 2FA omogucen + backup kodovi
    """
    admin = g.current_admin

    if admin.is_2fa_enabled:
        return jsonify({
            'error': '2FA Error',
            'message': '2FA je vec omogucen'
        }), 400

    if not admin.totp_secret:
        return jsonify({
            'error': '2FA Error',
            'message': 'Prvo pokrenite setup (/2fa/setup)'
        }), 400

    try:
        data = TwoFactorSetupRequest(**request.get_json())
    except ValidationError as e:
        return jsonify({
            'error': 'Validation Error',
            'details': e.errors()
        }), 400

    # Verifikuj kod
    if not admin.enable_2fa(data.code):
        return jsonify({
            'error': '2FA Error',
            'message': 'Neispravan kod. Proverite da li je vreme na telefonu tacno.'
        }), 400

    # Generiši backup kodove
    backup_codes = admin.generate_backup_codes()
    db.session.commit()

    SecurityEventLogger.log_event(
        SecurityEventType.ADMIN_ACTION,
        details={'action': '2fa_enabled'},
        user_id=admin.id,
        email=admin.email
    )

    AuditLog.log(
        entity_type='platform_admin',
        entity_id=admin.id,
        action=AuditAction.UPDATE,
        changes={'2fa': {'old': False, 'new': True}}
    )
    db.session.commit()

    return jsonify({
        'message': '2FA je uspesno omogucen!',
        'backup_codes': backup_codes,
        'warning': 'SACUVAJTE OVE KODOVE! Prikazuju se samo jednom.'
    }), 200


@bp.route('/2fa/disable', methods=['POST'])
@jwt_required
@admin_required
def disable_2fa():
    """
    Onemogucava 2FA. Zahteva potvrdu lozinkom.

    Request body:
        - password: Admin lozinka za potvrdu

    Returns:
        200: 2FA onemogucen
    """
    admin = g.current_admin

    if not admin.is_2fa_enabled:
        return jsonify({
            'error': '2FA Error',
            'message': '2FA nije omogucen'
        }), 400

    try:
        data = TwoFactorDisableRequest(**request.get_json())
    except ValidationError as e:
        return jsonify({
            'error': 'Validation Error',
            'details': e.errors()
        }), 400

    # Verifikuj lozinku
    if not admin.check_password(data.password):
        SecurityEventLogger.log_event(
            SecurityEventType.ADMIN_ACTION,
            details={'action': '2fa_disable_failed', 'reason': 'wrong_password'},
            user_id=admin.id,
            email=admin.email,
            level='warning'
        )
        return jsonify({
            'error': '2FA Error',
            'message': 'Pogresna lozinka'
        }), 401

    # Onemogući 2FA
    admin.disable_2fa()
    db.session.commit()

    SecurityEventLogger.log_event(
        SecurityEventType.ADMIN_ACTION,
        details={'action': '2fa_disabled'},
        user_id=admin.id,
        email=admin.email
    )

    AuditLog.log(
        entity_type='platform_admin',
        entity_id=admin.id,
        action=AuditAction.UPDATE,
        changes={'2fa': {'old': True, 'new': False}}
    )
    db.session.commit()

    return jsonify({
        'message': '2FA je onemogucen'
    }), 200


@bp.route('/2fa/backup-codes', methods=['POST'])
@jwt_required
@admin_required
def regenerate_backup_codes():
    """
    Regenerise backup kodove. Zahteva TOTP kod za potvrdu.

    Request body:
        - code: 6-cifreni TOTP kod

    Returns:
        200: Novi backup kodovi
    """
    admin = g.current_admin

    if not admin.is_2fa_enabled:
        return jsonify({
            'error': '2FA Error',
            'message': '2FA nije omogucen'
        }), 400

    try:
        data = TwoFactorSetupRequest(**request.get_json())
    except ValidationError as e:
        return jsonify({
            'error': 'Validation Error',
            'details': e.errors()
        }), 400

    # Verifikuj TOTP kod
    if not admin.verify_totp(data.code):
        return jsonify({
            'error': '2FA Error',
            'message': 'Neispravan kod'
        }), 401

    # Generiši nove backup kodove
    backup_codes = admin.generate_backup_codes()
    db.session.commit()

    SecurityEventLogger.log_event(
        SecurityEventType.ADMIN_ACTION,
        details={'action': '2fa_backup_codes_regenerated'},
        user_id=admin.id,
        email=admin.email
    )

    return jsonify({
        'backup_codes': backup_codes,
        'warning': 'SACUVAJTE OVE KODOVE! Stari kodovi vise ne vaze.'
    }), 200


@bp.route('/2fa/status', methods=['GET'])
@jwt_required
@admin_required
def get_2fa_status():
    """
    Vraca status 2FA za trenutnog admina.

    Returns:
        200: Status 2FA
    """
    admin = g.current_admin

    return jsonify({
        'is_2fa_enabled': admin.is_2fa_enabled,
        'verified_at': admin.totp_verified_at.isoformat() if admin.totp_verified_at else None,
        'has_backup_codes': admin.backup_codes is not None and admin.backup_codes != '[]'
    }), 200


def _generate_qr_code(data: str) -> str:
    """
    Generise QR kod kao base64 PNG.

    Args:
        data: Podaci za QR kod (TOTP URI)

    Returns:
        Base64 enkodiran PNG
    """
    try:
        import qrcode
        from io import BytesIO

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)

        return base64.b64encode(buffer.getvalue()).decode('utf-8')
    except ImportError:
        # Ako qrcode nije instaliran, vrati None
        return None
