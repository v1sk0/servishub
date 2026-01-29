"""
OAuth State Service - Redis-based storage for OAuth state.

Cuva OAuth state (CSRF, PKCE) u Redis umesto Flask session-a.
Ovo resava problem sa Heroku dynos gde session cookies mogu biti izgubljeni.

Strategija:
1. Generisi state token
2. Sacuvaj u Redis: oauth:state:{state} -> {code_verifier, nonce} sa TTL 5 min
3. Na callback, preuzmi i obrisi iz Redis

TTL je kratak (5 min) jer OAuth flow treba da se zavrsi brzo.

FAIL-MODE POLITIKA:
- Production (SECURITY_STRICT=True): FAIL-CLOSED - odbij OAuth ako Redis nije dostupan
- Development: FAIL-OPEN - dozvoli session fallback
"""

import json
import logging
import secrets
from typing import Optional, Tuple

from flask import current_app

logger = logging.getLogger(__name__)


class OAuthStateError(Exception):
    """OAuth state operation failed - FAIL-CLOSED triggered."""
    pass


class OAuthStateService:
    """
    Redis-based OAuth state storage.

    Koristi istu Redis konekciju kao TokenBlacklistService.
    Failover na Flask session ako Redis nije dostupan.
    """

    def __init__(self):
        self._redis = None
        self._redis_available = None

    @property
    def redis(self):
        """Lazy Redis connection (isti pattern kao TokenBlacklistService)."""
        if self._redis is None:
            try:
                import redis
                redis_url = current_app.config.get('REDIS_URL', 'redis://localhost:6379/0')

                # Heroku Redis koristi self-signed sertifikat
                if redis_url.startswith('rediss://'):
                    self._redis = redis.from_url(
                        redis_url,
                        decode_responses=True,
                        ssl_cert_reqs=None  # Prihvati self-signed cert
                    )
                else:
                    self._redis = redis.from_url(redis_url, decode_responses=True)

                # Test connection
                self._redis.ping()
                self._redis_available = True
                logger.info("OAuth state service: Redis connected")

            except Exception as e:
                logger.warning(f"OAuth state service: Redis unavailable, using session fallback: {e}")
                self._redis = None
                self._redis_available = False

        return self._redis

    def _check_redis(self) -> bool:
        """Proveri da li je Redis dostupan."""
        try:
            if self.redis is None:
                return False
            self.redis.ping()
            return True
        except Exception:
            self._redis_available = False
            return False

    def _is_strict_mode(self) -> bool:
        """Proveri da li je SECURITY_STRICT ukljucen (FAIL-CLOSED mode)."""
        try:
            return current_app.config.get('SECURITY_STRICT', False)
        except RuntimeError:
            return False

    def generate_and_store_state(self, code_verifier: str, nonce: str) -> str:
        """
        Generisi state token i sacuvaj ga u Redis sa PKCE podacima.

        FAIL-MODE:
        - Production (SECURITY_STRICT=True): FAIL-CLOSED - raises OAuthStateError
        - Development: FAIL-OPEN - returns state, relies on session fallback

        Args:
            code_verifier: PKCE code_verifier za kasnije verifikovanje
            nonce: OpenID Connect nonce

        Returns:
            state: Generisan state token

        Raises:
            OAuthStateError: If Redis unavailable in strict mode (FAIL-CLOSED)
        """
        state = secrets.token_urlsafe(32)

        if self._check_redis():
            try:
                key = f"oauth:state:{state}"
                data = json.dumps({
                    'code_verifier': code_verifier,
                    'nonce': nonce
                })
                # TTL: 5 minuta - OAuth flow mora da se zavrsi u tom roku
                self.redis.setex(key, 300, data)
                logger.debug(f"OAuth state stored in Redis: {state[:8]}...")
                return state
            except Exception as e:
                logger.error(f"Failed to store OAuth state in Redis: {e}")
                # Fall through to FAIL-MODE check

        # FAIL-MODE DECISION
        if self._is_strict_mode():
            # FAIL-CLOSED: Production mode - odbij OAuth ako Redis nije dostupan
            logger.error("OAuth state storage FAIL-CLOSED: Redis unavailable in strict mode")
            raise OAuthStateError(
                "OAuth state storage unavailable. Please try again later."
            )

        # FAIL-OPEN: Development mode - dozvoli session fallback
        logger.warning("OAuth state not stored in Redis, using session fallback (dev mode)")
        return state

    def get_and_delete_state(self, state: str) -> Optional[Tuple[str, str]]:
        """
        Preuzmi OAuth state podatke i obrisi ih (one-time use).

        Args:
            state: State token iz OAuth callback-a

        Returns:
            Tuple[code_verifier, nonce] ili None ako nije pronadjen
        """
        if not state:
            return None

        if self._check_redis():
            try:
                key = f"oauth:state:{state}"

                # Atomic get and delete
                pipe = self.redis.pipeline()
                pipe.get(key)
                pipe.delete(key)
                result, _ = pipe.execute()

                if result:
                    data = json.loads(result)
                    logger.debug(f"OAuth state retrieved from Redis: {state[:8]}...")
                    return (data.get('code_verifier'), data.get('nonce'))

            except Exception as e:
                logger.error(f"Failed to retrieve OAuth state from Redis: {e}")

        # Nije pronadjen u Redis-u
        return None

    def verify_state(self, received_state: str, session_state: Optional[str] = None,
                     session_code_verifier: Optional[str] = None,
                     session_nonce: Optional[str] = None) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Verifikuj OAuth state i vrati PKCE podatke.

        FAIL-MODE:
        - Production (SECURITY_STRICT=True): Session fallback DISABLED
        - Development: Session fallback ENABLED

        Pokusava da pronadje state u:
        1. Redis (primarno)
        2. Flask session (fallback - samo u dev mode)

        Args:
            received_state: State iz OAuth callback URL-a
            session_state: State iz Flask session-a (fallback)
            session_code_verifier: Code verifier iz session-a (fallback)
            session_nonce: Nonce iz session-a (fallback)

        Returns:
            Tuple[is_valid, code_verifier, nonce]
        """
        if not received_state:
            logger.warning("OAuth verification failed: no state received")
            return (False, None, None)

        # Pokusaj Redis prvo
        redis_data = self.get_and_delete_state(received_state)
        if redis_data:
            code_verifier, nonce = redis_data
            logger.info(f"OAuth state verified via Redis: {received_state[:8]}...")
            return (True, code_verifier, nonce)

        # FAIL-MODE CHECK
        if self._is_strict_mode():
            # FAIL-CLOSED: Production mode - session fallback DISABLED
            logger.warning(
                f"OAuth state verification FAIL-CLOSED: "
                f"{received_state[:8]}... not in Redis, session fallback disabled"
            )
            return (False, None, None)

        # FAIL-OPEN: Development mode - dozvoli session fallback
        if session_state and received_state == session_state:
            logger.info(f"OAuth state verified via session fallback (dev mode): {received_state[:8]}...")
            return (True, session_code_verifier, session_nonce)

        logger.warning(f"OAuth state verification failed: {received_state[:8]}... not found")
        return (False, None, None)


# Singleton instance
oauth_state = OAuthStateService()
