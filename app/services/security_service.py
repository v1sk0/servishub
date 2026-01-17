"""
Security Service - Rate Limiting i Security Event Logging.

Ovaj modul pruza:
1. Rate Limiting - ogranicava broj zahteva po IP adresi
2. Security Event Logging - loguje bezbednosne dogadjaje
3. Helper funkcije za sigurnosne provere
"""

import os
import logging
from datetime import datetime, timezone
from functools import wraps
from flask import request, g, jsonify, current_app
from typing import Optional, Dict, Any
import hashlib
import json

# Konfigurisi strukturirani logger za security eventove
security_logger = logging.getLogger('security')
security_logger.setLevel(logging.INFO)

# Kreiraj handler ako ne postoji
if not security_logger.handlers:
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        '%(asctime)s - SECURITY - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    security_logger.addHandler(handler)


class SecurityEventType:
    """Tipovi bezbednosnih dogadjaja."""
    # Auth events
    LOGIN_SUCCESS = 'login_success'
    LOGIN_FAILED = 'login_failed'
    LOGIN_LOCKED = 'login_locked'
    LOGOUT = 'logout'

    # OAuth events
    OAUTH_STARTED = 'oauth_started'
    OAUTH_SUCCESS = 'oauth_success'
    OAUTH_FAILED = 'oauth_failed'
    OAUTH_CSRF_INVALID = 'oauth_csrf_invalid'
    OAUTH_PKCE_INVALID = 'oauth_pkce_invalid'

    # Token events
    TOKEN_REFRESH = 'token_refresh'
    TOKEN_INVALID = 'token_invalid'
    TOKEN_EXPIRED = 'token_expired'

    # Rate limiting
    RATE_LIMIT_EXCEEDED = 'rate_limit_exceeded'

    # Suspicious activity
    SUSPICIOUS_IP = 'suspicious_ip'
    BRUTE_FORCE_DETECTED = 'brute_force_detected'

    # Admin events
    ADMIN_LOGIN_SUCCESS = 'admin_login_success'
    ADMIN_LOGIN_FAILED = 'admin_login_failed'
    ADMIN_ACTION = 'admin_action'

    # KYC events
    KYC_SUBMITTED = 'kyc_submitted'
    KYC_VERIFIED = 'kyc_verified'
    KYC_REJECTED = 'kyc_rejected'


