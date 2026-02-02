"""
Flask ekstenzije - centralizovana inicijalizacija svih ekstenzija.
Ekstenzije se inicijalizuju ovde, a povezuju sa app-om u __init__.py.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS

# SQLAlchemy - ORM za rad sa bazom podataka
# Koristi se za sve modele (Tenant, User, ServiceTicket, itd.)
db = SQLAlchemy()

# Flask-Migrate - Alembic wrapper za migracije baze
# Komande: flask db migrate, flask db upgrade
migrate = Migrate()

# Flask-CORS - Cross-Origin Resource Sharing
# Potrebno za frontend koji se hostuje na drugom domenu
cors = CORS()


# Redis klijent - inicijalizuje se lazy loading-om
_redis_client = None


def get_redis():
    """
    Vraca Redis klijent (lazy loading).
    Koristi se za cache i kao Celery broker.
    """
    global _redis_client
    if _redis_client is None:
        import redis
        import ssl
        from flask import current_app
        redis_url = current_app.config['REDIS_URL']
        # Heroku Redis koristi self-signed certifikate
        if redis_url.startswith('rediss://'):
            _redis_client = redis.from_url(
                redis_url,
                decode_responses=True,
                ssl_cert_reqs=None  # Disable SSL verification for Heroku
            )
        else:
            _redis_client = redis.from_url(
                redis_url,
                decode_responses=True
            )
    return _redis_client
