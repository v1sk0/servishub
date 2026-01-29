"""
Konfiguracija aplikacije - podesavanja za razlicita okruzenja.
Ucitava vrednosti iz environment varijabli sa fallback na defaults.
"""

import os
from datetime import timedelta
from dotenv import load_dotenv

# Ucitaj .env fajl ako postoji
load_dotenv()


class Config:
    """
    Bazna konfiguracija - zajednicka podesavanja za sva okruzenja.
    """

    # Flask core
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

    # Session Cookie Security
    SESSION_COOKIE_HTTPONLY = True  # JavaScript ne može pristupiti cookie-u
    SESSION_COOKIE_SAMESITE = 'Lax'  # CSRF zaštita za cookies
    PERMANENT_SESSION_LIFETIME = timedelta(hours=1)  # OAuth sesija ističe nakon 1 sat

    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        'postgresql://localhost:5432/servishub'
    )
    # Heroku koristi postgres:// umesto postgresql://, moramo popraviti
    if SQLALCHEMY_DATABASE_URI.startswith('postgres://'):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace(
            'postgres://', 'postgresql://', 1
        )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,  # Proveri konekciju pre upotrebe
        'pool_recycle': 300,    # Recikliraj konekcije nakon 5 min
    }

    # JWT Authentication
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'jwt-secret-key-change-in-production')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        seconds=int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES', 28800))  # 8 sati default
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        seconds=int(os.getenv('JWT_REFRESH_TOKEN_EXPIRES', 2592000))  # 30 dana default
    )
    JWT_TOKEN_LOCATION = ['headers']
    JWT_HEADER_NAME = 'Authorization'
    JWT_HEADER_TYPE = 'Bearer'

    # Redis (za cache i Celery)
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

    # Celery
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL

    # Cloudinary (za slike LK i attachments)
    CLOUDINARY_URL = os.getenv('CLOUDINARY_URL', '')

    # Google Maps API (za Places Autocomplete)
    GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY', '')

    # Pagination defaults
    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100

    # Business settings
    TRIAL_DAYS = 90  # 3 meseca besplatno
    BASE_SUBSCRIPTION_PRICE = 3600  # RSD
    LOCATION_SUBSCRIPTION_PRICE = 1800  # RSD po dodatnoj lokaciji
    SUPPLIER_COMMISSION_RATE = 0.05  # 5% provizija

    # Warranty defaults (mogu se override-ovati per-tenant)
    DEFAULT_WARRANTY_DAYS = 45

    # CORS
    CORS_ORIGINS = os.getenv('CORS_ORIGINS', '*').split(',')

    # ========================
    # SECURITY SETTINGS
    # ========================

    # SECURITY_STRICT: Ukljucuje fail-closed ponasanje
    # - Token blacklist odbija sve ako Redis nije dostupan
    # - Stroza validacija JWT secrets
    # - Default: False u development-u, True u produkciji
    SECURITY_STRICT = os.getenv('SECURITY_STRICT', 'false').lower() == 'true'

    # TOKEN_BLACKLIST_ENABLED: Da li je token blacklist aktivan
    # - Ako je False, logout ne invalidira tokene (legacy mode)
    # - Default: True
    TOKEN_BLACKLIST_ENABLED = os.getenv('TOKEN_BLACKLIST_ENABLED', 'true').lower() == 'true'

    # Insecure defaults - lista vrednosti koje nikad ne smeju biti u produkciji
    INSECURE_SECRETS = [
        'jwt-secret-key-change-in-production',
        'dev-secret-key-change-in-production',
        'your-jwt-secret-key',
        'changeme',
        'secret',
    ]


class DevelopmentConfig(Config):
    """
    Razvojna konfiguracija - debug mode ukljucen.
    """
    DEBUG = True
    SQLALCHEMY_ECHO = True  # Loguj SQL upite


class TestingConfig(Config):
    """
    Test konfiguracija - koristi se za pytest.
    """
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(seconds=5)


class ProductionConfig(Config):
    """
    Produkciona konfiguracija - stroga bezbednosna podesavanja.

    SECURITY: Ova klasa forsira stroge security postavke.
    App nece startovati sa slabim secrets u produkciji.
    """
    DEBUG = False

    # SECURITY_STRICT je UVEK True u produkciji
    SECURITY_STRICT = True

    # U produkciji SECRET_KEY MORA biti postavljen
    @property
    def SECRET_KEY(self):
        key = os.getenv('SECRET_KEY')
        if not key:
            raise ValueError(
                "CRITICAL: SECRET_KEY environment variable must be set in production!\n"
                "Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        if len(key) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        # Proveri da nije insecure default
        for insecure in Config.INSECURE_SECRETS:
            if insecure.lower() in key.lower():
                raise ValueError(f"CRITICAL: SECRET_KEY contains insecure default value!")
        return key

    @property
    def JWT_SECRET_KEY(self):
        key = os.getenv('JWT_SECRET_KEY')
        if not key:
            raise ValueError(
                "CRITICAL: JWT_SECRET_KEY environment variable must be set in production!\n"
                "Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        if len(key) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters")
        # Proveri da nije insecure default
        for insecure in Config.INSECURE_SECRETS:
            if insecure.lower() in key.lower():
                raise ValueError(f"CRITICAL: JWT_SECRET_KEY contains insecure default value!")
        return key

    # Session Cookie Security - HTTPS only u produkciji
    SESSION_COOKIE_SECURE = True  # Cookie se šalje samo preko HTTPS

    # CORS - Nikad wildcard u produkciji
    @property
    def CORS_ORIGINS(self):
        origins = os.getenv('CORS_ORIGINS', '')
        if not origins or origins.strip() == '*':
            # Default production whitelist
            return [
                'https://servishub.rs',
                'https://www.servishub.rs',
                'https://app.servishub.rs',
            ]
        return [o.strip() for o in origins.split(',') if o.strip()]

    # Stroza engine podesavanja za produkciju
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'pool_size': 10,
        'max_overflow': 20,
    }


# Mapiranje imena okruzenja na config klase
config_by_name = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
}


def get_config():
    """
    Vraca config klasu na osnovu FLASK_ENV environment varijable.
    Default je development.
    """
    env = os.getenv('FLASK_ENV', 'development')
    return config_by_name.get(env, DevelopmentConfig)
