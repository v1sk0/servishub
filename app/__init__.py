"""
ServisHub - SaaS platforma za servise mobilnih telefona i racunara.

Ovaj modul sadrzi app factory funkciju koja kreira i konfigurise
Flask aplikaciju sa svim potrebnim ekstenzijama i blueprintima.
"""

import click
from flask import Flask, jsonify
from .config import get_config
from .extensions import db, migrate, cors


def create_app(config_class=None):
    """
    App factory - kreira i konfigurise Flask aplikaciju.

    Args:
        config_class: Opciona config klasa. Ako nije proslednjena,
                     koristi se config na osnovu FLASK_ENV varijable.

    Returns:
        Konfigurisana Flask aplikacija.
    """
    app = Flask(__name__)

    # Ucitaj konfiguraciju
    if config_class is None:
        config_class = get_config()
    app.config.from_object(config_class)

    # Inicijalizuj ekstenzije
    _init_extensions(app)

    # Registruj blueprinte (API rute)
    _register_blueprints(app)

    # Registruj error handlere
    _register_error_handlers(app)

    # Registruj CLI komande
    _register_cli_commands(app)

    return app


def _init_extensions(app):
    """
    Inicijalizuje sve Flask ekstenzije sa app kontekstom.
    """
    # SQLAlchemy - ORM
    db.init_app(app)

    # Flask-Migrate - migracije
    migrate.init_app(app, db)

    # CORS - dozvoli cross-origin zahteve
    cors.init_app(app, origins=app.config['CORS_ORIGINS'])


def _register_blueprints(app):
    """
    Registruje sve API blueprinte.

    Struktura:
    - /api/v1/* - B2B API za servise (tenant-scoped)
    - /api/public/* - Javni B2C API (bez auth)
    - /api/admin/* - Platform Admin API
    """
    # V1 API - B2B za servise
    from .api.v1 import bp as api_v1_bp, register_routes as register_v1_routes
    register_v1_routes()
    app.register_blueprint(api_v1_bp, url_prefix='/api/v1')

    # Admin API - Platform Admin
    from .api.admin import bp as api_admin_bp, register_routes as register_admin_routes
    register_admin_routes()
    app.register_blueprint(api_admin_bp, url_prefix='/api/admin')

    # TODO: Public API - B2C za krajnje kupce
    # from .api.public import bp as api_public_bp
    # app.register_blueprint(api_public_bp, url_prefix='/api/public')

    # Zdravstvena provera - uvek dostupna
    @app.route('/health')
    def health_check():
        """Endpoint za health check (Railway, load balancer, itd.)"""
        return jsonify({
            'status': 'healthy',
            'service': 'servishub'
        })


def _register_error_handlers(app):
    """
    Registruje globalne error handlere za API.
    Svi errori se vracaju kao JSON.
    """

    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({
            'error': 'Bad Request',
            'message': str(error.description)
        }), 400

    @app.errorhandler(401)
    def unauthorized(error):
        return jsonify({
            'error': 'Unauthorized',
            'message': 'Autentifikacija je obavezna'
        }), 401

    @app.errorhandler(403)
    def forbidden(error):
        return jsonify({
            'error': 'Forbidden',
            'message': 'Nemate dozvolu za ovu akciju'
        }), 403

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            'error': 'Not Found',
            'message': 'Resurs nije pronadjen'
        }), 404

    @app.errorhandler(422)
    def unprocessable_entity(error):
        return jsonify({
            'error': 'Unprocessable Entity',
            'message': str(error.description)
        }), 422

    @app.errorhandler(500)
    def internal_error(error):
        # Loguj gresku za debugging
        app.logger.error(f'Internal Server Error: {error}')
        return jsonify({
            'error': 'Internal Server Error',
            'message': 'Doslo je do greske na serveru'
        }), 500


def _register_cli_commands(app):
    """
    Registruje custom CLI komande za Flask.
    Koriste se sa: flask <command>
    """

    @app.cli.command('create-admin')
    @click.option('--email', prompt='Admin email', help='Email za login')
    @click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True, help='Lozinka')
    @click.option('--ime', prompt='Ime', help='Ime admina')
    @click.option('--prezime', prompt='Prezime', help='Prezime admina')
    def create_admin_command(email, password, ime, prezime):
        """Kreira platform admin korisnika."""
        from .models import PlatformAdmin, AdminRole

        # Proveri da admin sa tim email-om ne postoji
        existing = PlatformAdmin.query.filter_by(email=email).first()
        if existing:
            click.echo(f'Admin sa email-om {email} vec postoji!')
            return

        # Kreiraj admina
        admin = PlatformAdmin(
            email=email,
            ime=ime,
            prezime=prezime,
            role=AdminRole.SUPER_ADMIN,  # Prvi admin je SUPER_ADMIN
            is_active=True
        )
        admin.set_password(password)

        db.session.add(admin)
        db.session.commit()

        click.echo(f'Admin {email} uspesno kreiran kao SUPER_ADMIN!')

    @app.cli.command('seed-regions')
    def seed_regions_command():
        """Popunjava tabelu regiona za Srbiju."""
        # TODO: Implementirati seed regiona
        click.echo('TODO: Implementirati seed-regions komandu')
