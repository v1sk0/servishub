"""
Public User API Blueprint - B2C endpoints za krajnje korisnike.

Svi endpointi su pod /api/public/ prefiksom.
"""

from flask import Blueprint

bp = Blueprint('public_user', __name__, url_prefix='/public')


def register_routes():
    """Registruje sve sub-module."""
    from . import auth, requests, marketplace, credits