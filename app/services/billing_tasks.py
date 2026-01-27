"""
Billing Tasks - Scheduled tasks za billing sistem.

Ove funkcije se pozivaju preko Flask CLI komandi ili Heroku Scheduler-a.

Komande:
    flask check-subscriptions   # Proverava istekle pretplate
    flask send-billing-emails   # Salje email podsetnike
    flask process-trust-expiry  # Procesira istekle "na rec" periode
"""

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta  # v3.05: kalendarski mesec
from decimal import Decimal
from flask import current_app
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import Tenant, TenantUser, TenantMessage, PlatformSettings
from ..models.tenant import TenantStatus, ServiceLocation, LocationStatus
from ..models.tenant_message import MessageCategory, MessagePriority
from ..models.representative import SubscriptionPayment
from .ips_service import IPSService


def get_next_invoice_number(year: int) -> str:
    """
    Generates next invoice number using atomic UPDATE + RETURNING.

    Uses invoice_counter table with row-level locking to prevent race conditions.
    Format: SH-{year}-{seq:06d} (e.g., SH-2026-000001)

    Automatically handles year rollover by creating new rows as needed.

    Args:
        year: Year for the invoice (typically current year)

    Returns:
        Invoice number string (e.g., "SH-2026-000001")

    Raises:
        Exception if unable to generate after retries
    """
    max_retries = 3

    for attempt in range(max_retries):
        try:
            # Use a savepoint for nested transaction
            with db.session.begin_nested():
                # Try atomic UPDATE + RETURNING (locks the row)
                result = db.session.execute(text("""
                    UPDATE invoice_counter
                    SET last_seq = last_seq + 1, updated_at = CURRENT_TIMESTAMP
                    WHERE year = :year
                    RETURNING last_seq
                """), {'year': year})

                row = result.fetchone()

                if row:
                    # Row existed and was updated atomically
                    next_seq = row[0]
                    return f"SH-{year}-{next_seq:06d}"

                # Row doesn't exist for this year - INSERT with conflict handling
                # This handles year rollover (e.g., Jan 1st of new year)
                db.session.execute(text("""
                    INSERT INTO invoice_counter (year, last_seq, updated_at)
                    VALUES (:year, 1, CURRENT_TIMESTAMP)
                    ON CONFLICT (year) DO UPDATE SET
                        last_seq = invoice_counter.last_seq + 1,
                        updated_at = CURRENT_TIMESTAMP
                """), {'year': year})

                # Get the sequence we just inserted/updated
                result = db.session.execute(text("""
                    SELECT last_seq FROM invoice_counter WHERE year = :year
                """), {'year': year})
                next_seq = result.scalar()

                return f"SH-{year}-{next_seq:06d}"

        except IntegrityError:
            # Race condition on INSERT - retry
            db.session.rollback()
            if attempt == max_retries - 1:
                raise
            continue

    raise Exception("Failed to generate invoice number after max retries")


