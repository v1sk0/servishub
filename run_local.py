"""
Lokalni razvojni server.
Pokreni sa: python run_local.py
"""

import os
from dotenv import load_dotenv

# Ucitaj .env fajl pre importa aplikacije
load_dotenv()

# Postavi development environment ako nije postavljen
os.environ.setdefault('FLASK_ENV', 'development')

from app import create_app

if __name__ == '__main__':
    app = create_app()
    app.run(
        host='127.0.0.1',
        port=5000,
        debug=True,
        use_reloader=True
    )
