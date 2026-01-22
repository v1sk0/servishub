"""
ServiceTicket model - servisni nalozi za popravke.

Glavni entitet za pracenje popravki uredjaja. Sadrzi podatke o
kupcu, uredjaju, statusu popravke i garanciji.

Implementira isti workflow kao Dolce Vita program:
- Prijem uredjaja sa ocenom stanja (A/B/C)
- Pracenje popravke i garancije
- Sistem obavestenja kupaca (min 15 dana izmedju)
- Write-off nakon 5 neuspesnih pokusaja kontakta
"""

import enum
import secrets
from datetime import datetime, timedelta, timezone
from ..extensions import db


class TicketStatus(enum.Enum):
    """
    Status servisnog naloga - workflow od prijema do isporuke.

    RECEIVED - Uredjaj primljen, ceka pregled
    DIAGNOSED - Pregledano, ceka odobrenje kupca
    IN_PROGRESS - U toku popravke
    WAITING_PARTS - Ceka na delove
    READY - Gotovo, ceka preuzimanje
    DELIVERED - Preuzeto od strane kupca
    CANCELLED - Otkazano
    REJECTED - Odbijeno (neisplativa popravka, nema delova, itd.)
    """
    RECEIVED = 'RECEIVED'
    DIAGNOSED = 'DIAGNOSED'
    IN_PROGRESS = 'IN_PROGRESS'
    WAITING_PARTS = 'WAITING_PARTS'
    READY = 'READY'
    DELIVERED = 'DELIVERED'
    CANCELLED = 'CANCELLED'
    REJECTED = 'REJECTED'


class TicketPriority(enum.Enum):
    """Prioritet naloga."""
    LOW = 'LOW'
    NORMAL = 'NORMAL'
    HIGH = 'HIGH'
    URGENT = 'URGENT'


