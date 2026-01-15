"""Script za kreiranje platform admina."""
import os
os.environ['DATABASE_URL'] = 'postgresql://postgres:DDPRLQsZzmXjtuMobKPCUYAEWKkXfEnV@mainline.proxy.rlwy.net:35540/railway'

from app import create_app
from app.models import PlatformAdmin
from app.extensions import db

app = create_app()
with app.app_context():
    # Run migrations first
    from flask_migrate import upgrade
    print('Running migrations...')
    upgrade()
    print('Migrations completed!')
    # Check if admin exists
    admin = PlatformAdmin.query.filter_by(email='admin@servishub.rs').first()
    if admin:
        print(f'Admin vec postoji: {admin.email}')
    else:
        # Create new admin
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