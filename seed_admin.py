"""Seed admin user if not exists."""
from app import create_app
from app.models import PlatformAdmin
from app.extensions import db

app = create_app()
with app.app_context():
    admin = PlatformAdmin.query.filter_by(email='admin@servishub.rs').first()
    if admin:
        print(f'Admin already exists: {admin.email}')
    else:
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
        print(f'Admin created: {admin.email}')