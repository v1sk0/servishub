"""
Auth middleware - dekoratori za autentifikaciju i autorizaciju.

Ovaj modul pruza dekoratore koji se koriste na API endpointima
za proveru JWT tokena i pristupa resursima.
"""

from functools import wraps
from flask import request, g, jsonify
from .jwt_utils import decode_token, extract_token_from_header, TokenType


def jwt_required(f):
    """
    Dekorator koji zahteva validan JWT access token.

    Proverava Authorization header, dekodira token i postavlja
    g.current_user_id i g.token_payload za dalje koriscenje.

    Koristi se na svim zastitenim endpointima.

    Usage:
        @bp.route('/protected')
        @jwt_required
        def protected_route():
            user_id = g.current_user_id
            ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # Dohvati Authorization header
        auth_header = request.headers.get('Authorization')
        token = extract_token_from_header(auth_header)

        if not token:
            return jsonify({
                'error': 'Unauthorized',
                'message': 'Token nije prosledjen'
            }), 401

        # Dekodiraj token
        payload, error = decode_token(token)

        if error:
            return jsonify({
                'error': 'Unauthorized',
                'message': error
            }), 401

        # Proveri da je access token (ne refresh)
        if payload.get('type') != TokenType.ACCESS:
            return jsonify({
                'error': 'Unauthorized',
                'message': 'Ocekivan je access token'
            }), 401

        # Sacuvaj podatke u Flask g objekt za dalje koriscenje
        g.current_user_id = payload.get('sub')
        g.token_payload = payload
        g.is_admin = payload.get('is_admin', False)

        return f(*args, **kwargs)

    return decorated


def tenant_required(f):
    """
    Dekorator koji zahteva aktivan tenant.

    MORA se koristiti POSLE @jwt_required dekoratora.
    Ucitava tenant iz baze, proverava status i postavlja
    g.current_tenant i g.current_user.

    Usage:
        @bp.route('/tenant-protected')
        @jwt_required
        @tenant_required
        def tenant_route():
            tenant = g.current_tenant
            user = g.current_user
            ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # Proveri da je jwt_required prethodno izvršen
        if not hasattr(g, 'token_payload'):
            return jsonify({
                'error': 'Internal Error',
                'message': 'tenant_required mora biti posle jwt_required'
            }), 500

        # Admin tokeni nemaju tenant_id
        if g.is_admin:
            return jsonify({
                'error': 'Forbidden',
                'message': 'Admin tokeni ne mogu pristupiti tenant resursima'
            }), 403

        payload = g.token_payload
        tenant_id = payload.get('tenant_id')

        if not tenant_id:
            return jsonify({
                'error': 'Forbidden',
                'message': 'Token ne sadrzi tenant_id'
            }), 403

        # Ucitaj tenant iz baze
        from ...models import Tenant, User
        from ...models.tenant import TenantStatus

        tenant = Tenant.query.get(tenant_id)
        if not tenant:
            return jsonify({
                'error': 'Forbidden',
                'message': 'Preduzece nije pronadjeno'
            }), 403

        # Proveri status tenanta
        if tenant.status == TenantStatus.SUSPENDED:
            return jsonify({
                'error': 'Forbidden',
                'message': 'Vas nalog je suspendovan. Kontaktirajte podrsku.'
            }), 403

        if tenant.status == TenantStatus.CANCELLED:
            return jsonify({
                'error': 'Forbidden',
                'message': 'Vas nalog je otkazan.'
            }), 403

        if tenant.status == TenantStatus.EXPIRED:
            return jsonify({
                'error': 'Payment Required',
                'message': 'Vasa pretplata je istekla. Obnovite pretplatu.'
            }), 402

        # DEMO, TRIAL i ACTIVE imaju pun pristup - ne treba dodatna provera

        # Ucitaj korisnika
        user = User.query.get(g.current_user_id)
        if not user or not user.is_active:
            return jsonify({
                'error': 'Forbidden',
                'message': 'Korisnicki nalog nije aktivan'
            }), 403

        # Proveri da korisnik pripada ovom tenantu
        if user.tenant_id != tenant_id:
            return jsonify({
                'error': 'Forbidden',
                'message': 'Korisnik ne pripada ovom preduzecu'
            }), 403

        # Postavi u g objekt
        g.current_tenant = tenant
        g.current_user = user

        return f(*args, **kwargs)

    return decorated