class ServiceTicket(db.Model):
    """
    Servisni nalog - glavni entitet za pracenje popravki.

    Sadrzi podatke o kupcu, uredjaju, statusu i garanciji.
    Broj naloga je jedinstven unutar tenanta (preduzeca).
    """
    __tablename__ = 'service_ticket'

    # Primarni kljuc - globalno jedinstven
    id = db.Column(db.BigInteger, primary_key=True)

    # Veza sa preduzecem - obavezno za multi-tenant izolaciju
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Lokacija gde se nalog vodi
    location_id = db.Column(
        db.Integer,
        db.ForeignKey('service_location.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )

    # Broj naloga - jedinstven unutar preduzeca, ne globalno
    # Format: SRV-0001, SRV-0002, itd.
    ticket_number = db.Column(db.Integer, nullable=False)

    # Podaci o kupcu
    customer_name = db.Column(db.String(100), nullable=False)  # Ime i prezime
    customer_phone = db.Column(db.String(30))                   # Kontakt telefon
    customer_email = db.Column(db.String(100))                  # Email za obavestenja

    # B2B kupac podaci (Dolce Vita stil)
    customer_company_name = db.Column(db.String(100))  # Naziv firme (ako je B2B)
    customer_pib = db.Column(db.String(15))            # PIB firme

    # Podaci o uredjaju
    device_type = db.Column(db.String(50))     # PHONE, TABLET, LAPTOP, PC, OTHER
    brand = db.Column(db.String(50))           # Marka: Apple, Samsung, Xiaomi...
    model = db.Column(db.String(100))          # Model: iPhone 14, Galaxy S24...
    imei = db.Column(db.String(20))            # IMEI/serijski broj
    device_condition = db.Column(db.Text)      # Stanje pri prijemu (ostecenja, itd.)
    device_password = db.Column(db.String(50)) # Sifra uredjaja (enkriptovati u produkciji)

    # Kategorija servisa (Dolce Vita stil)
    service_section = db.Column(db.String(50))  # Telefoni, Tableti, Racunari, Konzole, Ostalo

    # Stanje uredjaja - ABC ocena (Dolce Vita stil)
    device_condition_grade = db.Column(db.String(1))  # A, B, C
    device_condition_notes = db.Column(db.Text)       # Detaljne napomene o stanju
    device_not_working = db.Column(db.Boolean, default=False)  # Uredjaj ne radi uopste

    # Problem areas - JSON mapiranje problema
    problem_areas = db.Column(db.Text)  # JSON: {"display": true, "battery": true, ...}

    # Opis problema i resenja
    problem_description = db.Column(db.Text, nullable=False)  # Opis kvara
    diagnosis = db.Column(db.Text)                             # Dijagnoza tehnicara
    resolution = db.Column(db.Text)                            # Opis popravke

    # Status i prioritet
    status = db.Column(
        db.Enum(TicketStatus),
        default=TicketStatus.RECEIVED,
        nullable=False,
        index=True
    )
    priority = db.Column(
        db.Enum(TicketPriority),
        default=TicketPriority.NORMAL,
        nullable=False
    )

    # Razlog odbijanja (kada je status REJECTED)
    rejection_reason = db.Column(db.Text)

    # Dodeljeni tehnicar
    assigned_technician_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant_user.id', ondelete='SET NULL'),
        nullable=True
    )

    # Cene
    estimated_price = db.Column(db.Numeric(10, 2))  # Procenjena cena
    final_price = db.Column(db.Numeric(10, 2))      # Konacna cena
    currency = db.Column(db.String(3), default='RSD')

    # Garancija
    warranty_days = db.Column(db.Integer, default=45)  # Default iz tenant settings
    closed_at = db.Column(db.DateTime)                  # Kada je nalog zatvoren (DELIVERED) - garancija krece od ovog datuma

    # Naplata
    is_paid = db.Column(db.Boolean, default=False)
    paid_at = db.Column(db.DateTime)
    payment_method = db.Column(db.String(20))  # CASH, CARD, TRANSFER

    # Ko je preuzeo uredjaj (Dolce Vita stil)
    owner_collect = db.Column(db.String(255))  # Ime osobe koja je preuzela
    owner_collect_timestamp = db.Column(db.DateTime(timezone=True))

    # Trajanje popravke u sekundama
    complete_duration = db.Column(db.Integer)  # Vreme od prijema do zatvaranja

    # Napomene za servisera
    ticket_notes = db.Column(db.Text)

    # Write-off sistem (Dolce Vita stil)
    # Nalog se otpisuje nakon 5+ neuspesnih pokusaja kontakta
    is_written_off = db.Column(db.Boolean, default=False, index=True)
    written_off_timestamp = db.Column(db.DateTime(timezone=True))
    written_off_by_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant_user.id', ondelete='SET NULL'),
        nullable=True
    )

    # SMS notifikacije flagovi
    sms_notification_completed = db.Column(db.Boolean, default=False)
    sms_notification_10_days = db.Column(db.Boolean, default=False)
    sms_notification_30_days = db.Column(db.Boolean, default=False)

    # Fakturisanje
    billing_status = db.Column(db.String(20))  # PENDING, INVOICED, PAID
    invoice_number = db.Column(db.String(20))

    # QR kod za javni pristup
    access_token = db.Column(db.String(64), unique=True, index=True)

    # Kreiranje
    created_by_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant_user.id', ondelete='SET NULL'),
        nullable=True
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )
    ready_at = db.Column(db.DateTime, nullable=True)  # Kada je nalog postao READY

    # Relacije
    tenant = db.relationship('Tenant', backref='tickets')
    location = db.relationship('ServiceLocation', backref='tickets')
    assigned_technician = db.relationship(
        'TenantUser',
        foreign_keys=[assigned_technician_id],
        backref='assigned_tickets'
    )
    created_by = db.relationship(
        'TenantUser',
        foreign_keys=[created_by_id],
        backref='created_tickets'
    )
    written_off_by = db.relationship(
        'TenantUser',
        foreign_keys=[written_off_by_id],
        backref='written_off_tickets'
    )

    # Indeksi
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'ticket_number', name='uq_tenant_ticket_number'),
        db.Index('ix_ticket_tenant_status', 'tenant_id', 'status'),
        db.Index('ix_ticket_tenant_created', 'tenant_id', 'created_at'),
        db.Index('ix_ticket_location_status', 'location_id', 'status'),
    )

    def __repr__(self):
        return f'<ServiceTicket {self.id}: {self.ticket_number_formatted}>'

    @property
    def ticket_number_formatted(self):
        """Formatiran broj naloga: SRV-0001"""
        return f'SRV-{self.ticket_number:04d}'

    @property
    def warranty_expires_at(self):
        """Datum isteka garancije (closed_at + warranty_days)."""
        if self.closed_at and self.warranty_days:
            return self.closed_at + timedelta(days=self.warranty_days)
        return None

    @property
    def warranty_remaining_days(self):
        """Preostali dani garancije."""
        if not self.warranty_expires_at:
            return None
        remaining = (self.warranty_expires_at - datetime.utcnow()).days
        return max(0, remaining)

    @property
    def is_under_warranty(self):
        """Da li je nalog jos uvek pod garancijom."""
        remaining = self.warranty_remaining_days
        return remaining is not None and remaining > 0

    @property
    def is_collected(self):
        """Da li je uredjaj preuzet od strane kupca."""
        return self.owner_collect is not None or self.status == TicketStatus.DELIVERED

    @property
    def notification_count(self):
        """Broj svih notifikacija/poziva za ovaj nalog."""
        return self.notification_logs.count() if self.notification_logs else 0

    @property
    def last_notification(self):
        """Poslednja notifikacija/poziv kupcu."""
        if self.notification_logs:
            return self.notification_logs.order_by(
                TicketNotificationLog.timestamp.desc()
            ).first()
        return None

    @property
    def can_notify(self):
        """
        Da li mozemo obavestavati kupca.
        Pravilo: min 15 dana izmedju notifikacija, osim prve.
        """
        if self.is_collected or self.is_written_off:
            return False
        if self.notification_count == 0:
            return True  # Prva notifikacija uvek dozvoljena
        last = self.last_notification
        if last:
            days_since = (datetime.now(timezone.utc) - last.timestamp).days
            return days_since >= 15
        return True

    @property
    def can_write_off(self):
        """Da li moze write-off (min 5 notifikacija)."""
        return (
            self.notification_count >= 5 and
            not self.is_written_off and
            not self.is_collected
        )

    @property
    def days_until_can_notify(self):
        """Koliko dana do sledece moguce notifikacije."""
        if self.can_notify:
            return 0
        last = self.last_notification
        if last:
            days_since = (datetime.now(timezone.utc) - last.timestamp).days
            return max(0, 15 - days_since)
        return 0

    @property
    def duration_display(self):
        """Formatiran prikaz trajanja popravke."""
        if not self.created_at:
            return None

        if self.closed_at:
            delta = self.closed_at - self.created_at
        else:
            delta = datetime.utcnow() - self.created_at

        days = delta.days
        hours = delta.seconds // 3600

        if days > 0:
            return f"{days}d {hours}h"
        return f"{hours}h"

    def generate_access_token(self):
        """Generise jedinstveni token za javni pristup (QR kod)."""
        self.access_token = secrets.token_urlsafe(32)

    def close_ticket(self):
        """Zatvara nalog i postavlja datum zatvaranja."""
        self.status = TicketStatus.DELIVERED
        self.closed_at = datetime.utcnow()

    def mark_as_paid(self, payment_method='CASH'):
        """Oznacava nalog kao naplacen."""
        self.is_paid = True
        self.paid_at = datetime.utcnow()
        self.payment_method = payment_method

    def _parse_problem_areas(self):
        """Parse problem_areas - handles both JSON and comma-separated formats."""
        if not self.problem_areas:
            return None
        import json
        try:
            # Try JSON first
            return json.loads(self.problem_areas)
        except (json.JSONDecodeError, TypeError):
            # Fall back to comma-separated string
            return self.problem_areas

    def to_dict(self, include_sensitive=False):
        """Konvertuje nalog u dict za API response."""
        import json

        data = {
            'id': self.id,
            'ticket_number': self.ticket_number,
            'ticket_number_formatted': self.ticket_number_formatted,
            'customer_name': self.customer_name,
            'customer_phone': self.customer_phone,
            'customer_email': self.customer_email,
            'customer_company_name': self.customer_company_name,
            'customer_pib': self.customer_pib,
            'device_type': self.device_type,
            'brand': self.brand,
            'model': self.model,
            'imei': self.imei,
            'service_section': self.service_section,
            'device_condition_grade': self.device_condition_grade,
            'device_condition_notes': self.device_condition_notes,
            'device_not_working': self.device_not_working,
            'problem_areas': self._parse_problem_areas(),
            'problem_description': self.problem_description,
            'diagnosis': self.diagnosis,
            'resolution': self.resolution,
            'status': self.status.value,
            'priority': self.priority.value,
            'rejection_reason': self.rejection_reason,
            'estimated_price': float(self.estimated_price) if self.estimated_price else None,
            'final_price': float(self.final_price) if self.final_price else None,
            'currency': self.currency,
            'warranty_days': self.warranty_days,
            'warranty_expires_at': self.warranty_expires_at.isoformat() if self.warranty_expires_at else None,
            'warranty_remaining_days': self.warranty_remaining_days,
            'is_under_warranty': self.is_under_warranty,
            'is_paid': self.is_paid,
            'is_collected': self.is_collected,
            'owner_collect': self.owner_collect,
            'owner_collect_timestamp': self.owner_collect_timestamp.isoformat() if self.owner_collect_timestamp else None,
            'is_written_off': self.is_written_off,
            'written_off_timestamp': self.written_off_timestamp.isoformat() if self.written_off_timestamp else None,
            'notification_count': self.notification_count,
            'can_notify': self.can_notify,
            'can_write_off': self.can_write_off,
            'days_until_can_notify': self.days_until_can_notify,
            'duration_display': self.duration_display,
            'ticket_notes': self.ticket_notes,
            'billing_status': self.billing_status,
            'invoice_number': self.invoice_number,
            'assigned_technician_id': self.assigned_technician_id,
            'location_id': self.location_id,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'ready_at': self.ready_at.isoformat() if self.ready_at else None,
            'closed_at': self.closed_at.isoformat() if self.closed_at else None,
            'access_token': self.access_token,
        }

        # Dodaj ime tehnicara ako postoji
        if self.assigned_technician:
            data['assigned_technician_name'] = self.assigned_technician.full_name

        # Dodaj ime lokacije ako postoji
        if self.location:
            data['location_name'] = self.location.name

        if include_sensitive:
            data['device_condition'] = self.device_condition
            data['device_password'] = self.device_password

        return data


