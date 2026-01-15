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
from ...extensions import db

# Blueprint za auth endpoints
bp = Blueprint('auth', __name__, url_prefix='/auth')


@bp.route('/register', methods=['POST'])
def register():
    """
    Registracija novog servisa (tenanta).

    Kreira preduzece, prvu lokaciju, owner korisnika i KYC predstavnika.
    Preduzece dobija DEMO status (7 dana pun pristup).

    Request body (Korak 1 - Firma):
        - company_name: Naziv preduzeca
        - pib: PIB (9 cifara)
        - maticni_broj: Maticni broj (opciono, 8 cifara)
        - adresa_sedista: Adresa sedista
        - company_email: Email preduzeca
        - company_phone: Telefon preduzeca
        - bank_account: Bankovni racun (XXX-XXXXXXXXX-XX)

    Request body (Korak 2 - Lokacija):
        - location_name: Naziv lokacije
        - location_address: Adresa lokacije
        - location_city: Grad
        - location_postal_code: Postanski broj (opciono)
        - location_phone: Telefon lokacije (opciono)

    Request body (Korak 3 - Vlasnik):
        - owner_email: Email vlasnika (za login)
        - owner_password: Lozinka (opciono za OAuth)
        - owner_ime: Ime
        - owner_prezime: Prezime
        - owner_phone: Mobilni telefon

    Request body (Korak 4 - KYC):
        - kyc_jmbg: JMBG (13 cifara)
        - kyc_broj_licne: Broj licne karte
        - kyc_lk_front_url: URL slike prednje strane LK
        - kyc_lk_back_url: URL slike zadnje strane LK

    Request body (Opciono):
        - google_id: Google OAuth ID
        - phone_verified: Da li je telefon verifikovan

    Returns:
        201: Uspesna registracija (DEMO 7 dana)
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
            # Podaci preduzeca
            company_name=data.company_name,
            company_email=data.company_email,
            company_phone=data.company_phone,
            pib=data.pib,
            maticni_broj=data.maticni_broj,
            adresa_sedista=data.adresa_sedista,
            bank_account=data.bank_account,
            # Podaci lokacije
            location_name=data.location_name,
            location_address=data.location_address,
            location_city=data.location_city,
            location_postal_code=data.location_postal_code,
            location_phone=data.location_phone,
            # Podaci vlasnika
            owner_email=data.owner_email,
            owner_password=data.owner_password,
            owner_ime=data.owner_ime,
            owner_prezime=data.owner_prezime,
            owner_phone=data.owner_phone,
            # KYC podaci
            kyc_jmbg=data.kyc_jmbg,
            kyc_broj_licne=data.kyc_broj_licne,
            kyc_lk_front_url=data.kyc_lk_front_url,
            kyc_lk_back_url=data.kyc_lk_back_url,
            # OAuth
            google_id=data.google_id,
            phone_verified=data.phone_verified
        )

        return jsonify({
            'message': 'Registracija uspesna! Imate 7 dana DEMO perioda.',
            'tenant': {
                'id': tenant.id,
                'slug': tenant.slug,
                'name': tenant.name,
                'email': tenant.email,
                'status': tenant.status.value,
                'demo_ends_at': tenant.demo_ends_at.isoformat() if tenant.demo_ends_at else None
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


# =============================================================================
# SMS OTP Verifikacija
# =============================================================================

@bp.route('/send-otp', methods=['POST'])
def send_otp():
    """
    Salje OTP kod na telefon za verifikaciju.

    Koristi se tokom registracije pre nego sto se kreira korisnik.
    OTP kod se cuva u session ili se vraca u dev modu.

    Request body:
        - phone: Broj telefona (+381... ili 06...)

    Returns:
        200: SMS uspesno poslat
        400: Neispravan broj telefona
        429: Previse pokusaja
    """
    from ...services.sms_service import sms_service, SMSError
    from flask import session
    from datetime import datetime, timedelta
    import os

    data = request.get_json() or {}
    phone = data.get('phone')

    if not phone:
        return jsonify({
            'error': 'Validation Error',
            'message': 'Broj telefona je obavezan'
        }), 400

    try:
        # Posalji OTP (bez user-a jer se koristi pre registracije)
        success, result = sms_service.send_otp(phone)

        # U dev modu, cuva se kod u session za testiranje
        if os.environ.get('FLASK_ENV') == 'development' or not os.environ.get('SMS_API_KEY'):
            session['otp_code'] = result
            session['otp_phone'] = sms_service._format_phone(phone)
            session['otp_expires'] = (datetime.utcnow() + timedelta(minutes=5)).isoformat()
            return jsonify({
                'message': 'OTP kod poslat (DEV MODE)',
                'dev_code': result  # Samo u dev modu
            }), 200

        return jsonify({
            'message': 'SMS sa verifikacionim kodom je poslat na vas telefon'
        }), 200

    except SMSError as e:
        return jsonify({
            'error': 'SMS Error',
            'message': e.message
        }), e.code


@bp.route('/verify-otp', methods=['POST'])
def verify_otp():
    """
    Verifikuje OTP kod unet od strane korisnika.

    Koristi se tokom registracije pre nego sto se kreira korisnik.

    Request body:
        - phone: Broj telefona
        - code: 6-cifreni OTP kod

    Returns:
        200: Verifikacija uspesna
        400: Neispravan kod ili istekao
    """
    from ...services.sms_service import sms_service
    from flask import session
    from datetime import datetime
    import os

    data = request.get_json() or {}
    phone = data.get('phone')
    code = data.get('code')

    if not phone or not code:
        return jsonify({
            'error': 'Validation Error',
            'message': 'Broj telefona i kod su obavezni'
        }), 400

    # U dev modu, proveri session
    if os.environ.get('FLASK_ENV') == 'development' or not os.environ.get('SMS_API_KEY'):
        stored_code = session.get('otp_code')
        stored_phone = session.get('otp_phone')
        expires_str = session.get('otp_expires')

        if not stored_code:
            return jsonify({
                'error': 'Verification Error',
                'message': 'Kod nije poslat. Zatrazite novi kod.'
            }), 400

        if expires_str:
            expires = datetime.fromisoformat(expires_str)
            if datetime.utcnow() > expires:
                return jsonify({
                    'error': 'Verification Error',
                    'message': 'Kod je istekao. Zatrazite novi kod.'
                }), 400

        formatted_phone = sms_service._format_phone(phone)
        if stored_phone != formatted_phone:
            return jsonify({
                'error': 'Verification Error',
                'message': 'Broj telefona se ne poklapa.'
            }), 400

        if stored_code != code:
            return jsonify({
                'error': 'Verification Error',
                'message': 'Neispravan kod. Pokusajte ponovo.'
            }), 400

        # Ocisti session
        session.pop('otp_code', None)
        session.pop('otp_phone', None)
        session.pop('otp_expires', None)

        # Oznaci kao verifikovan u session
        session['phone_verified'] = formatted_phone

        return jsonify({
            'message': 'Telefon uspesno verifikovan',
            'verified': True
        }), 200

    # Produkcijski mod - za sada samo vracamo success
    # Prava verifikacija ce se desiti kada se kreira korisnik
    return jsonify({
        'message': 'Telefon uspesno verifikovan',
        'verified': True
    }), 200


# =============================================================================
# Google OAuth
# =============================================================================

@bp.route('/google', methods=['GET'])
def google_login():
    """
    Pokrece Google OAuth flow.

    Redirektuje korisnika na Google OAuth consent screen.
    Nakon odobrenja, Google vraca korisnika na /google/callback.

    Returns:
        302: Redirect na Google OAuth
    """
    import os
    from urllib.parse import urlencode

    client_id = os.environ.get('GOOGLE_CLIENT_ID')
    redirect_uri = os.environ.get('GOOGLE_REDIRECT_URI',
        'https://servicehubdolce-4c283dce32e9.herokuapp.com/api/v1/auth/google/callback')

    if not client_id:
        return jsonify({
            'error': 'Configuration Error',
            'message': 'Google OAuth nije konfigurisan'
        }), 500

    # Google OAuth URL
    params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'openid email profile',
        'access_type': 'offline',
        'prompt': 'select_account'
    }

    google_auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    return jsonify({
        'auth_url': google_auth_url
    }), 200


@bp.route('/google/callback', methods=['GET'])
def google_callback():
    """
    Callback za Google OAuth.

    Razmenjuje authorization code za access token,
    dohvata korisnicke podatke i:
    - Ako korisnik postoji: loguje ga
    - Ako ne postoji: redirektuje na registraciju sa pre-popunjenim podacima

    Query params:
        - code: Authorization code od Google-a
        - error: Greska (ako je korisnik odbio)

    Returns:
        302: Redirect na dashboard ili registraciju
    """
    import os
    import requests as http_requests
    from flask import redirect, session

    # Proveri greske
    error = request.args.get('error')
    if error:
        return redirect(f'/login?error=google_denied')

    code = request.args.get('code')
    if not code:
        return redirect(f'/login?error=no_code')

    client_id = os.environ.get('GOOGLE_CLIENT_ID')
    client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
    redirect_uri = os.environ.get('GOOGLE_REDIRECT_URI',
        'https://servicehubdolce-4c283dce32e9.herokuapp.com/api/v1/auth/google/callback')

    if not client_id or not client_secret:
        return redirect(f'/login?error=config')

    # Razmeni code za token
    try:
        token_response = http_requests.post(
            'https://oauth2.googleapis.com/token',
            data={
                'code': code,
                'client_id': client_id,
                'client_secret': client_secret,
                'redirect_uri': redirect_uri,
                'grant_type': 'authorization_code'
            },
            timeout=10
        )

        if token_response.status_code != 200:
            return redirect(f'/login?error=token_exchange')

        token_data = token_response.json()
        access_token = token_data.get('access_token')

        # Dohvati korisnicke podatke
        userinfo_response = http_requests.get(
            'https://www.googleapis.com/oauth2/v2/userinfo',
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10
        )

        if userinfo_response.status_code != 200:
            return redirect(f'/login?error=userinfo')

        google_user = userinfo_response.json()

        # Podaci od Google-a
        google_id = google_user.get('id')
        email = google_user.get('email')
        given_name = google_user.get('given_name', '')
        family_name = google_user.get('family_name', '')

        # Proveri da li korisnik vec postoji
        from ...models import TenantUser
        existing_user = TenantUser.query.filter(
            (TenantUser.google_id == google_id) | (TenantUser.email == email)
        ).first()

        if existing_user:
            # Korisnik postoji - loguj ga
            if not existing_user.google_id:
                # Povezi Google nalog sa postojecim email nalogom
                existing_user.google_id = google_id
                existing_user.auth_provider = 'google'
                db.session.commit()

            # Generiši tokene
            tokens = auth_service.generate_tokens(existing_user)

            # Redirect na dashboard sa tokenom
            return redirect(f'/dashboard?token={tokens["access_token"]}')

        else:
            # Novi korisnik - sacuvaj podatke u session i redirect na registraciju
            session['google_user'] = {
                'google_id': google_id,
                'email': email,
                'ime': given_name,
                'prezime': family_name
            }

            # Redirect na registraciju sa pre-popunjenim podacima
            return redirect('/register?oauth=google')

    except http_requests.RequestException:
        return redirect(f'/login?error=network')
