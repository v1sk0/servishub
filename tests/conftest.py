"""
Test fixtures za IDOR i location scoping testove.

Setup: 2 tenanta, svaki sa lokacijama i korisnicima.
- Tenant A: location_a1 (primary), location_a2, user_a (TECHNICIAN), admin_a (OWNER)
- Tenant B: location_b1 (primary), user_b (TECHNICIAN)
"""
import pytest
from datetime import datetime

from app import create_app
from app.config import TestingConfig
from app.extensions import db as _db
from app.models.tenant import Tenant, ServiceLocation, TenantStatus, LocationStatus
from app.models.user import TenantUser, UserLocation, UserRole
from app.api.middleware.jwt_utils import create_access_token


class IDORTestConfig(TestingConfig):
    """Override za IDOR testove — duži token expiry."""
    from datetime import timedelta
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SCHEDULER_ENABLED = False
    SERVER_NAME = 'localhost'


@pytest.fixture(scope='session')
def app():
    """Kreira Flask app za testove."""
    app = create_app(IDORTestConfig)
    yield app


@pytest.fixture(scope='function')
def db(app):
    """Kreira čistu bazu za svaki test."""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.rollback()
        _db.drop_all()


@pytest.fixture
def tenant_a(db):
    """Tenant A sa PROMO statusom."""
    t = Tenant(
        name='Servis A', slug='servis-a', email='a@test.com',
        login_secret='secret-a-12345678',
        status=TenantStatus.PROMO,
        promo_ends_at=datetime(2027, 1, 1)
    )
    db.session.add(t)
    db.session.flush()
    return t


@pytest.fixture
def tenant_b(db):
    """Tenant B sa PROMO statusom."""
    t = Tenant(
        name='Servis B', slug='servis-b', email='b@test.com',
        login_secret='secret-b-12345678',
        status=TenantStatus.PROMO,
        promo_ends_at=datetime(2027, 1, 1)
    )
    db.session.add(t)
    db.session.flush()
    return t


@pytest.fixture
def location_a1(db, tenant_a):
    """Primary lokacija tenanta A."""
    loc = ServiceLocation(
        tenant_id=tenant_a.id, name='Lokacija A1',
        is_primary=True, is_active=True, status=LocationStatus.ACTIVE
    )
    db.session.add(loc)
    db.session.flush()
    return loc


@pytest.fixture
def location_a2(db, tenant_a):
    """Sekundarna lokacija tenanta A."""
    loc = ServiceLocation(
        tenant_id=tenant_a.id, name='Lokacija A2',
        is_primary=False, is_active=True, status=LocationStatus.ACTIVE
    )
    db.session.add(loc)
    db.session.flush()
    return loc


@pytest.fixture
def location_b1(db, tenant_b):
    """Primary lokacija tenanta B."""
    loc = ServiceLocation(
        tenant_id=tenant_b.id, name='Lokacija B1',
        is_primary=True, is_active=True, status=LocationStatus.ACTIVE
    )
    db.session.add(loc)
    db.session.flush()
    return loc


@pytest.fixture
def admin_a(db, tenant_a, location_a1):
    """OWNER korisnik tenanta A."""
    u = TenantUser(
        tenant_id=tenant_a.id, username='admin_a', email='admin_a@test.com',
        ime='Admin', prezime='A', role=UserRole.OWNER, is_active=True,
        current_location_id=location_a1.id
    )
    u.set_password('test1234')
    db.session.add(u)
    db.session.flush()
    # UserLocation
    ul = UserLocation(user_id=u.id, location_id=location_a1.id, is_active=True, is_primary=True)
    db.session.add(ul)
    db.session.flush()
    return u


@pytest.fixture
def user_tech_a(db, tenant_a, location_a1):
    """TECHNICIAN korisnik tenanta A, assignovan samo na location_a1."""
    u = TenantUser(
        tenant_id=tenant_a.id, username='tech_a', email='tech_a@test.com',
        ime='Tech', prezime='A', role=UserRole.TECHNICIAN, is_active=True,
        current_location_id=location_a1.id
    )
    u.set_password('test1234')
    db.session.add(u)
    db.session.flush()
    ul = UserLocation(user_id=u.id, location_id=location_a1.id, is_active=True, is_primary=True)
    db.session.add(ul)
    db.session.flush()
    return u


@pytest.fixture
def user_b(db, tenant_b, location_b1):
    """TECHNICIAN korisnik tenanta B."""
    u = TenantUser(
        tenant_id=tenant_b.id, username='tech_b', email='tech_b@test.com',
        ime='Tech', prezime='B', role=UserRole.TECHNICIAN, is_active=True,
        current_location_id=location_b1.id
    )
    u.set_password('test1234')
    db.session.add(u)
    db.session.flush()
    ul = UserLocation(user_id=u.id, location_id=location_b1.id, is_active=True, is_primary=True)
    db.session.add(ul)
    db.session.flush()
    return u


def _make_auth_header(app, user):
    """Helper: generiše Authorization header za korisnika."""
    with app.app_context():
        token = create_access_token(user.id, user.tenant_id, user.role.value)
        return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def client_a(app, db, admin_a):
    """Test klijent sa OWNER tokenom tenanta A."""
    class AuthClient:
        def __init__(self):
            self._client = app.test_client()
            self._headers = _make_auth_header(app, admin_a)

        def get(self, url, **kw):
            kw.setdefault('headers', {}).update(self._headers)
            return self._client.get(url, **kw)

        def post(self, url, **kw):
            kw.setdefault('headers', {}).update(self._headers)
            return self._client.post(url, **kw)

        def put(self, url, **kw):
            kw.setdefault('headers', {}).update(self._headers)
            return self._client.put(url, **kw)

        def delete(self, url, **kw):
            kw.setdefault('headers', {}).update(self._headers)
            return self._client.delete(url, **kw)

        def patch(self, url, **kw):
            kw.setdefault('headers', {}).update(self._headers)
            return self._client.patch(url, **kw)

    db.session.commit()
    return AuthClient()


@pytest.fixture
def client_admin_a(client_a):
    """Alias — OWNER klijent tenanta A."""
    return client_a


@pytest.fixture
def client_tech_a(app, db, user_tech_a):
    """Test klijent sa TECHNICIAN tokenom tenanta A."""
    class AuthClient:
        def __init__(self):
            self._client = app.test_client()
            self._headers = _make_auth_header(app, user_tech_a)

        def get(self, url, **kw):
            kw.setdefault('headers', {}).update(self._headers)
            return self._client.get(url, **kw)

        def post(self, url, **kw):
            kw.setdefault('headers', {}).update(self._headers)
            return self._client.post(url, **kw)

        def put(self, url, **kw):
            kw.setdefault('headers', {}).update(self._headers)
            return self._client.put(url, **kw)

        def delete(self, url, **kw):
            kw.setdefault('headers', {}).update(self._headers)
            return self._client.delete(url, **kw)

    db.session.commit()
    return AuthClient()


@pytest.fixture
def client_b(app, db, user_b):
    """Test klijent sa TECHNICIAN tokenom tenanta B."""
    class AuthClient:
        def __init__(self):
            self._client = app.test_client()
            self._headers = _make_auth_header(app, user_b)

        def get(self, url, **kw):
            kw.setdefault('headers', {}).update(self._headers)
            return self._client.get(url, **kw)

        def post(self, url, **kw):
            kw.setdefault('headers', {}).update(self._headers)
            return self._client.post(url, **kw)

    db.session.commit()
    return AuthClient()