def admin_required(f):
    """
    Dekorator koji zahteva platform admin pristup.

    MORA se koristiti POSLE @jwt_required dekoratora.
    Ucitava admin korisnika iz baze i postavlja g.current_admin.

    Usage:
        @bp.route('/admin-only')
        @jwt_required
        @admin_required
        def admin_route():
            admin = g.current_admin
            ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # Proveri da je jwt_required prethodno izvršen
        if not hasattr(g, 'token_payload'):
            return jsonify({
                'error': 'Internal Error',
                'message': 'admin_required mora biti posle jwt_required'
            }), 500

        # Proveri da je admin token
        if not g.is_admin:
            return jsonify({
                'error': 'Forbidden',
                'message': 'Potreban je admin pristup'
            }), 403

        # Ucitaj admina iz baze
        from ...models.admin import PlatformAdmin

        admin = PlatformAdmin.query.get(g.current_user_id)
        if not admin or not admin.is_active:
            return jsonify({
                'error': 'Forbidden',
                'message': 'Admin nalog nije aktivan'
            }), 403

        g.current_admin = admin

        return f(*args, **kwargs)

    return decorated




def platform_admin_required(f):
    """
    Kombinovani dekorator za platform admin pristup.
    Kombinuje jwt_required i admin_required za jednostavniju upotrebu.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        token = extract_token_from_header(auth_header)

        if not token:
            return jsonify({'error': 'Unauthorized', 'message': 'Token nije prosledjen'}), 401

        payload, error = decode_token(token)
        if error:
            return jsonify({'error': 'Unauthorized', 'message': error}), 401

        if payload.get('type') != TokenType.ACCESS:
            return jsonify({'error': 'Unauthorized', 'message': 'Ocekivan je access token'}), 401

        if not payload.get('is_admin', False):
            return jsonify({'error': 'Forbidden', 'message': 'Potreban je admin pristup'}), 403

        from ...models.admin import PlatformAdmin
        admin = PlatformAdmin.query.get(payload.get('sub'))
        if not admin or not admin.is_active:
            return jsonify({'error': 'Forbidden', 'message': 'Admin nalog nije aktivan'}), 403

        g.current_user_id = payload.get('sub')
        g.token_payload = payload
        g.is_admin = True
        g.current_admin = admin

        return f(*args, **kwargs)
    return decorated

def role_required(*allowed_roles):
    """
    Dekorator koji zahteva odredjenu rolu korisnika.

    MORA se koristiti POSLE @tenant_required dekoratora.

    Args:
        *allowed_roles: Lista dozvoljenih rola (UserRole enum vrednosti)

    Usage:
        @bp.route('/owner-only')
        @jwt_required
        @tenant_required
        @role_required(UserRole.OWNER, UserRole.ADMIN)
        def owner_route():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            # Proveri da je tenant_required prethodno izvrsen
            if not hasattr(g, 'current_user'):
                return jsonify({
                    'error': 'Internal Error',
                    'message': 'role_required mora biti posle tenant_required'
                }), 500

            user = g.current_user

            # Konvertuj string role u enum ako treba
            from ...models import UserRole
            user_role = user.role if isinstance(user.role, UserRole) else UserRole(user.role)

            if user_role not in allowed_roles:
                return jsonify({
                    'error': 'Forbidden',
                    'message': 'Nemate dozvolu za ovu akciju'
                }), 403

            return f(*args, **kwargs)

        return decorated
    return decorator


def location_access_required(f):
    """
    Dekorator koji proverava pristup lokaciji.

    Ocekuje location_id kao URL parametar ili u JSON body-ju.
    MORA se koristiti POSLE @tenant_required dekoratora.

    Usage:
        @bp.route('/locations/<int:location_id>/tickets')
        @jwt_required
        @tenant_required
        @location_access_required
        def location_tickets(location_id):
            ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # Proveri da je tenant_required prethodno izvrsen
        if not hasattr(g, 'current_user'):
            return jsonify({
                'error': 'Internal Error',
                'message': 'location_access_required mora biti posle tenant_required'
            }), 500

        # Pokusaj da nadjemo location_id
        location_id = kwargs.get('location_id')
        if location_id is None and request.is_json:
            location_id = request.get_json().get('location_id')

        if location_id is None:
            return jsonify({
                'error': 'Bad Request',
                'message': 'location_id je obavezan'
            }), 400

        # Proveri pristup
        user = g.current_user
        if not user.has_location_access(location_id):
            return jsonify({
                'error': 'Forbidden',
                'message': 'Nemate pristup ovoj lokaciji'
            }), 403

        return f(*args, **kwargs)

    return decorated
