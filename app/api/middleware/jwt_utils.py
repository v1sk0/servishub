"""
JWT utilities - pomocne funkcije za rad sa JWT tokenima.

Ovaj modul pruza funkcije za kreiranje i validaciju JWT tokena
za autentifikaciju korisnika (tenant users) i platform admina.

SECURITY NOTES:
- Svaki token MORA imati 'jti' (JWT ID) claim za preciznu revokaciju
- jti se koristi u token_blacklist_service za invalidaciju
- Nikad ne koristi iste payload podatke za razlicite tokene
"""

import jwt
import uuid
from datetime import datetime, timedelta
from typing import Optional, Tuple
from flask import current_app


class TokenType:
    """Tipovi tokena koje koristimo."""
    ACCESS = 'access'
    REFRESH = 'refresh'


def _generate_jti() -> str:
    """
    Generise unique JWT ID.

    JTI se koristi za:
    - Preciznu revokaciju pojedinacnog tokena
    - Sprecavanje replay napada
    - Audit trail
    """
    return str(uuid.uuid4())


def create_access_token(user_id: int, tenant_id: int, role: str) -> str:
    """
    Kreira access token za tenant korisnika.

    Access token je kratkog veka (15 min default) i koristi se
    za autorizaciju API zahteva.

    Args:
        user_id: ID korisnika (TenantUser.id)
        tenant_id: ID tenanta (Tenant.id)
        role: Rola korisnika (OWNER, ADMIN, TECHNICIAN, itd.)

    Returns:
        Enkodovan JWT token string
    """
    expires_delta = current_app.config['JWT_ACCESS_TOKEN_EXPIRES']
    expire = datetime.utcnow() + expires_delta

    payload = {
        'sub': user_id,           # Subject - ID korisnika
        'jti': _generate_jti(),   # JWT ID za revokaciju
        'tenant_id': tenant_id,   # Tenant kome pripada
        'role': role,             # Rola u preduzecu
        'type': TokenType.ACCESS, # Tip tokena
        'exp': expire,            # Expiration time
        'iat': datetime.utcnow(), # Issued at
    }

    return jwt.encode(
        payload,
        current_app.config['JWT_SECRET_KEY'],
        algorithm='HS256'
    )


def create_refresh_token(user_id: int, tenant_id: int) -> str:
    """
    Kreira refresh token za tenant korisnika.

    Refresh token je dugog veka (30 dana default) i koristi se
    samo za dobijanje novog access tokena.

    Args:
        user_id: ID korisnika
        tenant_id: ID tenanta

    Returns:
        Enkodovan JWT token string
    """
    expires_delta = current_app.config['JWT_REFRESH_TOKEN_EXPIRES']
    expire = datetime.utcnow() + expires_delta

    payload = {
        'sub': user_id,
        'jti': _generate_jti(),   # JWT ID za revokaciju
        'tenant_id': tenant_id,
        'type': TokenType.REFRESH,
        'exp': expire,
        'iat': datetime.utcnow(),
    }

    return jwt.encode(
        payload,
        current_app.config['JWT_SECRET_KEY'],
        algorithm='HS256'
    )


def create_admin_access_token(admin_id: int, role: str) -> str:
    """
    Kreira access token za platform admina.

    Platform admin tokeni su odvojeni od tenant tokena i imaju
    pristup celom ekosistemu.

    Args:
        admin_id: ID admina (PlatformAdmin.id)
        role: Admin rola (SUPER_ADMIN, ADMIN, SUPPORT)

    Returns:
        Enkodovan JWT token string
    """
    expires_delta = current_app.config['JWT_ACCESS_TOKEN_EXPIRES']
    expire = datetime.utcnow() + expires_delta

    payload = {
        'sub': admin_id,
        'jti': _generate_jti(),    # JWT ID za revokaciju
        'role': role,
        'type': TokenType.ACCESS,
        'is_admin': True,          # Oznaka da je platform admin
        'exp': expire,
        'iat': datetime.utcnow(),
    }

    return jwt.encode(
        payload,
        current_app.config['JWT_SECRET_KEY'],
        algorithm='HS256'
    )


def create_admin_refresh_token(admin_id: int) -> str:
    """
    Kreira refresh token za platform admina.

    Args:
        admin_id: ID admina

    Returns:
        Enkodovan JWT token string
    """
    expires_delta = current_app.config['JWT_REFRESH_TOKEN_EXPIRES']
    expire = datetime.utcnow() + expires_delta

    payload = {
        'sub': admin_id,
        'jti': _generate_jti(),    # JWT ID za revokaciju
        'type': TokenType.REFRESH,
        'is_admin': True,
        'exp': expire,
        'iat': datetime.utcnow(),
    }

    return jwt.encode(
        payload,
        current_app.config['JWT_SECRET_KEY'],
        algorithm='HS256'
    )


def decode_token(token: str) -> Tuple[Optional[dict], Optional[str]]:
    """
    Dekodira i validira JWT token.

    Args:
        token: JWT token string

    Returns:
        Tuple (payload, error):
        - Ako je uspesno: (payload dict, None)
        - Ako je greska: (None, error message)
    """
    try:
        payload = jwt.decode(
            token,
            current_app.config['JWT_SECRET_KEY'],
            algorithms=['HS256']
        )
        return payload, None

    except jwt.ExpiredSignatureError:
        return None, 'Token je istekao'

    except jwt.InvalidTokenError as e:
        return None, f'Neispravan token: {str(e)}'


def extract_token_from_header(auth_header: str) -> Optional[str]:
    """
    Izvlaci token iz Authorization header-a.

    Ocekuje format: "Bearer <token>"

    Args:
        auth_header: Vrednost Authorization header-a

    Returns:
        Token string ili None ako format nije ispravan
    """
    if not auth_header:
        return None

    parts = auth_header.split()

    if len(parts) != 2:
        return None

    if parts[0].lower() != 'bearer':
        return None

    return parts[1]
