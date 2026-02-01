"""
SMS Rate Limiter - Redis-based rate limiting za SMS slanje.

Sprečava:
- Burst slanje SMS-ova (spam protection)
- Prekomerno slanje jednom primaocu (harassment prevention)
- Prekomerno korišćenje od strane tenanta

Limiti:
- 10 SMS/min po tenantu
- 100 SMS/sat po tenantu
- 3 SMS/dan po primaocu (per tenant)

Zahtevi:
- Redis (Heroku Redis addon)
- REDIS_URL environment varijabla
"""

import os
import hashlib
from datetime import datetime
from typing import Tuple

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class SmsRateLimiter:
    """
    Redis-based rate limiting za SMS.

    Koristi sliding window sa atomic INCR i EXPIRE operacijama.
    Svaki limit ima svoj TTL koji automatski čisti stare ključeve.
    """

    # Limiti (podešavaju se po potrebi)
    TENANT_PER_MINUTE = 10    # Max 10 SMS/min po tenantu
    TENANT_PER_HOUR = 100     # Max 100 SMS/sat po tenantu
    RECIPIENT_PER_DAY = 3     # Max 3 SMS/dan po primaocu (per tenant)

    def __init__(self):
        """Inicijalizuje Redis konekciju."""
        self.redis = None
        self._connected = False

        if not REDIS_AVAILABLE:
            print("[SMS RATE LIMITER] Redis package not installed, rate limiting disabled")
            return

        redis_url = os.environ.get('REDIS_URL')
        if not redis_url:
            print("[SMS RATE LIMITER] REDIS_URL not set, rate limiting disabled")
            return

        try:
            self.redis = redis.from_url(redis_url, decode_responses=True)
            # Test connection
            self.redis.ping()
            self._connected = True
            print("[SMS RATE LIMITER] Connected to Redis")
        except Exception as e:
            print(f"[SMS RATE LIMITER] Failed to connect to Redis: {e}")
            self.redis = None

    @property
    def is_enabled(self) -> bool:
        """Da li je rate limiting aktivan."""
        return self._connected and self.redis is not None

    def can_send(self, tenant_id: int, phone: str) -> Tuple[bool, str]:
        """
        Proverava sve rate limite pre slanja SMS-a.

        Args:
            tenant_id: ID tenanta
            phone: Broj telefona primaoca

        Returns:
            Tuple (can_send, reason)
            - can_send: True ako je dozvoljeno slanje
            - reason: "ok" ili opis limita koji je prekoračen
        """
        if not self.is_enabled:
            return True, "ok"

        now = datetime.utcnow()

        try:
            # 1. Tenant per-minute limit
            minute_key = f"sms:tenant:{tenant_id}:minute:{now.strftime('%Y%m%d%H%M')}"
            minute_count = int(self.redis.get(minute_key) or 0)
            if minute_count >= self.TENANT_PER_MINUTE:
                return False, f"rate_limit:tenant_minute:{self.TENANT_PER_MINUTE}"

            # 2. Tenant per-hour limit
            hour_key = f"sms:tenant:{tenant_id}:hour:{now.strftime('%Y%m%d%H')}"
            hour_count = int(self.redis.get(hour_key) or 0)
            if hour_count >= self.TENANT_PER_HOUR:
                return False, f"rate_limit:tenant_hour:{self.TENANT_PER_HOUR}"

            # 3. Recipient per-day limit (hashed for privacy)
            phone_hash = hashlib.sha256(phone.encode()).hexdigest()[:16]
            day_key = f"sms:recipient:{tenant_id}:{phone_hash}:day:{now.strftime('%Y%m%d')}"
            day_count = int(self.redis.get(day_key) or 0)
            if day_count >= self.RECIPIENT_PER_DAY:
                return False, f"rate_limit:recipient_day:{self.RECIPIENT_PER_DAY}"

            return True, "ok"

        except Exception as e:
            print(f"[SMS RATE LIMITER] Error checking limits: {e}")
            # U slučaju greške, dozvoli slanje (fail-open)
            return True, "ok"

    def record_send(self, tenant_id: int, phone: str):
        """
        Inkrementira brojače nakon uspešnog slanja.

        Koristi Redis pipeline za atomic operacije.

        Args:
            tenant_id: ID tenanta
            phone: Broj telefona primaoca
        """
        if not self.is_enabled:
            return

        now = datetime.utcnow()

        try:
            pipe = self.redis.pipeline()

            # Tenant minute counter (expire in 60s)
            minute_key = f"sms:tenant:{tenant_id}:minute:{now.strftime('%Y%m%d%H%M')}"
            pipe.incr(minute_key)
            pipe.expire(minute_key, 60)

            # Tenant hour counter (expire in 3600s)
            hour_key = f"sms:tenant:{tenant_id}:hour:{now.strftime('%Y%m%d%H')}"
            pipe.incr(hour_key)
            pipe.expire(hour_key, 3600)

            # Recipient day counter (expire in 86400s = 24h)
            phone_hash = hashlib.sha256(phone.encode()).hexdigest()[:16]
            day_key = f"sms:recipient:{tenant_id}:{phone_hash}:day:{now.strftime('%Y%m%d')}"
            pipe.incr(day_key)
            pipe.expire(day_key, 86400)

            pipe.execute()

        except Exception as e:
            print(f"[SMS RATE LIMITER] Error recording send: {e}")
            # Ne prekidaj ako logovanje ne uspe

    def get_tenant_usage(self, tenant_id: int) -> dict:
        """
        Vraća trenutnu upotrebu limita za tenanta.

        Koristi se za prikaz u admin panelu.

        Args:
            tenant_id: ID tenanta

        Returns:
            Dict sa trenutnom upotrebom i limitima
        """
        if not self.is_enabled:
            return {
                'enabled': False,
                'minute': {'used': 0, 'limit': self.TENANT_PER_MINUTE},
                'hour': {'used': 0, 'limit': self.TENANT_PER_HOUR}
            }

        now = datetime.utcnow()

        try:
            minute_key = f"sms:tenant:{tenant_id}:minute:{now.strftime('%Y%m%d%H%M')}"
            hour_key = f"sms:tenant:{tenant_id}:hour:{now.strftime('%Y%m%d%H')}"

            minute_count = int(self.redis.get(minute_key) or 0)
            hour_count = int(self.redis.get(hour_key) or 0)

            return {
                'enabled': True,
                'minute': {'used': minute_count, 'limit': self.TENANT_PER_MINUTE},
                'hour': {'used': hour_count, 'limit': self.TENANT_PER_HOUR}
            }

        except Exception as e:
            print(f"[SMS RATE LIMITER] Error getting usage: {e}")
            return {
                'enabled': False,
                'error': str(e)
            }

    def reset_tenant_limits(self, tenant_id: int):
        """
        Resetuje sve limite za tenanta.

        Koristi se za admin override u posebnim situacijama.

        Args:
            tenant_id: ID tenanta
        """
        if not self.is_enabled:
            return

        try:
            # Pronađi sve ključeve za tenanta
            pattern = f"sms:tenant:{tenant_id}:*"
            keys = self.redis.keys(pattern)
            if keys:
                self.redis.delete(*keys)
                print(f"[SMS RATE LIMITER] Reset {len(keys)} keys for tenant {tenant_id}")
        except Exception as e:
            print(f"[SMS RATE LIMITER] Error resetting limits: {e}")


# Singleton instance
rate_limiter = SmsRateLimiter()
