"""
Package Notification Service - Slanje notifikacija o promenama paketa.

Šalje:
- Email notifikacije aktivnim tenantima
- In-app SYSTEM thread notifikacije
- Prati dostavu u PackageChangeDelivery tabeli
"""

from datetime import datetime, timezone
from flask import render_template_string
from ..extensions import db
from ..models import (
    Tenant, TenantStatus, PackageChangeHistory, PackageChangeDelivery, DeliveryStatus,
    MessageThread, Message, ThreadType, ThreadStatus
)


# Email template za package change notifikaciju
PACKAGE_CHANGE_EMAIL_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background: linear-gradient(135deg, #dc2626 0%, #991b1b 100%); color: white; padding: 30px; border-radius: 12px 12px 0 0; }
        .content { background: #f9fafb; padding: 30px; border: 1px solid #e5e7eb; border-top: none; border-radius: 0 0 12px 12px; }
        .change-table { width: 100%; border-collapse: collapse; margin: 20px 0; }
        .change-table th, .change-table td { padding: 12px; text-align: left; border-bottom: 1px solid #e5e7eb; }
        .change-table th { background: #f3f4f6; font-weight: 600; }
        .old-value { color: #6b7280; text-decoration: line-through; }
        .new-value { color: #059669; font-weight: 600; }
        .footer { margin-top: 20px; padding-top: 20px; border-top: 1px solid #e5e7eb; font-size: 12px; color: #6b7280; }
        .version-badge { display: inline-block; background: #fef3c7; color: #92400e; padding: 4px 12px; border-radius: 9999px; font-size: 12px; font-weight: 500; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 style="margin: 0; font-size: 24px;">Promena uslova paketa</h1>
            <p style="margin: 10px 0 0 0; opacity: 0.9;">ServisHub vas obaveštava o ažuriranju cenovnika</p>
        </div>
        <div class="content">
            <p>Poštovani,</p>
            <p>Obaveštavamo vas da je došlo do promene u uslovima paketa ServisHub platforme.</p>

            <p><span class="version-badge">Verzija promene: {{ change_version }}</span></p>

            {% if price_changes %}
            <h3 style="color: #1f2937;">Izmene:</h3>
            <table class="change-table">
                <tr>
                    <th>Stavka</th>
                    <th>Bilo</th>
                    <th>Biće</th>
                </tr>
                {% for key, values in price_changes.items() %}
                <tr>
                    <td>{{ labels.get(key, key) }}</td>
                    <td class="old-value">{{ values.old }} {{ currency if 'price' in key else '' }}</td>
                    <td class="new-value">{{ values.new }} {{ currency if 'price' in key else '' }}</td>
                </tr>
                {% endfor %}
            </table>
            {% endif %}

            <p><strong>Promene stupaju na snagu:</strong> {{ effective_at }}</p>

            {% if change_reason %}
            <p><strong>Razlog promene:</strong> {{ change_reason }}</p>
            {% endif %}

            <p>
                Za vašu trenutnu pretplatu, nove cene će se primenjivati od sledećeg ciklusa naplate.
                Ako imate pitanja, kontaktirajte našu podršku.
            </p>

            <div class="footer">
                <p>Referentni broj promene: {{ change_version }}</p>
                <p>Za pitanja kontaktirajte podršku sa ovim brojem.</p>
                <p>&copy; {{ year }} ServisHub. Sva prava zadržana.</p>
            </div>
        </div>
    </div>
</body>
</html>
"""

# In-app poruka template
PACKAGE_CHANGE_INAPP_TEMPLATE = """
## Promena uslova paketa

**Verzija promene:** {{ change_version }}

### Izmene:
{% for key, values in price_changes.items() %}
- **{{ labels.get(key, key) }}**: ~~{{ values.old }}~~ → **{{ values.new }}**
{% endfor %}

**Promene stupaju na snagu:** {{ effective_at }}

{% if change_reason %}
**Razlog:** {{ change_reason }}
{% endif %}

Za vašu trenutnu pretplatu, nove cene će se primenjivati od sledećeg ciklusa naplate.
"""

# Labele za prikaz
CHANGE_LABELS = {
    'base_price': 'Bazni paket',
    'location_price': 'Dodatna lokacija',
    'trial_days': 'Trial period (dana)',
    'grace_period_days': 'Grace period (dana)',
    'default_commission': 'Provizija dobavljača (%)',
    'currency': 'Valuta'
}


def get_active_tenants():
    """Vraća listu aktivnih tenanata koji trebaju biti obavešteni."""
    return Tenant.query.filter(
        Tenant.status.in_([
            TenantStatus.ACTIVE,
            TenantStatus.TRIAL,
            TenantStatus.DEMO
        ])
    ).all()


def create_package_change_notification(tenant: Tenant, change: PackageChangeHistory) -> PackageChangeDelivery:
    """
    Kreira notifikaciju o promeni paketa za jednog tenanta.

    Args:
        tenant: Tenant koji prima notifikaciju
        change: PackageChangeHistory zapis

    Returns:
        PackageChangeDelivery zapis za praćenje
    """
    # Kreiraj delivery zapis
    delivery = PackageChangeDelivery(
        change_id=change.id,
        tenant_id=tenant.id
    )
    db.session.add(delivery)

    # Pripremi podatke za template
    price_changes = change.get_price_diff()
    template_data = {
        'change_version': change.change_version,
        'price_changes': price_changes,
        'labels': CHANGE_LABELS,
        'currency': 'RSD',
        'effective_at': change.get_effective_at_local().strftime('%d.%m.%Y %H:%M'),
        'change_reason': change.change_reason,
        'year': datetime.now().year
    }

    # Kreiraj in-app SYSTEM thread
    try:
        thread = MessageThread.create_system_thread(
            tenant_id=tenant.id,
            subject=f"Promena uslova paketa - {change.change_version}",
            tags=['PACKAGE_CHANGE', 'BILLING'],
            admin_id=change.admin_id
        )
        db.session.flush()  # Da dobijemo thread.id

        # Kreiraj poruku u thread-u
        body = render_template_string(PACKAGE_CHANGE_INAPP_TEMPLATE, **template_data)
        Message.create_system_message(
            thread_id=thread.id,
            body=body,
            admin_id=change.admin_id,
            category='PACKAGE_CHANGE'
        )

        delivery.mark_inapp_created(thread.id)

    except Exception as e:
        delivery.mark_inapp_failed(str(e))

    return delivery


def send_package_change_email(tenant: Tenant, change: PackageChangeHistory,
                              delivery: PackageChangeDelivery) -> bool:
    """
    Šalje email notifikaciju o promeni paketa.

    Args:
        tenant: Tenant koji prima email
        change: PackageChangeHistory zapis
        delivery: PackageChangeDelivery za update statusa

    Returns:
        True ako je email uspešno poslat
    """
    from .email_service import send_email

    # Odredi email adresu (owner email ili company email)
    recipient = tenant.owner_email or tenant.email
    if not recipient:
        delivery.mark_email_skipped("Nema email adrese")
        return False

    # Pripremi podatke za template
    price_changes = change.get_price_diff()
    template_data = {
        'change_version': change.change_version,
        'price_changes': price_changes,
        'labels': CHANGE_LABELS,
        'currency': 'RSD',
        'effective_at': change.get_effective_at_local().strftime('%d.%m.%Y %H:%M'),
        'change_reason': change.change_reason,
        'year': datetime.now().year
    }

    # Renderuj email body
    html_body = render_template_string(PACKAGE_CHANGE_EMAIL_TEMPLATE, **template_data)

    try:
        success = send_email(
            to_email=recipient,
            subject=f"ServisHub: Promena uslova paketa - {change.change_version}",
            html_content=html_body,
            from_email="noreply@shub.rs"
        )

        if success:
            delivery.mark_email_sent(recipient)
            return True
        else:
            delivery.mark_email_failed("Email service returned false")
            return False

    except Exception as e:
        delivery.mark_email_failed(str(e))
        return False


def notify_all_tenants(change_id: int) -> dict:
    """
    Šalje notifikacije svim aktivnim tenantima o promeni paketa.

    Args:
        change_id: ID PackageChangeHistory zapisa

    Returns:
        Dict sa statistikama (tenants_notified, emails_sent, emails_failed)
    """
    change = PackageChangeHistory.query.get(change_id)
    if not change:
        return {'error': 'Change not found'}

    # Označi početak slanja
    change.start_notification()
    db.session.commit()

    tenants = get_active_tenants()
    stats = {
        'tenants_notified': 0,
        'emails_sent': 0,
        'emails_failed': 0
    }

    for tenant in tenants:
        # Kreiraj in-app notifikaciju
        delivery = create_package_change_notification(tenant, change)

        # Pošalji email
        email_sent = send_package_change_email(tenant, change, delivery)

        stats['tenants_notified'] += 1
        if email_sent:
            stats['emails_sent'] += 1
        else:
            stats['emails_failed'] += 1

        db.session.commit()

    # Označi završetak
    change.complete_notification(stats)
    db.session.commit()

    return stats


def schedule_notifications(change_id: int):
    """
    Zakazuje async slanje notifikacija.

    TODO: Implementirati sa APScheduler ili Celery kad bude potrebno.
    Za sada izvršava sinhrono.
    """
    # Za MVP - sinhrono izvršavanje
    # U produkciji bi ovo trebalo da bude async job
    return notify_all_tenants(change_id)