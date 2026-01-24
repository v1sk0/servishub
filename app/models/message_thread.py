"""
Message Thread Model - Threaded Messaging System.

Podržava tri tipa konverzacija:
- SYSTEM: Sistemske notifikacije (read-only) - npr. package changes
- SUPPORT: Tenant ↔ Admin podrška
- NETWORK: Tenant ↔ Tenant komunikacija (zahteva TenantConnection)
"""

import enum
from datetime import datetime, timezone
from ..extensions import db


class ThreadType(enum.Enum):
    """Tip konverzacije."""
    SYSTEM = 'SYSTEM'       # Sistemske notifikacije (read-only)
    SUPPORT = 'SUPPORT'     # Tenant ↔ Admin
    NETWORK = 'NETWORK'     # Tenant ↔ Tenant


class ThreadStatus(enum.Enum):
    """Status konverzacije."""
    OPEN = 'OPEN'           # Nova/aktivna
    PENDING = 'PENDING'     # Čeka odgovor
    RESOLVED = 'RESOLVED'   # Zatvorena


class ThreadTag(enum.Enum):
    """Tagovi za kategorisanje konverzacija."""
    BILLING = 'BILLING'
    TECH = 'TECH'
    ORDER = 'ORDER'
    PACKAGE_CHANGE = 'PACKAGE_CHANGE'
    OUTAGE = 'OUTAGE'
    ANNOUNCEMENT = 'ANNOUNCEMENT'
    OTHER = 'OTHER'


class HiddenByType(enum.Enum):
    """Ko je sakrio poruku."""
    ADMIN = 'ADMIN'
    TENANT = 'TENANT'


class MessageThread(db.Model):
    """
    Conversation thread - grupira poruke.

    VAŽNO:
    - SYSTEM threads su read-only - tenant ne može reply
    - SUPPORT threads imaju SLA tracking
    - NETWORK threads zahtevaju aktivnu TenantConnection
    """
    __tablename__ = 'message_thread'

    id = db.Column(db.Integer, primary_key=True)

    # =========================================================================
    # Vlasnik thread-a
    # =========================================================================
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)

    # =========================================================================
    # Tip i status
    # =========================================================================
    thread_type = db.Column(db.Enum(ThreadType), nullable=False)
    status = db.Column(db.Enum(ThreadStatus), default=ThreadStatus.OPEN)

    # =========================================================================
    # Naslov i tagovi
    # =========================================================================
    subject = db.Column(db.String(200), nullable=False)
    # FIXED: koristi default=list, NE default=[]
    tags = db.Column(db.JSON, default=list)

    # =========================================================================
    # SLA tracking (za SUPPORT threads)
    # =========================================================================
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('platform_admin.id'))
    # VAŽNO: first_response_at se postavlja SAMO kad admin PRVI PUT odgovori
    first_response_at = db.Column(db.DateTime(timezone=True))
    last_reply_at = db.Column(db.DateTime(timezone=True))

    # =========================================================================
    # Za NETWORK tip - veza sa TenantConnection
    # =========================================================================
    connection_id = db.Column(db.Integer)  # ForeignKey se dodaje kad se kreira TenantConnection
    other_tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'))

    # =========================================================================
    # Timestamps
    # =========================================================================
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc))
    resolved_at = db.Column(db.DateTime(timezone=True))

    # =========================================================================
    # Relationships
    # =========================================================================
    tenant = db.relationship('Tenant', foreign_keys=[tenant_id], backref='message_threads')
    other_tenant = db.relationship('Tenant', foreign_keys=[other_tenant_id])
    assigned_to = db.relationship('PlatformAdmin', backref='assigned_threads')
    messages = db.relationship('Message', backref='thread', lazy='dynamic',
                               cascade='all, delete-orphan', order_by='Message.created_at')
    participants = db.relationship('ThreadParticipant', backref='thread',
                                   cascade='all, delete-orphan')

    def is_read_only(self) -> bool:
        """SYSTEM threads su read-only."""
        return self.thread_type == ThreadType.SYSTEM

    def record_admin_response(self):
        """Beleži prvi admin odgovor za SLA."""
        now = datetime.now(timezone.utc)
        if not self.first_response_at:
            self.first_response_at = now
        self.last_reply_at = now

    def record_reply(self):
        """Beleži bilo koji odgovor."""
        self.last_reply_at = datetime.now(timezone.utc)

    def resolve(self):
        """Zatvara thread."""
        self.status = ThreadStatus.RESOLVED
        self.resolved_at = datetime.now(timezone.utc)

    def reopen(self):
        """Ponovo otvara thread."""
        self.status = ThreadStatus.OPEN
        self.resolved_at = None

    def get_unread_count(self, user_type: str, user_id: int) -> int:
        """
        Vraća broj nepročitanih poruka za korisnika.

        Args:
            user_type: 'tenant_user' ili 'admin'
            user_id: ID korisnika

        Returns:
            Broj nepročitanih poruka
        """
        participant = ThreadParticipant.query.filter_by(
            thread_id=self.id
        ).filter(
            (ThreadParticipant.user_id == user_id) if user_type == 'tenant_user'
            else (ThreadParticipant.admin_id == user_id)
        ).first()

        if not participant or not participant.last_read_at:
            return self.messages.count()

        return self.messages.filter(
            Message.created_at > participant.last_read_at
        ).count()

    @classmethod
    def create_system_thread(cls, tenant_id: int, subject: str, tags: list = None,
                            admin_id: int = None) -> 'MessageThread':
        """
        Kreira SYSTEM thread (read-only sistemska notifikacija).

        Args:
            tenant_id: ID tenanta koji prima notifikaciju
            subject: Naslov notifikacije
            tags: Lista tagova (npr. ['PACKAGE_CHANGE', 'BILLING'])
            admin_id: ID admina koji kreira (opciono)

        Returns:
            Novi MessageThread objekat
        """
        thread = cls(
            tenant_id=tenant_id,
            thread_type=ThreadType.SYSTEM,
            subject=subject,
            tags=tags or [],
            status=ThreadStatus.RESOLVED,  # SYSTEM threads su uvek "resolved"
            assigned_to_id=admin_id
        )
        db.session.add(thread)
        return thread

    @classmethod
    def create_support_thread(cls, tenant_id: int, subject: str, tags: list = None) -> 'MessageThread':
        """
        Kreira SUPPORT thread (tenant ↔ admin podrška).

        Args:
            tenant_id: ID tenanta koji pokreće razgovor
            subject: Naslov
            tags: Lista tagova

        Returns:
            Novi MessageThread objekat
        """
        thread = cls(
            tenant_id=tenant_id,
            thread_type=ThreadType.SUPPORT,
            subject=subject,
            tags=tags or [],
            status=ThreadStatus.OPEN
        )
        db.session.add(thread)
        return thread

    def __repr__(self):
        return f'<MessageThread {self.id} [{self.thread_type.value}] "{self.subject[:30]}">'