def get_next_ticket_number(tenant_id):
    """
    Vraca sledeci broj naloga za tenant.
    Thread-safe sa SELECT FOR UPDATE.
    """
    from sqlalchemy import func

    max_number = db.session.query(func.max(ServiceTicket.ticket_number)).filter(
        ServiceTicket.tenant_id == tenant_id
    ).scalar()

    return (max_number or 0) + 1


class TicketNotificationLog(db.Model):
    """
    Log poziva kupaca za preuzimanje uredjaja.

    Prati kada je i ko zvao kupca, i sta je kupac rekao.
    Koristi se za:
    - Pracenje broja pokusaja kontakta
    - Odredjivanje da li moze write-off (min 5 pokusaja)
    - Provera da li je proslo 15 dana od poslednjeg poziva
    """
    __tablename__ = 'ticket_notification_log'

    id = db.Column(db.Integer, primary_key=True)

    # Veza sa nalogom
    ticket_id = db.Column(
        db.BigInteger,
        db.ForeignKey('service_ticket.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Ko je zvao
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant_user.id', ondelete='SET NULL'),
        nullable=True
    )

    # Kada je poziv obavljen
    timestamp = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # Sta je kupac rekao / napomena o pozivu
    comment = db.Column(db.Text)

    # Tip notifikacije (poziv, SMS, email)
    notification_type = db.Column(db.String(20), default='CALL')  # CALL, SMS, EMAIL

    # Da li je uspesno kontaktiran
    contact_successful = db.Column(db.Boolean, default=False)

    # Relacije
    ticket = db.relationship(
        'ServiceTicket',
        backref=db.backref('notification_logs', lazy='dynamic', cascade='all, delete-orphan')
    )
    user = db.relationship('TenantUser', backref='ticket_notifications')

    # Indeksi
    __table_args__ = (
        db.Index('ix_notification_ticket_timestamp', 'ticket_id', 'timestamp'),
    )

    def __repr__(self):
        return f'<TicketNotificationLog {self.id} for ticket {self.ticket_id}>'

    def to_dict(self):
        """Konvertuje log u dict za API response."""
        data = {
            'id': self.id,
            'ticket_id': self.ticket_id,
            'user_id': self.user_id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'comment': self.comment,
            'notification_type': self.notification_type,
            'contact_successful': self.contact_successful,
        }

        if self.user:
            data['user_name'] = self.user.full_name

        return data