class BillingTasksService:
    """
    Servis za automatizovane billing taskove.
    """

    # =========================================================================
    # CHECK SUBSCRIPTIONS - Proverava i azurira statuse pretplata
    # =========================================================================

    @staticmethod
    def check_subscriptions():
        """
        Proverava sve pretplate i azurira statuse.

        Workflow:
        1. TRIAL -> EXPIRED ako je trial_ends_at prosao
        2. ACTIVE -> EXPIRED ako je subscription_ends_at prosao
        3. EXPIRED -> SUSPENDED ako je proslo 7 dana grace perioda

        Returns:
            dict sa statistikama
        """
        now = datetime.utcnow()
        stats = {
            'promo_activated': 0,  # v3.05: PROMO -> ACTIVE
            'trial_expired': 0,
            'active_expired': 0,
            'suspended': 0,
            'errors': []
        }

        # v3.05: 0. PROMO koji je istekao -> ACTIVE (1 kalendarski mesec)
        promo_expired = Tenant.query.filter(
            Tenant.status == TenantStatus.PROMO,
            Tenant.promo_ends_at < now
        ).all()

        for tenant in promo_expired:
            try:
                tenant.status = TenantStatus.ACTIVE
                tenant.subscription_ends_at = now + relativedelta(months=1)
                BillingTasksService._send_tenant_message(
                    tenant_id=tenant.id,
                    title='Promo period je završen - aktivirana mesečna pretplata',
                    content='Vaš besplatni 2-mesečni promo period je završen. Automatski je aktiviran mesečni paket. Faktura će biti generisana 7 dana pre isteka.',
                    category=MessageCategory.BILLING,
                    priority=MessagePriority.NORMAL
                )
                stats['promo_activated'] += 1
            except Exception as e:
                stats['errors'].append(f'PROMO Tenant {tenant.id}: {str(e)}')

        # 1. TRIAL koji je istekao -> EXPIRED
        trial_expired = Tenant.query.filter(
            Tenant.status == TenantStatus.TRIAL,
            Tenant.trial_ends_at < now
        ).all()

        for tenant in trial_expired:
            try:
                tenant.status = TenantStatus.EXPIRED
                BillingTasksService._send_tenant_message(
                    tenant_id=tenant.id,
                    title='Besplatni trial period je istekao',
                    content='Vas besplatni 60-dnevni trial period je istekao. Imate 7 dana da uplatite pretplatu pre suspenzije naloga.',
                    category=MessageCategory.BILLING,
                    priority=MessagePriority.URGENT
                )
                stats['trial_expired'] += 1
            except Exception as e:
                stats['errors'].append(f'Tenant {tenant.id}: {str(e)}')

        # 2. ACTIVE koji je istekao -> EXPIRED
        active_expired = Tenant.query.filter(
            Tenant.status == TenantStatus.ACTIVE,
            Tenant.subscription_ends_at < now
        ).all()

        for tenant in active_expired:
            try:
                tenant.status = TenantStatus.EXPIRED
                BillingTasksService._send_tenant_message(
                    tenant_id=tenant.id,
                    title='Pretplata je istekla',
                    content='Vasa pretplata je istekla. Imate 7 dana grace perioda da uplatite. Nakon toga nalog ce biti suspendovan.',
                    category=MessageCategory.BILLING,
                    priority=MessagePriority.URGENT
                )
                stats['active_expired'] += 1
            except Exception as e:
                stats['errors'].append(f'Tenant {tenant.id}: {str(e)}')

        # 3. EXPIRED duze od 7 dana -> SUSPENDED
        grace_cutoff = now - timedelta(days=7)
        to_suspend = Tenant.query.filter(
            Tenant.status == TenantStatus.EXPIRED
        ).all()

        for tenant in to_suspend:
            # Proveri kada je istekao (trial ili subscription)
            expired_at = None
            if tenant.trial_ends_at and tenant.trial_ends_at < now:
                expired_at = tenant.trial_ends_at
            elif tenant.subscription_ends_at and tenant.subscription_ends_at < now:
                expired_at = tenant.subscription_ends_at

            if expired_at and expired_at < grace_cutoff:
                try:
                    tenant.block('Istekao grace period - neplacena pretplata')
                    BillingTasksService._send_tenant_message(
                        tenant_id=tenant.id,
                        title='Nalog je suspendovan',
                        content='Vas nalog je suspendovan zbog neplacene pretplate. Uplatite dugovanje da biste nastavili sa koriscenjem.',
                        category=MessageCategory.BILLING,
                        priority=MessagePriority.URGENT
                    )
                    stats['suspended'] += 1
                except Exception as e:
                    stats['errors'].append(f'Tenant {tenant.id}: {str(e)}')

        db.session.commit()
        return stats

    # =========================================================================
    # PROCESS TRUST EXPIRY - Procesira istekle "na rec" periode
    # =========================================================================

    @staticmethod
    def process_trust_expiry():
        """
        Proverava istekle "na rec" periode i umanjuje trust score.

        Ako je proslo 48h od aktivacije a nije placeno:
        - Trust score -= 25 (dodatna kazna)
        - Ostaje SUSPENDED

        Returns:
            dict sa statistikama
        """
        now = datetime.utcnow()
        cutoff = now - timedelta(hours=48)
        stats = {
            'processed': 0,
            'errors': []
        }

        # Pronadji tenante sa isteklim trust periodom
        # NAPOMENA: has_debt je @property, ne moze se koristiti u SQL filteru!
        # Koristi current_debt > 0 umesto toga
        tenants = Tenant.query.filter(
            Tenant.status == TenantStatus.SUSPENDED,
            Tenant.trust_activated_at.isnot(None),
            Tenant.trust_activated_at < cutoff,
            Tenant.current_debt > 0  # FIX: koristi DB kolonu umesto @property
        ).all()

        for tenant in tenants:
            try:
                # Dodatno umanjenje trust score-a
                tenant.update_trust_score(-25, 'Nije platio tokom "na rec" perioda')
                tenant.trust_activated_at = None  # Resetuj

                BillingTasksService._send_tenant_message(
                    tenant_id=tenant.id,
                    title='"Na rec" period je istekao',
                    content='Vas "na rec" period je istekao bez uplate. Trust Score je umanjen za dodatnih 25 poena.',
                    category=MessageCategory.BILLING,
                    priority=MessagePriority.URGENT
                )
                stats['processed'] += 1
            except Exception as e:
                stats['errors'].append(f'Tenant {tenant.id}: {str(e)}')

        db.session.commit()
        return stats

    # =========================================================================
    # UPDATE OVERDUE DAYS - Azurira dane kasnjenja
    # =========================================================================

    @staticmethod
    def update_overdue_days():
        """
        Azurira days_overdue za sve tenante sa dugom.

        Returns:
            dict sa statistikama
        """
        now = datetime.utcnow()
        stats = {
            'updated': 0,
            'errors': []
        }

        # Pronadji tenante sa dugom
        tenants = Tenant.query.filter(
            Tenant.current_debt > 0
        ).all()

        for tenant in tenants:
            try:
                # Izracunaj dane kasnjenja od kada je nastao dug
                # Koristimo poslednju neplacenu fakturu
                last_overdue = SubscriptionPayment.query.filter(
                    SubscriptionPayment.tenant_id == tenant.id,
                    SubscriptionPayment.status == 'OVERDUE'
                ).order_by(SubscriptionPayment.due_date.asc()).first()

                if last_overdue and last_overdue.due_date:
                    days = (now.date() - last_overdue.due_date).days
                    tenant.days_overdue = max(0, days)
                    stats['updated'] += 1
            except Exception as e:
                stats['errors'].append(f'Tenant {tenant.id}: {str(e)}')

        db.session.commit()
        return stats

    # =========================================================================
    # GENERATE MONTHLY INVOICES - Generise mesecne fakture
    # =========================================================================

    @staticmethod
    def generate_monthly_invoices():
        """
        Generise fakture za sve aktivne tenante.
        Poziva se 1. u mesecu.

        Returns:
            dict sa statistikama
        """
        now = datetime.utcnow()
        stats = {
            'generated': 0,
            'skipped': 0,
            'errors': []
        }

        # Dohvati aktivne tenante
        active_tenants = Tenant.query.filter(
            Tenant.status == TenantStatus.ACTIVE
        ).all()

        # Dohvati platformske cene
        settings = PlatformSettings.get_settings()
        base_price = Decimal(str(settings.get('base_price', 2990)))
        location_price = Decimal(str(settings.get('location_price', 990)))

        for tenant in active_tenants:
            try:
                # Proveri da li vec ima fakturu za ovaj mesec
                period_start = now.replace(day=1).date()
                existing = SubscriptionPayment.query.filter(
                    SubscriptionPayment.tenant_id == tenant.id,
                    SubscriptionPayment.period_start == period_start
                ).first()

                if existing:
                    stats['skipped'] += 1
                    continue

                # Izracunaj cenu
                actual_base = tenant.custom_base_price or base_price
                actual_loc = tenant.custom_location_price or location_price

                # Broj lokacija (koristi LocationStatus umesto is_active)
                location_count = ServiceLocation.query.filter(
                    ServiceLocation.tenant_id == tenant.id,
                    ServiceLocation.status == LocationStatus.ACTIVE
                ).count()
                additional_locations = max(0, location_count - 1)

                # Stavke
                items = [
                    {
                        'description': 'ServisHub Pro - bazni paket',
                        'quantity': 1,
                        'unit_price': float(actual_base),
                        'total': float(actual_base)
                    }
                ]

                if additional_locations > 0:
                    items.append({
                        'description': f'Dodatne lokacije x{additional_locations}',
                        'quantity': additional_locations,
                        'unit_price': float(actual_loc),
                        'total': float(actual_loc * additional_locations)
                    })

                subtotal = actual_base + (actual_loc * additional_locations)
                total = subtotal  # Bez PDV za sada

                # Period
                if now.month == 12:
                    period_end = now.replace(year=now.year + 1, month=1, day=1).date() - timedelta(days=1)
                else:
                    period_end = now.replace(month=now.month + 1, day=1).date() - timedelta(days=1)

                # Generisi broj fakture (race-safe sa SELECT FOR UPDATE)
                invoice_number = get_next_invoice_number(now.year)

                # Generisi payment reference (IPS format sa godinom za v3.04)
                invoice_seq = int(invoice_number.split('-')[-1])  # SH-2026-000042 → 42
                ref_data = IPSService.generate_payment_reference(tenant.id, invoice_seq, now.year)

                # Kreiraj fakturu
                payment = SubscriptionPayment(
                    tenant_id=tenant.id,
                    invoice_number=invoice_number,
                    period_start=period_start,
                    period_end=period_end,
                    items_json=items,
                    subtotal=subtotal,
                    total_amount=total,
                    currency='RSD',
                    status='PENDING',
                    due_date=period_start + timedelta(days=15),
                    payment_reference=ref_data['full'],
                    payment_reference_model=ref_data['model']
                )
                db.session.add(payment)

                # Azuriraj dugovanje tenanta
                tenant.current_debt = (tenant.current_debt or Decimal('0')) + total

                # Posalji poruku
                BillingTasksService._send_tenant_message(
                    tenant_id=tenant.id,
                    title=f'Nova faktura: {invoice_number}',
                    content=f'Generisana je faktura za {now.strftime("%B %Y")} u iznosu od {total:,.0f} RSD. Rok placanja: {(period_start + timedelta(days=15)).strftime("%d.%m.%Y")}',
                    category=MessageCategory.BILLING,
                    priority=MessagePriority.MEDIUM
                )

                stats['generated'] += 1

            except Exception as e:
                stats['errors'].append(f'Tenant {tenant.id}: {str(e)}')

        db.session.commit()
        return stats

    # =========================================================================
    # MARK OVERDUE INVOICES - Oznacava prekoracene fakture
    # =========================================================================

    @staticmethod
    def mark_overdue_invoices():
        """
        Oznacava fakture koje su prekoracile rok placanja.

        Returns:
            dict sa statistikama
        """
        now = datetime.utcnow().date()
        stats = {
            'marked': 0,
            'errors': []
        }

        pending_invoices = SubscriptionPayment.query.filter(
            SubscriptionPayment.status == 'PENDING',
            SubscriptionPayment.due_date < now
        ).all()

        for invoice in pending_invoices:
            try:
                invoice.status = 'OVERDUE'

                # Posalji poruku
                BillingTasksService._send_tenant_message(
                    tenant_id=invoice.tenant_id,
                    title=f'Faktura {invoice.invoice_number} je prekoracena',
                    content=f'Rok placanja fakture je istekao. Molimo uplatite sto pre da izbegnete suspenziju naloga.',
                    category=MessageCategory.BILLING,
                    priority=MessagePriority.URGENT
                )

                stats['marked'] += 1
            except Exception as e:
                stats['errors'].append(f'Invoice {invoice.id}: {str(e)}')

        db.session.commit()
        return stats

    # =========================================================================
    # HELPER - Slanje poruke tenantu
    # =========================================================================

    @staticmethod
    def _send_tenant_message(tenant_id: int, title: str, content: str,
                             category: MessageCategory, priority: MessagePriority):
        """Kreira poruku za tenanta."""
        message = TenantMessage(
            tenant_id=tenant_id,
            title=title,
            content=content,
            category=category.value if hasattr(category, 'value') else category,
            priority=priority.value if hasattr(priority, 'value') else priority
        )
        db.session.add(message)


    # =========================================================================
    # ENFORCE LOCATION LIMITS - Deaktivira višak lokacija pri downgrade-u
    # =========================================================================

    @staticmethod
    def enforce_location_limits(tenant_id: int):
        """
        Poziva se pri downgrade-u plana.
        Lokacije preko limita se deaktiviraju (najnovije prvo, nikad primary).
        """
        from .billing_service import can_add_location

        check = can_add_location(tenant_id)
        if check['allowed']:
            return  # Sve OK, nema viška

        excess = check['current'] - check['limit']
        if excess <= 0:
            return

        # Deaktiviraj najnovije ne-primary lokacije
        locations = ServiceLocation.query.filter_by(
            tenant_id=tenant_id, status=LocationStatus.ACTIVE, is_primary=False
        ).order_by(ServiceLocation.created_at.desc()).limit(excess).all()

        for loc in locations:
            loc.status = LocationStatus.INACTIVE
            loc.is_active = False
            # Prebaci korisnike — middleware će postaviti primary kao fallback
            TenantUser.query.filter_by(
                current_location_id=loc.id
            ).update({'current_location_id': None})

        db.session.commit()


# Singleton instanca
billing_tasks = BillingTasksService()