class SecurityEventLogger:
    """
    Logger za bezbednosne dogadjaje.
    Loguje sve sigurnosno relevantne akcije za analizu i detekciju napada.
    """

    @staticmethod
    def _get_client_ip() -> str:
        """Dobija pravu IP adresu klijenta (sa proxy podrskom)."""
        # Heroku i drugi load balanceri koriste X-Forwarded-For
        if request.headers.get('X-Forwarded-For'):
            # Uzmi prvi IP (pravi klijent) iz liste
            return request.headers.get('X-Forwarded-For').split(',')[0].strip()
        return request.remote_addr or 'unknown'

    @staticmethod
    def _hash_sensitive_data(data: str) -> str:
        """Heshira osetljive podatke za logging (npr. email)."""
        if not data:
            return 'none'
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    @staticmethod
    def _get_request_context() -> Dict[str, Any]:
        """Dobija kontekst zahteva za logging."""
        return {
            'ip': SecurityEventLogger._get_client_ip(),
            'user_agent': request.headers.get('User-Agent', 'unknown')[:200],
            'method': request.method,
            'path': request.path,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

    @classmethod
    def log_event(cls, event_type: str, details: Optional[Dict[str, Any]] = None,
                  user_id: Optional[int] = None, email: Optional[str] = None,
                  level: str = 'info', user_type: Optional[str] = None,
                  save_to_db: bool = True) -> None:
        """
        Loguje bezbednosni dogadjaj.

        Args:
            event_type: Tip dogadjaja (iz SecurityEventType)
            details: Dodatni detalji o dogadjaju
            user_id: ID korisnika (ako je poznat)
            email: Email korisnika (bice hashiran)
            level: Log level (info, warning, error)
            user_type: Tip korisnika (tenant_user, admin, guest)
            save_to_db: Da li da sacuva u bazu (default: True)
        """
        context = cls._get_request_context()
        email_hash = cls._hash_sensitive_data(email) if email else None

        log_data = {
            'event': event_type,
            'context': context,
            'user_id': user_id,
            'email_hash': email_hash,
            'details': details or {}
        }

        log_message = json.dumps(log_data)

        # Loguj u konzolu
        if level == 'error':
            security_logger.error(log_message)
        elif level == 'warning':
            security_logger.warning(log_message)
        else:
            security_logger.info(log_message)

        # Sacuvaj u bazu ako je omoguceno
        if save_to_db:
            try:
                from ..models.security_event import SecurityEvent
                from ..extensions import db

                # Mapiraj level na severity
                severity_map = {
                    'info': 'info',
                    'warning': 'warning',
                    'error': 'error',
                    'critical': 'critical'
                }
                severity = severity_map.get(level, 'info')

                SecurityEvent.log(
                    event_type=event_type,
                    severity=severity,
                    user_id=user_id,
                    user_type=user_type,
                    email_hash=email_hash,
                    ip_address=context.get('ip'),
                    user_agent=context.get('user_agent'),
                    endpoint=context.get('path'),
                    method=context.get('method'),
                    details=details
                )
                db.session.commit()
            except Exception as e:
                # Ako ne uspe upis u bazu, samo loguj gresku - ne prekidaj aplikaciju
                security_logger.error(f"Failed to save security event to database: {e}")

    @classmethod
    def log_login_success(cls, user_id: int, email: str, auth_method: str = 'email') -> None:
        """Loguje uspesnu prijavu."""
        cls.log_event(
            SecurityEventType.LOGIN_SUCCESS,
            details={'auth_method': auth_method},
            user_id=user_id,
            email=email
        )

    @classmethod
    def log_login_failed(cls, email: str, reason: str = 'invalid_credentials') -> None:
        """Loguje neuspesnu prijavu."""
        cls.log_event(
            SecurityEventType.LOGIN_FAILED,
            details={'reason': reason},
            email=email,
            level='warning'
        )

    @classmethod
    def log_oauth_event(cls, event_type: str, email: Optional[str] = None,
                        error: Optional[str] = None) -> None:
        """Loguje OAuth dogadjaj."""
        details = {}
        if error:
            details['error'] = error

        level = 'warning' if event_type in [
            SecurityEventType.OAUTH_FAILED,
            SecurityEventType.OAUTH_CSRF_INVALID,
            SecurityEventType.OAUTH_PKCE_INVALID
        ] else 'info'

        cls.log_event(event_type, details=details, email=email, level=level)

    @classmethod
    def log_rate_limit(cls, endpoint: str, limit: str) -> None:
        """Loguje prekoracenje rate limita."""
        cls.log_event(
            SecurityEventType.RATE_LIMIT_EXCEEDED,
            details={'endpoint': endpoint, 'limit': limit},
            level='warning'
        )

    @classmethod
    def log_admin_login(cls, admin_id: int, email: str, success: bool) -> None:
        """Loguje admin prijavu."""
        event_type = SecurityEventType.ADMIN_LOGIN_SUCCESS if success else SecurityEventType.ADMIN_LOGIN_FAILED
        level = 'info' if success else 'warning'
        cls.log_event(event_type, user_id=admin_id, email=email, level=level)


# In-memory rate limiter (za jednostavnost, moze se zameniti sa Redis)
class InMemoryRateLimiter:
    """
    Jednostavan in-memory rate limiter.

    Za produkciju sa vise instanci, koristiti Redis-based limiter.
    Ovaj limiter radi per-process, sto je dovoljno za Heroku sa 1 dyno.
    """

    def __init__(self):
        self._requests: Dict[str, list] = {}
        self._blocked: Dict[str, float] = {}

    def _get_key(self, ip: str, endpoint: str) -> str:
        """Generise kljuc za rate limiting."""
        return f"{ip}:{endpoint}"

    def _cleanup_old_requests(self, key: str, window_seconds: int) -> None:
        """Cisti stare zahteve van window-a."""
        if key not in self._requests:
            return

        now = datetime.now(timezone.utc).timestamp()
        cutoff = now - window_seconds
        self._requests[key] = [ts for ts in self._requests[key] if ts > cutoff]

    def is_rate_limited(self, ip: str, endpoint: str, max_requests: int,
                        window_seconds: int) -> tuple[bool, int]:
        """
        Proverava da li je IP rate limitovan za dati endpoint.

        Args:
            ip: IP adresa klijenta
            endpoint: Endpoint kategorija (npr. 'login', 'oauth', 'register')
            max_requests: Maksimalan broj zahteva u window-u
            window_seconds: Velicina window-a u sekundama

        Returns:
            Tuple (is_limited, remaining_requests)
        """
        key = self._get_key(ip, endpoint)
        now = datetime.now(timezone.utc).timestamp()

        # Proveri da li je IP blokiran
        if key in self._blocked:
            if now < self._blocked[key]:
                return True, 0
            else:
                del self._blocked[key]

        # Ocisti stare zahteve
        self._cleanup_old_requests(key, window_seconds)

        # Inicijalizuj ako ne postoji
        if key not in self._requests:
            self._requests[key] = []

        # Proveri broj zahteva
        request_count = len(self._requests[key])
        remaining = max(0, max_requests - request_count)

        if request_count >= max_requests:
            return True, 0

        # Dodaj trenutni zahtev
        self._requests[key].append(now)

        return False, remaining - 1

    def block_ip(self, ip: str, endpoint: str, block_seconds: int) -> None:
        """Blokira IP za odredjeno vreme."""
        key = self._get_key(ip, endpoint)
        now = datetime.now(timezone.utc).timestamp()
        self._blocked[key] = now + block_seconds


# Globalna instanca rate limitera
_rate_limiter = InMemoryRateLimiter()


def get_rate_limiter() -> InMemoryRateLimiter:
    """Vraca globalnu instancu rate limitera."""
    return _rate_limiter


def rate_limit(max_requests: int = 10, window_seconds: int = 60,
               endpoint_name: Optional[str] = None, block_seconds: int = 300):
    """
    Dekorator za rate limiting endpointa.

    Args:
        max_requests: Maksimalan broj zahteva u window-u
        window_seconds: Velicina window-a u sekundama
        endpoint_name: Opciono ime endpointa (default: funkcija ime)
        block_seconds: Koliko sekundi blokirati IP posle prekoracenja

    Usage:
        @rate_limit(max_requests=5, window_seconds=60, endpoint_name='login')
        def login():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            ip = SecurityEventLogger._get_client_ip()
            endpoint = endpoint_name or f.__name__

            limiter = get_rate_limiter()
            is_limited, remaining = limiter.is_rate_limited(
                ip, endpoint, max_requests, window_seconds
            )

            if is_limited:
                # Logiraj prekoracenje
                SecurityEventLogger.log_rate_limit(endpoint, f"{max_requests}/{window_seconds}s")

                # Blokiraj IP
                limiter.block_ip(ip, endpoint, block_seconds)

                return jsonify({
                    'error': 'Previse zahteva',
                    'message': f'Prekoracen limit zahteva. Pokusajte ponovo za {block_seconds} sekundi.',
                    'retry_after': block_seconds
                }), 429

            # Dodaj headers za rate limit info
            response = f(*args, **kwargs)

            # Ako je response tuple (data, status_code), konvertuj
            if isinstance(response, tuple):
                return response

            return response

        return decorated_function
    return decorator


# Rate limit presets za razlicite endpointe
class RateLimits:
    """Predefinisani limiti za razlicite operacije."""

    # Auth - strozi limiti
    LOGIN = {'max_requests': 5, 'window_seconds': 60, 'block_seconds': 300}
    OAUTH = {'max_requests': 10, 'window_seconds': 60, 'block_seconds': 180}
    REGISTER = {'max_requests': 3, 'window_seconds': 3600, 'block_seconds': 3600}
    PASSWORD_RESET = {'max_requests': 3, 'window_seconds': 3600, 'block_seconds': 3600}

    # Email verifikacija
    SEND_EMAIL = {'max_requests': 5, 'window_seconds': 300, 'block_seconds': 600}

    # API - opusteni limiti
    API_READ = {'max_requests': 100, 'window_seconds': 60, 'block_seconds': 60}
    API_WRITE = {'max_requests': 30, 'window_seconds': 60, 'block_seconds': 120}
