"""
Scheduler Service - In-app job scheduler za automatske taskove.

Koristi APScheduler za pokretanje billing taskova bez potrebe za
Heroku Scheduler addonom.

Taskovi:
- billing_daily: Svaki dan u 06:00 UTC
- generate_invoices: 1. u mesecu u 00:00 UTC
- send_reminders: Svaki dan u 10:00 UTC
"""

import atexit
from datetime import datetime
from flask import current_app
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger


scheduler = BackgroundScheduler()


def init_scheduler(app):
    """
    Inicijalizuje scheduler sa svim billing taskovima.
    Poziva se iz create_app().
    """
    # Izbegni dupli scheduler u reload modu
    if scheduler.running:
        return

    # Koristi app context za database operacije
    def run_with_context(func):
        def wrapper():
            with app.app_context():
                try:
                    func()
                except Exception as e:
                    app.logger.error(f"Scheduler error in {func.__name__}: {e}")
        return wrapper

    # =========================================================================
    # JOB 1: Dnevne billing provere - svaki dan u 06:00 UTC
    # =========================================================================
    @run_with_context
    def billing_daily_job():
        from .billing_tasks import billing_tasks
        app.logger.info("[SCHEDULER] Starting billing_daily_job...")

        stats1 = billing_tasks.check_subscriptions()
        app.logger.info(f"[SCHEDULER] check_subscriptions: expired={stats1['trial_expired'] + stats1['active_expired']}, suspended={stats1['suspended']}")

        stats2 = billing_tasks.process_trust_expiry()
        app.logger.info(f"[SCHEDULER] process_trust_expiry: processed={stats2['processed']}")

        stats3 = billing_tasks.mark_overdue_invoices()
        app.logger.info(f"[SCHEDULER] mark_overdue: marked={stats3['marked']}")

        stats4 = billing_tasks.update_overdue_days()
        app.logger.info(f"[SCHEDULER] update_overdue_days: updated={stats4['updated']}")

        app.logger.info("[SCHEDULER] billing_daily_job completed.")

    scheduler.add_job(
        func=billing_daily_job,
        trigger=CronTrigger(hour=6, minute=0),  # 06:00 UTC = 07:00 CET
        id='billing_daily',
        name='Dnevne billing provere',
        replace_existing=True
    )

    # =========================================================================
    # JOB 2: Generisanje mesecnih faktura - 1. u mesecu u 00:00 UTC
    # =========================================================================
    @run_with_context
    def generate_invoices_job():
        from .billing_tasks import billing_tasks
        app.logger.info("[SCHEDULER] Starting generate_invoices_job...")

        stats = billing_tasks.generate_monthly_invoices()
        app.logger.info(f"[SCHEDULER] generate_invoices: generated={stats['generated']}, skipped={stats['skipped']}")

        app.logger.info("[SCHEDULER] generate_invoices_job completed.")

    scheduler.add_job(
        func=generate_invoices_job,
        trigger=CronTrigger(day=1, hour=0, minute=0),  # 1. u mesecu u 00:00
        id='generate_invoices',
        name='Generisanje mesecnih faktura',
        replace_existing=True
    )

    # =========================================================================
    # JOB 3: Email podsecanja - svaki dan u 10:00 UTC
    # =========================================================================
    @run_with_context
    def send_reminders_job():
        from ..models import Tenant
        from ..models.representative import SubscriptionPayment
        from .email_service import email_service
        from datetime import timedelta

        app.logger.info("[SCHEDULER] Starting send_reminders_job...")

        reminder_days = [3, 7, 14]
        today = datetime.utcnow().date()
        sent = 0

        for days in reminder_days:
            target_date = today - timedelta(days=days)
            overdue_invoices = SubscriptionPayment.query.filter(
                SubscriptionPayment.status == 'OVERDUE',
                SubscriptionPayment.due_date == target_date
            ).all()

            for invoice in overdue_invoices:
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

        app.logger.info(f"[SCHEDULER] send_reminders: sent={sent}")

    scheduler.add_job(
        func=send_reminders_job,
        trigger=CronTrigger(hour=10, minute=0),  # 10:00 UTC = 11:00 CET
        id='send_reminders',
        name='Slanje email podsecanja',
        replace_existing=True
    )

    # Pokreni scheduler
    scheduler.start()
    app.logger.info("[SCHEDULER] Started with 3 jobs: billing_daily, generate_invoices, send_reminders")

    # Zaustavi scheduler kada se app ugasi
    atexit.register(lambda: scheduler.shutdown(wait=False))


def get_scheduler_status():
    """Vraca status svih scheduler jobova."""
    jobs = []
    for job in scheduler.get_jobs():
        next_run = job.next_run_time
        jobs.append({
            'id': job.id,
            'name': job.name,
            'next_run': next_run.isoformat() if next_run else None,
            'trigger': str(job.trigger)
        })
    return {
        'running': scheduler.running,
        'jobs': jobs
    }


def run_job_now(job_id: str) -> bool:
    """
    Pokrece job odmah (van rasporeda).
    Koristi se za manuelno pokretanje iz admin panela.
    """
    job = scheduler.get_job(job_id)
    if job:
        job.func()
        return True
    return False
