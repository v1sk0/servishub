"""
Database initialization script.
Creates tables and seeds admin user.
Run before gunicorn starts.
"""
import os
import sys

# Set Flask environment
os.environ.setdefault('FLASK_ENV', 'production')

from app import create_app
from app.extensions import db
from app.models import PlatformAdmin

def init_database():
    """Initialize database tables and create admin if not exists."""
    app = create_app()

    with app.app_context():
        print("Creating database tables...")
        db.create_all()
        print("Tables created successfully!")

        # Check if admin exists
        admin = PlatformAdmin.query.filter_by(email='admin@servishub.rs').first()
        if admin:
            print(f"Admin already exists: {admin.email}")
        else:
            print("Creating admin user...")
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
            print(f"Admin created: {admin.email}")

        print("Database initialization complete!")

if __name__ == '__main__':
    try:
        init_database()
        sys.exit(0)
    except Exception as e:
        print(f"Error initializing database: {e}")
        sys.exit(1)