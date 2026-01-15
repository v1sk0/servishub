"""
Database initialization script.
Creates tables and seeds admin user.
Run before gunicorn starts.
"""
import os
import sys
import signal

# Timeout handler
def timeout_handler(signum, frame):
    print("ERROR: Database initialization timed out after 30 seconds")
    print("Continuing with app startup anyway...")
    sys.exit(0)  # Exit cleanly so gunicorn starts

# Set 30 second timeout (only on Unix)
if hasattr(signal, 'SIGALRM'):
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(30)

# Set Flask environment
os.environ.setdefault('FLASK_ENV', 'production')

print("Starting database initialization...")
print(f"DATABASE_URL set: {'DATABASE_URL' in os.environ}")

from app import create_app
from app.extensions import db
from app.models import PlatformAdmin

def init_database():
    """Initialize database tables and create admin if not exists."""
    print("Creating Flask app...")
    app = create_app()
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', 'NOT SET')
    print(f"App created, DB URI: {db_uri[:50] if db_uri else 'NONE'}...")

    with app.app_context():
        print("Creating database tables...")
        db.create_all()
        print("Tables created successfully!")

        # Check if admin exists
        print("Checking for existing admin...")
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
        # Cancel alarm if successful
        if hasattr(signal, 'SIGALRM'):
            signal.alarm(0)
        sys.exit(0)
    except Exception as e:
        print(f"Error initializing database: {e}")
        import traceback
        traceback.print_exc()
        # Still exit cleanly so gunicorn starts
        sys.exit(0)