class ThreadParticipant(db.Model):
    """
    Ko učestvuje u thread-u.

    Prati kada je korisnik poslednji put pročitao poruke.
    """
    __tablename__ = 'thread_participant'

    id = db.Column(db.Integer, primary_key=True)
    thread_id = db.Column(db.Integer, db.ForeignKey('message_thread.id'), nullable=False)

    # Jedan od ova tri mora biti popunjen
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('tenant_user.id'))
    admin_id = db.Column(db.Integer, db.ForeignKey('platform_admin.id'))

    # Role u thread-u
    role = db.Column(db.String(20))  # OWNER, PARTICIPANT, ADMIN

    # Read tracking
    last_read_at = db.Column(db.DateTime(timezone=True))
    # NAPOMENA: unread_count je CACHE - računa se iz last_read_at
    _unread_count_cache = db.Column('unread_count', db.Integer, default=0)

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    tenant = db.relationship('Tenant', backref='thread_participations')
    user = db.relationship('TenantUser', backref='thread_participations')
    admin = db.relationship('PlatformAdmin', backref='thread_participations')

    def mark_read(self):
        """Označava sve poruke kao pročitane."""
        self.last_read_at = datetime.now(timezone.utc)
        self._unread_count_cache = 0

    def get_unread_count(self) -> int:
        """Računa unread count iz last_read_at (source of truth)."""
        if not self.last_read_at:
            return self.thread.messages.count()
        return self.thread.messages.filter(
            Message.created_at > self.last_read_at
        ).count()

    def refresh_unread_cache(self):
        """Osvežava cache - pozovi samo sa servera."""
        self._unread_count_cache = self.get_unread_count()

    def __repr__(self):
        participant = self.user_id or self.admin_id or self.tenant_id
        return f'<ThreadParticipant thread={self.thread_id} participant={participant}>'


