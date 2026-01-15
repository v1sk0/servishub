"""Direct database admin creation with psycopg2."""
import psycopg2
from werkzeug.security import generate_password_hash
from datetime import datetime

DATABASE_URL = 'postgresql://postgres:DDPRLQsZzmXjtuMobKPCUYAEWKkXfEnV@mainline.proxy.rlwy.net:35540/railway'

print('Connecting to database...')
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

print('Connected! Checking tables...')

# Check if platform_admin table exists
cur.execute("""
    SELECT EXISTS (
        SELECT FROM information_schema.tables
        WHERE table_name = 'platform_admin'
    );
""")
table_exists = cur.fetchone()[0]
print(f'platform_admin table exists: {table_exists}')

if not table_exists:
    print('Table does not exist! Running migrations first...')
    # List all tables
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)
    tables = cur.fetchall()
    print(f'Existing tables: {[t[0] for t in tables]}')
else:
    # Check if admin exists
    cur.execute("SELECT email FROM platform_admin WHERE email = 'admin@servishub.rs'")
    existing = cur.fetchone()

    if existing:
        print(f'Admin already exists: {existing[0]}')
    else:
        # Create admin
        password_hash = generate_password_hash('Admin123')
        now = datetime.utcnow()

        cur.execute("""
            INSERT INTO platform_admin (email, password_hash, ime, prezime, role, is_active, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, ('admin@servishub.rs', password_hash, 'Admin', 'ServisHub', 'SUPER_ADMIN', True, now, now))

        conn.commit()
        print('Admin created: admin@servishub.rs')

cur.close()
conn.close()
print('Done!')