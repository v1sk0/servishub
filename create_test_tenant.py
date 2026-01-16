"""
Kreira test servis Tritel za testiranje.
"""
from app import create_app
from app.extensions import db
from app.models import Tenant, TenantUser

app = create_app()
with app.app_context():
    # Proveri da li vec postoji
    existing = Tenant.query.filter_by(slug='tritel').first()
    if existing:
        print(f'Tenant vec postoji: {existing.name}')
    else:
        # Kreiraj tenant
        tenant = Tenant(
            name='Tritel Servis',
            slug='tritel',
            email='info@tritel.rs',
            telefon='011123456',
            status='ACTIVE'
        )
        db.session.add(tenant)
        db.session.flush()

        # Kreiraj korisnika
        user = TenantUser(
            tenant_id=tenant.id,
            email='tritel@tritel.rs',
            username='tritel',
            ime='Test',
            prezime='Korisnik',
            role='OWNER',
            is_active=True
        )
        user.set_password('tritel123')
        db.session.add(user)
        db.session.commit()

        print(f'Tenant kreiran: {tenant.name} (ID: {tenant.id})')
        print(f'User kreiran: {user.email}')

    print('')
    print('=== LOGIN PODACI ===')
    print('URL: https://servishub.rs/login')
    print('Email: tritel@tritel.rs')
    print('Password: tritel123')
