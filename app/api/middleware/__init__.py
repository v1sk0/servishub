"""
Middleware - auth, tenant context, rate limiting.

Ovaj modul sadrzi dekoratore i middleware funkcije za
autentifikaciju, autorizaciju i ostale cross-cutting concerns.
"""

from .auth import (
    jwt_required,
    tenant_required,
    admin_required,
    role_required,
    location_access_required
)
from .jwt_utils import (
    create_access_token,
    create_refresh_token,
    create_admin_access_token,
    create_admin_refresh_token,
    decode_token,
    extract_token_from_header,
    TokenType
)

__all__ = [
    # Auth dekoratori
    'jwt_required',
    'tenant_required',
    'admin_required',
    'role_required',
    'location_access_required',
    # JWT funkcije
    'create_access_token',
    'create_refresh_token',
    'create_admin_access_token',
    'create_admin_refresh_token',
    'decode_token',
    'extract_token_from_header',
    'TokenType',
]
