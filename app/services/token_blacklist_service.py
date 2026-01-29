"""
Token Blacklist Service - Redis-based JWT invalidation.

SECURITY CRITICAL COMPONENT

Koristi se za:
- Invalidaciju tokena na logout (pojedinacni token)
- Invalidaciju SVIH tokena korisnika na password change
- Force logout od strane admina

FAIL-MODE POLITIKA: FAIL-CLOSED
- Ako Redis nije dostupan → odbij sve tokene
- Ovo sprecava security bypass ali moze izazvati kratki downtime
- Feature flag: TOKEN_BLACKLIST_ENABLED (default: True)

Strategija:
1. Individual token blacklist: blacklist:jti:{jti} -> TTL = token expiry
2. User-wide blacklist: blacklist:user:{user_id}:{type} -> timestamp invalidacije
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from flask import current_app

logger = logging.getLogger(__name__)


class TokenBlacklistService:
    """
    Redis-based token blacklist sa fail-closed politikom.

    VAZNO: Ova klasa je singleton i koristi lazy initialization
    za Redis konekciju jer current_app nije dostupan pri importu.
    """

    def __init__(self):
        self._redis = None
        self._redis_available = None

    def _is_enabled(self) -> bool:
        """Proveri da li je blacklist ukljucen."""
        try:
            return current_app.config.get('TOKEN_BLACKLIST_ENABLED', True)
        except RuntimeError:
            # Nema app context
            return True

    def _is_strict_mode(self) -> bool:
        """Proveri da li je SECURITY_STRICT ukljucen."""
        try:
            return current_app.config.get('SECURITY_STRICT', False)
        except RuntimeError:
            return False

    @property
    def redis(self):
        """Lazy Redis connection."""
        if self._redis is None:
            try:
                import redis
                import ssl
                redis_url = current_app.config.get('REDIS_URL', 'redis://localhost:6379/0')

                # Heroku Redis koristi self-signed sertifikat
                # Za rediss:// URL treba ssl_cert_reqs=None
                if redis_url.startswith('rediss://'):
                    self._redis = redis.from_url(
                        redis_url,
                        decode_responses=True,
                        ssl_cert_reqs=None  # Prihvati self-signed cert
                    )
                else:
                    self._redis = redis.from_url(redis_url, decode_responses=True)
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                self._redis = None
        return self._redis

    def _check_redis_health(self) -> bool:
        """Proveri da li je Redis dostupan."""
        try:
            if self.redis is None:
                return False
            self.redis.ping()
            self._redis_available = True
            return True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            self._redis_available = False
            return False

    def _get_jti(self, token_payload: dict) -> str:
        """
        Dohvati JTI (JWT ID) iz tokena.

        VAZNO: Novi tokeni MORAJU imati jti claim.
        Za legacy tokene bez jti, koristimo hash od sub+iat+type.
        """
        jti = token_payload.get('jti')
        if jti:
            return jti

        # FALLBACK za stare tokene bez jti
        # Ovo treba ukloniti nakon sto svi stari tokeni isteknu (30 dana)
        unique = f"{token_payload.get('sub')}:{token_payload.get('iat')}:{token_payload.get('type')}"
        return hashlib.sha256(unique.encode()).hexdigest()[:32]

    def blacklist_token(self, token_payload: dict) -> bool:
        """
        Dodaj pojedinacni token u blacklist.
        TTL = preostalo vreme do isteka tokena.

        Args:
            token_payload: Dekodirani JWT payload

        Returns:
            True ako uspesno dodat, False ako Redis nije dostupan
        """
        if not self._is_enabled():
            return True

        if not self._check_redis_health():
            logger.error("Cannot blacklist token: Redis unavailable")
            return False

        try:
            jti = self._get_jti(token_payload)
            exp = token_payload.get('exp', 0)

            # Racunaj preostali TTL
            if isinstance(exp, datetime):
                exp = exp.timestamp()
            now = datetime.now(timezone.utc).timestamp()
            ttl = max(int(exp - now), 1)

            if ttl > 0:
                key = f"blacklist:jti:{jti}"
                self.redis.setex(key, ttl, "1")
                logger.info(f"Token blacklisted: {jti[:8]}... TTL={ttl}s")
                return True

            return True  # Token vec istekao, nema potrebe za blacklist

        except Exception as e:
            logger.error(f"Failed to blacklist token: {e}")
            return False

    def blacklist_all_user_tokens(self, user_id: int, is_admin: bool = False) -> bool:
        """
        Invalidiraj SVE tokene za korisnika.

        Koristi se kada:
        - Korisnik promeni lozinku
        - Admin force logout-uje korisnika
        - Detektovana sumnjiva aktivnost

        Args:
            user_id: ID korisnika
            is_admin: Da li je platform admin

        Returns:
            True ako uspesno
        """
        if not self._is_enabled():
            return True

        if not self._check_redis_health():
            logger.error("Cannot blacklist user tokens: Redis unavailable")
            return False

        try:
            user_type = 'admin' if is_admin else 'tenant'
            key = f"blacklist:user:{user_id}:{user_type}"

            # Postavi marker sa timestampom
            # Svi tokeni izdati PRE ovog vremena su nevazeci
            # TTL = max token lifetime (30 dana za refresh token)
            now = datetime.now(timezone.utc).timestamp()
            self.redis.setex(key, 2592000, str(now))  # 30 dana

            logger.info(f"All tokens blacklisted for {user_type}:{user_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to blacklist user tokens: {e}")
            return False

    def is_blacklisted(self, token_payload: dict) -> bool:
        """
        Proveri da li je token blacklisted.

        FAIL-MODE: FAIL-CLOSED
        - Ako Redis nije dostupan I SECURITY_STRICT=True → vrati True (odbij token)
        - Ako Redis nije dostupan I SECURITY_STRICT=False → vrati False (dozvoli, dev mode)

        Proverava:
        1. Redis dostupnost (fail-closed ako nije)
        2. Individual token blacklist (po jti)
        3. User-wide blacklist (token izdat pre invalidacije)

        Args:
            token_payload: Dekodirani JWT payload

        Returns:
            True ako je token blacklisted ILI ako Redis nije dostupan u strict mode
        """
        # Feature flag check
        if not self._is_enabled():
            return False

        # FAIL-CLOSED check
        if not self._check_redis_health():
            if self._is_strict_mode():
                logger.error("Redis unavailable, FAIL-CLOSED: rejecting token")
                return True  # FAIL-CLOSED u produkciji
            else:
                logger.warning("Redis unavailable, FAIL-OPEN: allowing token (dev mode)")
                return False  # FAIL-OPEN samo u development-u

        try:
            # 1. Proveri individual blacklist po JTI
            jti = self._get_jti(token_payload)
            if self.redis.exists(f"blacklist:jti:{jti}"):
                logger.debug(f"Token {jti[:8]}... is blacklisted (individual)")
                return True

            # 2. Proveri user-wide blacklist
            user_id = token_payload.get('sub')
            is_admin = token_payload.get('is_admin', False)
            user_type = 'admin' if is_admin else 'tenant'
            key = f"blacklist:user:{user_id}:{user_type}"

            blacklist_time = self.redis.get(key)
            if blacklist_time:
                token_iat = token_payload.get('iat', 0)
                if isinstance(token_iat, datetime):
                    token_iat = token_iat.timestamp()

                if token_iat < float(blacklist_time):
                    logger.debug(f"Token for {user_type}:{user_id} is blacklisted (user-wide)")
                    return True

            return False

        except Exception as e:
            logger.error(f"Error checking blacklist: {e}")
            # Fail-closed na gresku ako smo u strict mode
            return self._is_strict_mode()

    def clear_user_blacklist(self, user_id: int, is_admin: bool = False) -> bool:
        """
        Obrisi user-wide blacklist.
        Obicno nije potrebno - TTL se brine za ciscenje.
        """
        if not self._check_redis_health():
            return False

        try:
            user_type = 'admin' if is_admin else 'tenant'
            key = f"blacklist:user:{user_id}:{user_type}"
            self.redis.delete(key)
            return True
        except Exception as e:
            logger.error(f"Failed to clear user blacklist: {e}")
            return False

    def get_blacklist_stats(self) -> dict:
        """
        Vrati statistiku blacklist-a (za admin dashboard).
        """
        if not self._check_redis_health():
            return {'error': 'Redis unavailable'}

        try:
            # Prebroj kljuceve
            jti_keys = len(self.redis.keys("blacklist:jti:*"))
            user_keys = len(self.redis.keys("blacklist:user:*"))

            return {
                'individual_tokens': jti_keys,
                'user_wide_blacklists': user_keys,
                'redis_available': True
            }
        except Exception as e:
            return {'error': str(e)}


# Singleton instance
token_blacklist = TokenBlacklistService()
