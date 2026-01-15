"""Direktan upis u bazu."""
import psycopg2
from werkzeug.security import generate_password_hash

# Public URL za pristup bazi
DATABASE_URL = 'postgresql://postgres:DDPRLQsZzmXjtuMobKPCUYAEWKkXfEnV@mainline.proxy.rlwy.net:35540/railway'

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# Prvo kreiraj tabelu ako ne postoji
cur.execute("""
CREATE TABLE IF NOT EXISTS platform_admin (
    id SERIAL PRIMARY KEY,
    email VARCHAR(120) UNIQUE NOT NULL,
    password_hash VARCHAR(256) NOT NULL,
    ime VARCHAR(50) NOT NULL,
    prezime VARCHAR(50) NOT NULL,
    role VARCHAR(20) DEFAULT 'ADMIN',
    is_active BOOLEAN DEFAULT TRUE,
    last_login_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""")
conn.commit()
print('Tabela kreirana/postoji')

# Proveri da li admin postoji
cur.execute("SELECT id, email FROM platform_admin WHERE email = %s", ('admin@servishub.rs',))
row = cur.fetchone()

if row:
    print(f'Admin vec postoji: id={row[0]}, email={row[1]}')
else:
    # Kreiraj admina
    password_hash = generate_password_hash('Admin123')
    cur.execute("""
        INSERT INTO platform_admin (email, password_hash, ime, prezime, role, is_active)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """, ('admin@servishub.rs', password_hash, 'Admin', 'ServisHub', 'SUPER_ADMIN', True))
    admin_id = cur.fetchone()[0]
    conn.commit()
    print(f'Admin kreiran: id={admin_id}')

cur.close()
conn.close()
print('Gotovo!')