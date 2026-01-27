"""
Public User Auth - registracija, login, verifikacija emaila.
"""

from datetime import datetime
from functools import wraps
from flask import Blueprint, request, g, current_app
import jwt as pyjwt
from app.extensions import db
from app.models.public_user import PublicUser, PublicUserStatus
from app.models.feature_flag import is_feature_enabled
from app.api.middleware.jwt_utils import TokenType

bp = Blueprint('public_auth', __name__, url_prefix='/auth')


def _check_b2c_enabled():
    if not is_feature_enabled('b2c_marketplace_enabled'):
        return {'error': 'B2C marketplace nije aktiviran'}, 403
    return None


def create_public_access_token(public_user_id):
    """Kreira access token za public usera."""
    from datetime import timedelta
    expires = datetime.utcnow() + timedelta(hours=1)
    payload = {
        'sub': public_user_id,
        'type': 'public_access',
        'exp': expires,
        'iat': datetime.utcnow(),
    }
    return pyjwt.encode(payload, current_app.config['JWT_SECRET_KEY'], algorithm='HS256')


def create_public_refresh_token(public_user_id):
    """Kreira refresh token za public usera."""
    from datetime import timedelta
    expires = datetime.utcnow() + timedelta(days=30)
    payload = {
        'sub': public_user_id,
        'type': 'public_refresh',
        'exp': expires,
        'iat': datetime.utcnow(),
    }
    return pyjwt.encode(payload, current_app.config['JWT_SECRET_KEY'], algorithm='HS256')


def public_jwt_required(f):
    """Dekorator za public user autentifikaciju."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return {'error': 'Token je obavezan'}, 401

        token = auth_header[7:]
        try:
            payload = pyjwt.decode(token, current_app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
            if payload.get('type') != 'public_access':
                return {'error': 'Pogrešan tip tokena'}, 401
            g.public_user_id = payload['sub']
        except pyjwt.ExpiredSignatureError:
            return {'error': 'Token istekao'}, 401
        except pyjwt.InvalidTokenError:
            return {'error': 'Nevažeći token'}, 401

        user = PublicUser.query.get(g.public_user_id)
        if not user or user.status in (PublicUserStatus.SUSPENDED, PublicUserStatus.BANNED):
            return {'error': 'Nalog nije aktivan'}, 403

        return f(*args, **kwargs)
    return decorated


@bp.route('/register', methods=['POST'])
def register():
    """Registracija novog public usera."""
    check = _check_b2c_enabled()
    if check:
        return check

    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    ime = data.get('ime', '').strip()
    prezime = data.get('prezime', '').strip()
    telefon = data.get('telefon')
    grad = data.get('grad')
    consent = data.get('consent', False)

    if not email or not password or not ime or not prezime:
        return {'error': 'Sva polja su obavezna (email, password, ime, prezime)'}, 400
    if len(password) < 8:
        return {'error': 'Lozinka mora imati najmanje 8 karaktera'}, 400
    if not consent:
        return {'error': 'Morate prihvatiti uslove korišćenja'}, 400

    if PublicUser.query.filter_by(email=email).first():
        return {'error': 'Email je već registrovan'}, 409

    user = PublicUser(
        email=email,
        ime=ime,
        prezime=prezime,
        telefon=telefon,
        grad=grad,
        status=PublicUserStatus.PENDING,
        consent_given_at=datetime.utcnow(),
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    # Welcome credits
    try:
        from app.services.credit_service import grant_welcome_credits
        from app.models.credits import OwnerType
        grant_welcome_credits(OwnerType.PUBLIC_USER, user.id)
        db.session.commit()
    except Exception:
        pass

    access_token = create_public_access_token(user.id)
    refresh_token = create_public_refresh_token(user.id)

    return {
        'message': 'Registracija uspešna',
        'user_id': user.id,
        'access_token': access_token,
        'refresh_token': refresh_token,
    }, 201


@bp.route('/login', methods=['POST'])
def login():
    """Login za public usera."""
    check = _check_b2c_enabled()
    if check:
        return check

    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    user = PublicUser.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return {'error': 'Pogrešan email ili lozinka'}, 401

    if user.status in (PublicUserStatus.SUSPENDED, PublicUserStatus.BANNED):
        return {'error': 'Nalog je suspendovan'}, 403

    user.last_login_at = datetime.utcnow()
    db.session.commit()

    return {
        'access_token': create_public_access_token(user.id),
        'refresh_token': create_public_refresh_token(user.id),
        'user': {
            'id': user.id,
            'email': user.email,
            'ime': user.ime,
            'prezime': user.prezime,
            'grad': user.grad,
            'status': user.status.value,
        }
    }, 200


@bp.route('/me', methods=['GET'])
@public_jwt_required
def get_profile():
    """Profil trenutnog korisnika."""
    user = PublicUser.query.get(g.public_user_id)
    return {
        'id': user.id,
        'email': user.email,
        'ime': user.ime,
        'prezime': user.prezime,
        'telefon': user.telefon,
        'grad': user.grad,
        'status': user.status.value,
        'email_verified': user.email_verified,
        'rating': float(user.rating) if user.rating else None,
        'rating_count': user.rating_count,
        'created_at': user.created_at.isoformat(),
    }, 200


@bp.route('/account', methods=['DELETE'])
@public_jwt_required
def delete_account():
    """Soft delete - anonimizacija naloga."""
    user = PublicUser.query.get(g.public_user_id)
    user.status = PublicUserStatus.BANNED
    user.email = f'deleted_{user.id}@anon'
    user.ime = 'Obrisan'
    user.prezime = 'Korisnik'
    user.telefon = None
    user.password_hash = None
    user.google_id = None
    db.session.commit()

    return {'message': 'Nalog obrisan'}, 200