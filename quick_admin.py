"""Quick admin creation - no migrations."""
import os
os.environ['DATABASE_URL'] = 'postgresql://postgres:DDPRLQsZzmXjtuMobKPCUYAEWKkXfEnV@mainline.proxy.rlwy.net:35540/railway'

from app import create_app
from app.models import PlatformAdmin
from app.extensions import db

app = create_app()
with app.app_context():
    print('Checking for existing admin...')
    admin = PlatformAdmin.query.filter_by(email='admin@servishub.rs').first()
    if admin:
        print(f'Admin vec postoji: {admin.email}')
    else:
        print('Creating new admin...')
        admin = PlatformAdmin(
            email='admin@servishub.rs',
            ime='Admin',
            prezime='ServisHub',
            role='SUPER_ADMIN',
            is_active=True
        )
        admin.set_password('Admin123')
        db.session.add(admin)
        db.session.commit()
        print(f'Admin kreiran: {admin.email}')
    print('Done!')