class Message(db.Model):
    """
    Pojedinačna poruka u thread-u.

    VAŽNO:
    - Poruke se NE brišu, samo sakrivaju (soft delete)
    - Edit čuva punu istoriju (audit trail)
    """
    __tablename__ = 'message'

    id = db.Column(db.Integer, primary_key=True)
    thread_id = db.Column(db.Integer, db.ForeignKey('message_thread.id'), nullable=False)

    # =========================================================================
    # Ko je poslao - jedan od ova tri mora biti popunjen
    # =========================================================================
    sender_tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'))
    sender_user_id = db.Column(db.Integer, db.ForeignKey('tenant_user.id'))
    sender_admin_id = db.Column(db.Integer, db.ForeignKey('platform_admin.id'))

    # =========================================================================
    # Sadržaj
    # =========================================================================
    body = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50))  # Opciona kategorija (PACKAGE_CHANGE, BILLING, etc.)

    # =========================================================================
    # Audit - edit tracking
    # =========================================================================
    is_edited = db.Column(db.Boolean, default=False)
    edited_at = db.Column(db.DateTime(timezone=True))
    # FIXED: koristi default=list, NE default=[]
    edit_history_json = db.Column(db.JSON, default=list)
    # Format: [{'body': 'stari tekst', 'edited_at': '...', 'edited_by': '...', 'edited_by_type': 'ADMIN|TENANT'}]

    # =========================================================================
    # Soft delete
    # =========================================================================
    is_hidden = db.Column(db.Boolean, default=False)
    hidden_at = db.Column(db.DateTime(timezone=True))
    hidden_by_id = db.Column(db.Integer)
    hidden_by_type = db.Column(db.Enum(HiddenByType))
    hidden_reason = db.Column(db.String(200))

    # =========================================================================
    # Timestamp
    # =========================================================================
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # =========================================================================
    # Relationships
    # =========================================================================
    sender_tenant = db.relationship('Tenant', backref='sent_messages')
    sender_user = db.relationship('TenantUser', backref='sent_messages')
    sender_admin = db.relationship('PlatformAdmin', backref='sent_messages')

    def edit(self, new_body: str, edited_by_id: int, edited_by_type: HiddenByType):
        """
        Edit poruke sa audit trail-om.

        Args:
            new_body: Novi tekst poruke
            edited_by_id: ID korisnika koji vrši edit
            edited_by_type: ADMIN ili TENANT
        """
        if self.edit_history_json is None:
            self.edit_history_json = []

        # Append stari tekst u history (immutable pattern)
        self.edit_history_json = self.edit_history_json + [{
            'body': self.body,
            'edited_at': datetime.now(timezone.utc).isoformat(),
            'edited_by': edited_by_id,
            'edited_by_type': edited_by_type.value
        }]

        self.body = new_body
        self.is_edited = True
        self.edited_at = datetime.now(timezone.utc)

    def hide(self, hidden_by_id: int, hidden_by_type: HiddenByType, reason: str = None):
        """
        Soft delete sa audit info.

        Args:
            hidden_by_id: ID korisnika koji skriva poruku
            hidden_by_type: ADMIN ili TENANT
            reason: Opcioni razlog
        """
        self.is_hidden = True
        self.hidden_at = datetime.now(timezone.utc)
        self.hidden_by_id = hidden_by_id
        self.hidden_by_type = hidden_by_type
        self.hidden_reason = reason

    def unhide(self):
        """Vraća sakrivenu poruku."""
        self.is_hidden = False
        self.hidden_at = None
        self.hidden_by_id = None
        self.hidden_by_type = None
        self.hidden_reason = None

    @property
    def sender_name(self) -> str:
        """Vraća ime pošiljaoca za prikaz."""
        if self.sender_admin:
            return f"{self.sender_admin.full_name} (ServisHub)"
        elif self.sender_user:
            return self.sender_user.full_name
        elif self.sender_tenant:
            return self.sender_tenant.name
        return "Nepoznat"

    @classmethod
    def create_system_message(cls, thread_id: int, body: str, admin_id: int = None,
                              category: str = None) -> 'Message':
        """
        Kreira sistemsku poruku u thread-u.

        Args:
            thread_id: ID thread-a
            body: Tekst poruke (može biti HTML)
            admin_id: ID admina koji kreira (opciono)
            category: Kategorija (npr. 'PACKAGE_CHANGE')

        Returns:
            Novi Message objekat
        """
        message = cls(
            thread_id=thread_id,
            sender_admin_id=admin_id,
            body=body,
            category=category
        )
        db.session.add(message)
        return message

    def __repr__(self):
        return f'<Message {self.id} thread={self.thread_id} from={self.sender_name[:20]}>'