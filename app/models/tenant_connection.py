"""
Tenant Connection & Invite Models - Tenant-to-Tenant Networking.

Omogućava servisima da se povežu i komuniciraju:
- Invite: Sigurni invite linkovi za povezivanje
- TenantConnection: Bidirekciona veza sa dozvolama

VAŽNO:
- Token se NIKAD ne čuva u plaintextu - samo hash!
- Connection uvek ima tenant_a < tenant_b (konzistentnost)
- BLOCKED status automatski blokira sve komunikacije
"""

import enum
import secrets
import hashlib
from datetime import datetime, timezone, timedelta
from sqlalchemy import UniqueConstraint, CheckConstraint
from ..extensions import db


class ConnectionStatus(enum.Enum):
    """Status konekcije između dva tenanta."""
    PENDING_INVITEE = 'PENDING_INVITEE'   # Čeka da B prihvati
    PENDING_INVITER = 'PENDING_INVITER'   # Čeka da A potvrdi (2-step)
    ACTIVE = 'ACTIVE'                      # Aktivna konekcija
    BLOCKED = 'BLOCKED'                    # Blokirana


def _default_permissions():
    """Factory za default permissions - izbegava mutable default bug."""
    return {
        'can_message': True,
        'can_share_contacts': False,
        'can_order_parts': False
    }


class Invite(db.Model):
    """
    Invite link za povezivanje servisa.

    SIGURNOST:
    - Token se generiše kriptografski sigurno (secrets.token_urlsafe)
    - U bazi se čuva SAMO SHA-256 hash tokena
    - token_hint (prvih 6 karaktera) služi za support/debug

    KORIŠĆENJE:
    1. create() vraća (Invite, plaintext_token) - token se vraća SAMO jednom!
    2. find_by_token() pronalazi invite po plaintext tokenu
    3. use() označava korišćenje (inkrementira used_count)
    """
    __tablename__ = 'invite'

    id = db.Column(db.Integer, primary_key=True)

    # NIKAD ne čuvaj plaintext token!
    token_hash = db.Column(db.String(64), unique=True, nullable=False)

    # Token hint za support/debug (prva 6 karaktera)
    # Nema sigurnosnog rizika - nedovoljno za brute force
    token_hint = db.Column(db.String(6))

    # Ko je kreirao
    created_by_tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('tenant_user.id'))

    # Poruka uz invite
    message = db.Column(db.Text)

    # Ograničenja
    max_uses = db.Column(db.Integer, default=1)  # 1 = jednokratan
    used_count = db.Column(db.Integer, default=0)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)

    # Revoke
    revoked_at = db.Column(db.DateTime(timezone=True))
    revoked_reason = db.Column(db.String(200))

    # Rate limiting
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    created_by_tenant = db.relationship('Tenant', backref='created_invites')
    created_by_user = db.relationship('TenantUser', backref='created_invites')

    @classmethod
    def create(cls, tenant_id: int, user_id: int = None, message: str = None,
               max_uses: int = 1, expires_in_days: int = 7) -> tuple:
        """
        Kreira novi invite sa sigurnim tokenom.

        Args:
            tenant_id: ID tenanta koji kreira invite
            user_id: ID korisnika koji kreira (opciono)
            message: Poruka uz invite (opciono)
            max_uses: Maksimalan broj korišćenja (default 1)
            expires_in_days: Za koliko dana ističe (default 7)

        Returns:
            Tuple (Invite object, plaintext_token)

        VAŽNO: plaintext_token se vraća SAMO jednom - sačuvaj ga!
        """
        # Generiši kriptografski siguran token
        plaintext_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(plaintext_token.encode()).hexdigest()
        token_hint = plaintext_token[:6]

        invite = cls(
            token_hash=token_hash,
            token_hint=token_hint,
            created_by_tenant_id=tenant_id,
            created_by_user_id=user_id,
            message=message,
            max_uses=max_uses,
            expires_at=datetime.now(timezone.utc) + timedelta(days=expires_in_days)
        )

        db.session.add(invite)
        return invite, plaintext_token

    @classmethod
    def find_by_token(cls, plaintext_token: str) -> 'Invite':
        """
        Pronalazi invite po plaintext tokenu.

        Args:
            plaintext_token: Originalni token iz URL-a

        Returns:
            Invite objekat ili None
        """
        token_hash = hashlib.sha256(plaintext_token.encode()).hexdigest()
        return cls.query.filter_by(token_hash=token_hash).first()

    def is_valid(self) -> bool:
        """Proverava da li je invite validan."""
        if self.revoked_at:
            return False
        if self.expires_at < datetime.now(timezone.utc):
            return False
        if self.used_count >= self.max_uses:
            return False
        return True

    def get_validation_error(self) -> str:
        """Vraća razlog zašto invite nije validan."""
        if self.revoked_at:
            return "Ovaj poziv je poništen"
        if self.expires_at < datetime.now(timezone.utc):
            return "Ovaj poziv je istekao"
        if self.used_count >= self.max_uses:
            return "Ovaj poziv je već iskorišćen"
        return None

    def use(self):
        """Označava korišćenje invita."""
        self.used_count += 1

    def revoke(self, reason: str = None):
        """Poništava invite."""
        self.revoked_at = datetime.now(timezone.utc)
        self.revoked_reason = reason

    def __repr__(self):
        return f'<Invite {self.id} hint={self.token_hint} uses={self.used_count}/{self.max_uses}>'


