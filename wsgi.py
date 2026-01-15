"""
ServisHub - WSGI Entry Point za Gunicorn.

Koristi se u produkciji (Heroku, itd.)
"""

import os
from dotenv import load_dotenv

# Ucitaj .env fajl ako postoji
load_dotenv()

from app import create_app

app = create_app()
