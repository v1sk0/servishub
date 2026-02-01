"""
ServisHub - SaaS platforma za servise mobilnih telefona i racunara.

Ovaj modul sadrzi app factory funkciju koja kreira i konfigurise
Flask aplikaciju sa svim potrebnim ekstenzijama i blueprintima.
"""

import os
import click
from flask import Flask, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix
from .config import get_config, validate_production_config
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

    # SECURITY: Validiraj production konfiguraciju
    validate_production_config(app)

    # =========================================================================
    # ProxyFix Middleware - za ispravno citanje X-Forwarded-* headera
    # =========================================================================
    # Heroku ima 1 proxy layer (router), Cloudflare bi bio +1
    # ENV varijabla omogucava podesavanje bez code change-a
    proxy_count = int(os.environ.get('TRUSTED_PROXY_COUNT', '1'))
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=proxy_count,      # Trust X-Forwarded-For (client IP)
        x_proto=proxy_count,    # Trust X-Forwarded-Proto (https)
        x_host=proxy_count,     # Trust X-Forwarded-Host
        x_prefix=proxy_count    # Trust X-Forwarded-Prefix
    )

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

    # Security Headers - dodaje sigurnosne HTTP headere na sve responses
    from .middleware import init_security_headers
    init_security_headers(app)

    # Public Site Middleware - detektuje subdomen i custom domen za javne stranice
    from .middleware.public_site import setup_public_site_middleware
    setup_public_site_middleware(app)

    # Background Scheduler - pokrece billing taskove automatski
    # Scheduler: samo na web.1 dyno-u (ako ima vise workera) i ne tokom CLI
    import sys
    is_cli_command = 'flask' in sys.argv[0] or any(cmd in sys.argv for cmd in ['db', 'shell', 'routes'])

    # DYNO guard: na Heroku pokreni scheduler samo na web.1
    # Lokalno (bez DYNO env) uvek pokreni
    dyno = os.environ.get('DYNO', 'web.1')
    is_primary_dyno = dyno == 'web.1'

    if not is_cli_command and is_primary_dyno and app.config.get('SCHEDULER_ENABLED', True):
        from .services.scheduler_service import init_scheduler
        init_scheduler(app)


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

    # Supplier API - Za dobavljace
    from .api.supplier import bp as api_supplier_bp, register_routes as register_supplier_routes
    register_supplier_routes()
    app.register_blueprint(api_supplier_bp, url_prefix='/api/supplier')

    # Public API - B2C za krajnje kupce (bez autentifikacije)
    from .api.public import bp as api_public_bp, register_routes as register_public_routes
    register_public_routes()
    app.register_blueprint(api_public_bp, url_prefix='/api/public')

    # Frontend - HTML stranice (Jinja2 templates)
    from .frontend import bp as frontend_bp, register_routes as register_frontend_routes
    register_frontend_routes()
    app.register_blueprint(frontend_bp)

    # Tenant Public Site - Javne stranice tenanta (subdomen i custom domen)
    from .frontend.tenant_public import bp as tenant_public_bp
    app.register_blueprint(tenant_public_bp)

    # Webhooks - callback endpointi za eksterne servise (D7 DLR, Stripe, itd.)
    from .api.webhooks import bp as webhooks_bp
    app.register_blueprint(webhooks_bp)

    # Zdravstvena provera - uvek dostupna
    @app.route('/health')
    def health_check():
        """Endpoint za health check (Heroku, load balancer, itd.)"""
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

    @app.cli.command('migrate-demo-to-trial')
    def migrate_demo_to_trial_command():
        """
        Migrira sve postojece DEMO tenante u TRIAL status sa 60 dana.
        Jednokratna komanda za tranziciju na novi paket sistem.
        """
        from .models import Tenant
        from .models.tenant import TenantStatus
        from datetime import datetime, timedelta

        click.echo('Trazim DEMO tenante...')

        demo_tenants = Tenant.query.filter(
            Tenant.status == TenantStatus.DEMO
        ).all()

        if not demo_tenants:
            click.echo('Nema DEMO tenanta za migraciju.')
            return

        click.echo(f'Pronadjeno {len(demo_tenants)} DEMO tenanta.')

        migrated = 0
        for tenant in demo_tenants:
            try:
                tenant.status = TenantStatus.TRIAL
                tenant.trial_ends_at = datetime.utcnow() + timedelta(days=60)
                migrated += 1
                click.echo(f'  Migriran: {tenant.name} (ID: {tenant.id})')
            except Exception as e:
                click.echo(f'  Greska za {tenant.id}: {e}')

        db.session.commit()
        click.echo(f'\\nMigrirano {migrated} tenanta iz DEMO u TRIAL (60 dana).')
        click.echo('Gotovo!')

    # =========================================================================
    # BILLING CRON COMMANDS - Za Heroku Scheduler
    # =========================================================================

    @app.cli.command('check-subscriptions')
    def check_subscriptions_command():
        """
        Proverava istekle pretplate i azurira statuse.

        Preporuka: Pokretati svakih sat vremena.
        Heroku Scheduler: flask check-subscriptions
        """
        from .services.billing_tasks import billing_tasks

        click.echo('Proveravam pretplate...')
        stats = billing_tasks.check_subscriptions()

        click.echo(f'Trial istekao: {stats["trial_expired"]}')
        click.echo(f'Active istekao: {stats["active_expired"]}')
        click.echo(f'Suspendovano: {stats["suspended"]}')

        if stats['errors']:
            click.echo(f'Greske: {len(stats["errors"])}')
            for err in stats['errors'][:5]:
                click.echo(f'  - {err}')

        click.echo('Gotovo!')

    @app.cli.command('process-trust-expiry')
    def process_trust_expiry_command():
        """
        Procesira istekle "na rec" periode.

        Preporuka: Pokretati svakih sat vremena.
        """
        from .services.billing_tasks import billing_tasks

        click.echo('Procesiram istekle "na rec" periode...')
        stats = billing_tasks.process_trust_expiry()

        click.echo(f'Procesirano: {stats["processed"]}')
        if stats['errors']:
            click.echo(f'Greske: {len(stats["errors"])}')

        click.echo('Gotovo!')

    @app.cli.command('generate-invoices')
    def generate_invoices_command():
        """
        Generise mesecne fakture za aktivne tenante.

        Preporuka: Pokretati 1. u mesecu.
        """
        from .services.billing_tasks import billing_tasks

        click.echo('Generisem fakture...')
        stats = billing_tasks.generate_monthly_invoices()

        click.echo(f'Generisano: {stats["generated"]}')
        click.echo(f'Preskoceno (vec postoji): {stats["skipped"]}')
        if stats['errors']:
            click.echo(f'Greske: {len(stats["errors"])}')

        click.echo('Gotovo!')

    @app.cli.command('mark-overdue')
    def mark_overdue_command():
        """
        Oznacava fakture koje su prekoracile rok.

        Preporuka: Pokretati svaki dan.
        """
        from .services.billing_tasks import billing_tasks

        click.echo('Oznacavam prekoracene fakture...')
        stats = billing_tasks.mark_overdue_invoices()

        click.echo(f'Oznaceno: {stats["marked"]}')
        if stats['errors']:
            click.echo(f'Greske: {len(stats["errors"])}')

        click.echo('Gotovo!')

    @app.cli.command('update-overdue-days')
    def update_overdue_days_command():
        """
        Azurira dane kasnjenja za tenante sa dugom.

        Preporuka: Pokretati svaki dan.
        """
        from .services.billing_tasks import billing_tasks

        click.echo('Azuriram dane kasnjenja...')
        stats = billing_tasks.update_overdue_days()

        click.echo(f'Azurirano: {stats["updated"]}')
        if stats['errors']:
            click.echo(f'Greske: {len(stats["errors"])}')

        click.echo('Gotovo!')

    @app.cli.command('billing-daily')
    def billing_daily_command():
        """
        Pokrece sve dnevne billing taskove.

        Kombinuje: check-subscriptions, process-trust-expiry,
                   mark-overdue, update-overdue-days

        Preporuka: Pokretati jednom dnevno (npr. 06:00).
        Heroku Scheduler: flask billing-daily
        """
        from .services.billing_tasks import billing_tasks

        click.echo('=' * 50)
        click.echo('BILLING DAILY TASKS')
        click.echo('=' * 50)

        # 1. Check subscriptions
        click.echo('\n[1/4] Proveravam pretplate...')
        stats1 = billing_tasks.check_subscriptions()
        click.echo(f'  Expired: {stats1["trial_expired"] + stats1["active_expired"]}')
        click.echo(f'  Suspended: {stats1["suspended"]}')

        # 2. Process trust expiry
        click.echo('\n[2/4] Procesiram "na rec" periode...')
        stats2 = billing_tasks.process_trust_expiry()
        click.echo(f'  Processed: {stats2["processed"]}')

        # 3. Mark overdue
        click.echo('\n[3/4] Oznacavam prekoracene fakture...')
        stats3 = billing_tasks.mark_overdue_invoices()
        click.echo(f'  Marked: {stats3["marked"]}')

        # 4. Update overdue days
        click.echo('\n[4/4] Azuriram dane kasnjenja...')
        stats4 = billing_tasks.update_overdue_days()
        click.echo(f'  Updated: {stats4["updated"]}')

        click.echo('\n' + '=' * 50)
        click.echo('BILLING DAILY TASKS - ZAVRSENO')
        click.echo('=' * 50)

    @app.cli.command('send-billing-emails')
    @click.option('--type', 'email_type', type=click.Choice(['reminders', 'warnings']),
                  default='reminders', help='Tip emailova za slanje')
    def send_billing_emails_command(email_type):
        """
        Salje billing email notifikacije.

        Tipovi:
        - reminders: Podsecanje za neplacene fakture (kasnjenje 3, 7, 14 dana)
        - warnings: Upozorenje o suspenziji (2 dana pre)

        Preporuka: Pokretati svaki dan.
        """
        from .models import Tenant
        from .models.representative import SubscriptionPayment
        from .services.email_service import email_service
        from datetime import datetime, timedelta

        click.echo(f'Saljem {email_type} emailove...')
        sent = 0
        errors = 0

        if email_type == 'reminders':
            # Posalji podsetnik za fakture koje kasne 3, 7 i 14 dana
            reminder_days = [3, 7, 14]
            today = datetime.utcnow().date()

            for days in reminder_days:
                target_date = today - timedelta(days=days)
                overdue_invoices = SubscriptionPayment.query.filter(
                    SubscriptionPayment.status == 'OVERDUE',
                    SubscriptionPayment.due_date == target_date
                ).all()

                for invoice in overdue_invoices:
                    try:
                        tenant = Tenant.query.get(invoice.tenant_id)
                        if tenant:
                            success = email_service.send_payment_reminder_email(
                                email=tenant.email,
                                tenant_name=tenant.name,
                                invoice_number=invoice.invoice_number,
                                amount=float(invoice.total_amount),
                                days_overdue=days
                            )
                            if success:
                                sent += 1
                            else:
                                errors += 1
                    except Exception as e:
                        click.echo(f'  Greska: {e}')
                        errors += 1

        elif email_type == 'warnings':
            # Posalji upozorenje 2 dana pre suspenzije (dan 5 od grace perioda)
            from .models.tenant import TenantStatus
            today = datetime.utcnow()
            warning_cutoff = today - timedelta(days=5)

            expired_tenants = Tenant.query.filter(
                Tenant.status == TenantStatus.EXPIRED,
                Tenant.current_debt > 0
            ).all()

            for tenant in expired_tenants:
                expired_at = tenant.subscription_ends_at or tenant.trial_ends_at
                if expired_at and expired_at.date() == warning_cutoff.date():
                    try:
                        success = email_service.send_suspension_warning_email(
                            email=tenant.email,
                            tenant_name=tenant.name,
                            amount=float(tenant.current_debt),
                            days_until_suspension=2
                        )
                        if success:
                            sent += 1
                        else:
                            errors += 1
                    except Exception as e:
                        click.echo(f'  Greska: {e}')
                        errors += 1

        click.echo(f'Poslato: {sent}')
        click.echo(f'Gresaka: {errors}')
        click.echo('Gotovo!')