class TenantConnection(db.Model):
    """
    Veza između dva servisa.

    VAŽNO:
    - UVEK koristi get_or_create() umesto ručnog kreiranja
    - tenant_a_id < tenant_b_id (constraint garantuje konzistentnost)
    - BLOCKED status automatski blokira SVE komunikacije
    """
    __tablename__ = 'tenant_connection'

    id = db.Column(db.Integer, primary_key=True)

    # Oba tenanta (bidirectional) - UVEK a < b
    tenant_a_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    tenant_b_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)

    # Status
    status = db.Column(db.Enum(ConnectionStatus), default=ConnectionStatus.PENDING_INVITEE)

    # Koji invite je korišćen
    invite_id = db.Column(db.Integer, db.ForeignKey('invite.id'))

    # Ko je inicirao (tenant koji je poslao invite)
    initiated_by_tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'))

    # Granularne dozvole - koristi factory function za default
    permissions_json = db.Column(db.JSON, default=_default_permissions)

    # Block info
    blocked_by_tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'))
    blocked_reason = db.Column(db.String(200))
    blocked_at = db.Column(db.DateTime(timezone=True))

    # Timestamps
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    connected_at = db.Column(db.DateTime(timezone=True))  # Kad je postalo ACTIVE

    # Relationships
    tenant_a = db.relationship('Tenant', foreign_keys=[tenant_a_id], backref='connections_as_a')
    tenant_b = db.relationship('Tenant', foreign_keys=[tenant_b_id], backref='connections_as_b')
    initiated_by = db.relationship('Tenant', foreign_keys=[initiated_by_tenant_id])
    blocked_by = db.relationship('Tenant', foreign_keys=[blocked_by_tenant_id])
    invite = db.relationship('Invite', backref='connections')

    # Constraints
    __table_args__ = (
        UniqueConstraint('tenant_a_id', 'tenant_b_id', name='uq_tenant_connection'),
        CheckConstraint('tenant_a_id < tenant_b_id', name='ck_tenant_order'),
    )

    @classmethod
    def get_or_create(cls, tenant_id_1: int, tenant_id_2: int) -> 'TenantConnection':
        """
        Dohvata ili kreira konekciju (uvek isti redosled).

        VAŽNO: UVEK koristi ovu metodu - nikad ne kreiraj ručno!

        Args:
            tenant_id_1: ID prvog tenanta
            tenant_id_2: ID drugog tenanta

        Returns:
            TenantConnection objekat (postojeći ili novi)
        """
        a, b = min(tenant_id_1, tenant_id_2), max(tenant_id_1, tenant_id_2)
        conn = cls.query.filter_by(tenant_a_id=a, tenant_b_id=b).first()
        if not conn:
            conn = cls(tenant_a_id=a, tenant_b_id=b)
            db.session.add(conn)
        return conn

    @classmethod
    def get_connection(cls, tenant_id_1: int, tenant_id_2: int) -> 'TenantConnection':
        """Dohvata postojeću konekciju ili None."""
        a, b = min(tenant_id_1, tenant_id_2), max(tenant_id_1, tenant_id_2)
        return cls.query.filter_by(tenant_a_id=a, tenant_b_id=b).first()

    @classmethod
    def are_connected(cls, tenant_id_1: int, tenant_id_2: int) -> bool:
        """Proverava aktivnu konekciju."""
        conn = cls.get_connection(tenant_id_1, tenant_id_2)
        return conn and conn.status == ConnectionStatus.ACTIVE

    @classmethod
    def get_connections_for_tenant(cls, tenant_id: int, status: ConnectionStatus = None):
        """
        Vraća sve konekcije za tenanta.

        Args:
            tenant_id: ID tenanta
            status: Opciono filtriranje po statusu

        Returns:
            Query objekat sa konekcijama
        """
        from sqlalchemy import or_
        query = cls.query.filter(
            or_(cls.tenant_a_id == tenant_id, cls.tenant_b_id == tenant_id)
        )
        if status:
            query = query.filter(cls.status == status)
        return query

    def get_other_tenant_id(self, my_tenant_id: int) -> int:
        """Vraća ID drugog tenanta u konekciji."""
        if my_tenant_id == self.tenant_a_id:
            return self.tenant_b_id
        return self.tenant_a_id

    def get_other_tenant(self, my_tenant_id: int):
        """Vraća drugog tenanta u konekciji."""
        if my_tenant_id == self.tenant_a_id:
            return self.tenant_b
        return self.tenant_a

    def can_message(self) -> bool:
        """Proverava da li je dozvoljen messaging."""
        if self.status == ConnectionStatus.BLOCKED:
            return False
        if self.status != ConnectionStatus.ACTIVE:
            return False
        return self.permissions_json.get('can_message', False)

    def can_share_contacts(self) -> bool:
        """Proverava da li je dozvoljeno deljenje kontakata."""
        if self.status != ConnectionStatus.ACTIVE:
            return False
        return self.permissions_json.get('can_share_contacts', False)

    def can_order_parts(self) -> bool:
        """Proverava da li je dozvoljena narudžbina delova."""
        if self.status != ConnectionStatus.ACTIVE:
            return False
        return self.permissions_json.get('can_order_parts', False)

    def activate(self):
        """Aktivira konekciju."""
        self.status = ConnectionStatus.ACTIVE
        self.connected_at = datetime.now(timezone.utc)

    def block(self, blocked_by_tenant_id: int, reason: str = None):
        """
        Blokira konekciju.

        BLOCKED = automatski block svih poruka + hide threads
        """
        self.status = ConnectionStatus.BLOCKED
        self.blocked_by_tenant_id = blocked_by_tenant_id
        self.blocked_reason = reason
        self.blocked_at = datetime.now(timezone.utc)

    def unblock(self):
        """Deblokira konekciju (vraća na ACTIVE)."""
        self.status = ConnectionStatus.ACTIVE
        self.blocked_by_tenant_id = None
        self.blocked_reason = None
        self.blocked_at = None

    def update_permissions(self, permissions: dict):
        """Ažurira dozvole."""
        if self.permissions_json is None:
            self.permissions_json = _default_permissions()

        # Merge sa postojećim
        self.permissions_json = {**self.permissions_json, **permissions}

    def to_dict(self, for_tenant_id: int) -> dict:
        """Konvertuje u dict za API (iz perspektive datog tenanta)."""
        other_tenant = self.get_other_tenant(for_tenant_id)
        return {
            'id': self.id,
            'partner': {
                'id': other_tenant.id,
                'name': other_tenant.name,
                'slug': other_tenant.slug,
                'logo_url': getattr(other_tenant, 'logo_url', None)
            },
            'status': self.status.value,
            'permissions': self.permissions_json,
            'is_initiator': self.initiated_by_tenant_id == for_tenant_id,
            'connected_at': self.connected_at.isoformat() if self.connected_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'blocked_by_me': self.blocked_by_tenant_id == for_tenant_id if self.blocked_by_tenant_id else False
        }

    def __repr__(self):
        return f'<TenantConnection {self.id} {self.tenant_a_id}<->{self.tenant_b_id} [{self.status.value}]>'