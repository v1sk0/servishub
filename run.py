"""
ServisHub - Development Server Entry Point.

Pokreni sa: python run.py
"""

import os
from dotenv import load_dotenv

# Ucitaj .env fajl
load_dotenv()

from app import create_app

app = create_app()

if __name__ == '__main__':
    # Debug mode za lokalni razvoj
    debug = os.environ.get('FLASK_ENV') == 'development'
    # Za lokalni razvoj koristi port 8000, Heroku postavlja PORT automatski
    port = 8000 if debug else int(os.environ.get('PORT', 5000))

    print(f"""
    =================================================
           ServisHub Development Server
    =================================================
      URL: http://localhost:{port}
      API: http://localhost:{port}/api/v1
      Admin API: http://localhost:{port}/api/admin
    =================================================
    """)

    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug
    )
