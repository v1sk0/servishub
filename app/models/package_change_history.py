"""
Package Change History Model - Verzioniranje promena cena paketa.

Append-only audit log za promene cenovnika. Jednom kreiran zapis se NIKAD ne menja.
Omogućava:
- Verzioniranje promena (YYYY-MM-DD-NN format)
- Idempotency (sprečava duplikate)
- Per-tenant delivery tracking
- Full audit trail
"""

import enum
import hashlib
import json
from datetime import datetime, date, timezone, timedelta
from sqlalchemy import UniqueConstraint
from sqlalchemy.exc import IntegrityError
from ..extensions import db


class DeliveryStatus(enum.Enum):
    """Status dostave notifikacije."""
    PENDING = 'PENDING'      # Čeka na slanje
    SENT = 'SENT'            # Uspešno poslato
    FAILED = 'FAILED'        # Greška pri slanju
    SKIPPED = 'SKIPPED'      # Preskočeno (npr. neaktivan tenant)


class PackageChangeHistory(db.Model):
    """
    Append-only audit log promena cena paketa.

    VAŽNO:
    - Svi datumi se čuvaju u UTC!
    - effective_timezone služi samo za prikaz korisniku
    - Jednom kreiran zapis se NIKAD ne menja
    - Koristi create_with_version() za kreiranje novih zapisa
    """
    __tablename__ = 'package_change_history'

    id = db.Column(db.Integer, primary_key=True)

    # =========================================================================
    # Verzioniranje - RACE-SAFE pristup
    # =========================================================================
    change_date = db.Column(db.Date, nullable=False)  # Datum promene
    daily_seq = db.Column(db.Integer, nullable=False)  # Redni broj tog dana
    # change_version se računa kao property: f"{change_date}-{daily_seq:02d}"

    # =========================================================================
    # Append-only JSON snapshots
    # =========================================================================
    old_settings_json = db.Column(db.JSON, nullable=False)
    new_settings_json = db.Column(db.JSON, nullable=False)

    # =========================================================================
    # Kada stupa na snagu
    # =========================================================================
    effective_at_utc = db.Column(db.DateTime(timezone=True), nullable=False)
    effective_timezone = db.Column(db.String(50), default='Europe/Belgrade')

    # Razlog promene
    change_reason = db.Column(db.String(500))

    # =========================================================================
    # Idempotency - sprečava duplikate
    # =========================================================================
    idempotency_hash = db.Column(db.String(64), unique=True, nullable=False)
    # SHA-256 hash od: old_json + new_json + effective_at_utc.isoformat()

    # Ko je napravio promenu
    admin_id = db.Column(db.Integer, db.ForeignKey('platform_admin.id'))

    # =========================================================================
    # Notification stats (aggregate - summary only)
    # =========================================================================
    notification_started_at = db.Column(db.DateTime(timezone=True))
    notification_completed_at = db.Column(db.DateTime(timezone=True))
    tenants_notified = db.Column(db.Integer, default=0)
    emails_sent = db.Column(db.Integer, default=0)
    emails_failed = db.Column(db.Integer, default=0)

    # Timestamp (uvek UTC)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # =========================================================================
    # Relationships
    # =========================================================================
    deliveries = db.relationship('PackageChangeDelivery', backref='change', lazy='dynamic',
                                  cascade='all, delete-orphan')
    admin = db.relationship('PlatformAdmin', backref='package_changes')

    # Unique constraint za race-safe verzioniranje
    __table_args__ = (
        UniqueConstraint('change_date', 'daily_seq', name='uq_package_change_version'),
    )

    @property
    def change_version(self):
        """Computed verzija: YYYY-MM-DD-NN"""
        return f"{self.change_date.isoformat()}-{self.daily_seq:02d}"

    def get_effective_at_local(self):
        """Vraća effective_at u lokalnom timezone-u za prikaz."""
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(self.effective_timezone)
            return self.effective_at_utc.astimezone(tz)
        except Exception:
            # Fallback ako zoneinfo ne radi
            return self.effective_at_utc

    def get_price_diff(self):
        """Vraća razlike u cenama između stare i nove verzije."""
        old = self.old_settings_json or {}
        new = self.new_settings_json or {}

        diff = {}
        for key in ['base_price', 'location_price', 'trial_days', 'grace_period_days', 'default_commission']:
            old_val = old.get(key)
            new_val = new.get(key)
            if old_val != new_val:
                diff[key] = {'old': old_val, 'new': new_val}

        return diff

    @staticmethod
    def compute_idempotency_hash(old_json: dict, new_json: dict, effective_at_utc: datetime) -> str:
        """
        Računa SHA-256 hash za idempotency check.

        Args:
            old_json: Stare vrednosti podešavanja
            new_json: Nove vrednosti podešavanja
            effective_at_utc: Kada promena stupa na snagu (UTC)

        Returns:
            SHA-256 hash string (64 karaktera)
        """
        data = json.dumps({
            'old': old_json,
            'new': new_json,
            'effective': effective_at_utc.isoformat()
        }, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()

    @classmethod
    def create_with_version(cls, old_json: dict, new_json: dict, effective_at_utc: datetime,
                           admin_id: int, change_reason: str = None,
                           effective_timezone: str = 'Europe/Belgrade'):
        """
        Kreira novi zapis sa race-safe verzioniranjem.
        Koristi optimistic locking sa retry.

        Args:
            old_json: Stare vrednosti podešavanja
            new_json: Nove vrednosti podešavanja
            effective_at_utc: Kada promena stupa na snagu (UTC)
            admin_id: ID admina koji je napravio promenu
            change_reason: Opcioni razlog promene
            effective_timezone: Timezone za prikaz (default: Europe/Belgrade)

        Returns:
            Tuple[PackageChangeHistory, bool]: (zapis, created)
            - created=True ako je novi zapis kreiran
            - created=False ako je postojeći zapis vraćen (idempotency)

        Raises:
            RuntimeError: Ako ne uspe da generiše verziju nakon max pokušaja
        """
        # Računaj idempotency hash
        idempotency_hash = cls.compute_idempotency_hash(old_json, new_json, effective_at_utc)

        # Proveri da li već postoji (idempotency check)
        existing = cls.query.filter_by(idempotency_hash=idempotency_hash).first()
        if existing:
            return existing, False

        # Race-safe kreiranje verzije
        today = date.today()
        max_retries = 5

        for attempt in range(max_retries):
            # Nađi sledeći seq za danas
            last = cls.query.filter_by(change_date=today).order_by(
                cls.daily_seq.desc()
            ).first()
            next_seq = (last.daily_seq + 1) if last else 1

            change = cls(
                change_date=today,
                daily_seq=next_seq,
                old_settings_json=old_json,
                new_settings_json=new_json,
                effective_at_utc=effective_at_utc,
                effective_timezone=effective_timezone,
                idempotency_hash=idempotency_hash,
                admin_id=admin_id,
                change_reason=change_reason
            )

            try:
                db.session.add(change)
                db.session.flush()  # Proveri constraint pre commit-a
                return change, True
            except IntegrityError:
                db.session.rollback()
                if attempt == max_retries - 1:
                    raise RuntimeError(
                        f"Failed to generate unique version after {max_retries} retries"
                    )
                continue

        # Ovaj deo se nikad ne izvršava zbog raise iznad
        raise RuntimeError("Failed to generate unique version")

    def start_notification(self):
        """Označava početak slanja notifikacija."""
        self.notification_started_at = datetime.now(timezone.utc)

    def complete_notification(self, stats: dict = None):
        """
        Označava završetak slanja notifikacija.

        Args:
            stats: Dict sa statistikama (tenants_notified, emails_sent, emails_failed)
        """
        self.notification_completed_at = datetime.now(timezone.utc)
        if stats:
            self.tenants_notified = stats.get('tenants_notified', 0)
            self.emails_sent = stats.get('emails_sent', 0)
            self.emails_failed = stats.get('emails_failed', 0)

    def __repr__(self):
        return f'<PackageChangeHistory {self.change_version}>'


class PackageChangeDelivery(db.Model):
    """
    Per-tenant tracking dostave notifikacija o promeni paketa.

    Omogućava praćenje:
    - Da li je tenant primio email
    - Da li je tenant primio in-app notifikaciju
    - Greške pri dostavi
    - "Ko tvrdi da nije dobio" evidenciju
    """
    __tablename__ = 'package_change_delivery'

    id = db.Column(db.Integer, primary_key=True)

    # =========================================================================
    # Veza sa promenom i tenantom
    # =========================================================================
    change_id = db.Column(db.Integer, db.ForeignKey('package_change_history.id'), nullable=False)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)

    # =========================================================================
    # Email status
    # =========================================================================
    email_status = db.Column(db.Enum(DeliveryStatus), default=DeliveryStatus.PENDING)
    email_sent_at = db.Column(db.DateTime(timezone=True))
    email_error = db.Column(db.Text)
    email_recipient = db.Column(db.String(255))  # Email adresa na koju je poslato

    # =========================================================================
    # In-app notification status
    # =========================================================================
    inapp_status = db.Column(db.Enum(DeliveryStatus), default=DeliveryStatus.PENDING)
    inapp_created_at = db.Column(db.DateTime(timezone=True))
    inapp_thread_id = db.Column(db.Integer)  # ID MessageThread-a kad se implementira
    inapp_error = db.Column(db.Text)

    # Timestamps
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # =========================================================================
    # Relationships
    # =========================================================================
    tenant = db.relationship('Tenant', backref='package_change_deliveries')

    # Unique - jedan zapis po tenant/change kombinaciji
    __table_args__ = (
        UniqueConstraint('change_id', 'tenant_id', name='uq_package_delivery_per_tenant'),
    )

    def mark_email_sent(self, recipient: str):
        """Označava uspešno slanje emaila."""
        self.email_status = DeliveryStatus.SENT
        self.email_sent_at = datetime.now(timezone.utc)
        self.email_recipient = recipient

    def mark_email_failed(self, error: str):
        """Označava neuspešno slanje emaila."""
        self.email_status = DeliveryStatus.FAILED
        self.email_error = error

    def mark_email_skipped(self, reason: str):
        """Označava preskočeno slanje emaila."""
        self.email_status = DeliveryStatus.SKIPPED
        self.email_error = reason

    def mark_inapp_created(self, thread_id: int = None):
        """Označava uspešno kreiranje in-app notifikacije."""
        self.inapp_status = DeliveryStatus.SENT
        self.inapp_created_at = datetime.now(timezone.utc)
        if thread_id:
            self.inapp_thread_id = thread_id

    def mark_inapp_failed(self, error: str):
        """Označava neuspešno kreiranje in-app notifikacije."""
        self.inapp_status = DeliveryStatus.FAILED
        self.inapp_error = error

    @property
    def is_fully_delivered(self) -> bool:
        """Da li je notifikacija potpuno isporučena (email + in-app)."""
        return (
            self.email_status == DeliveryStatus.SENT and
            self.inapp_status == DeliveryStatus.SENT
        )

    def __repr__(self):
        return f'<PackageChangeDelivery change={self.change_id} tenant={self.tenant_id}>'