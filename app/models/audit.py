"""
Audit Log model - pracenje svih promena u sistemu.

AuditLog cuva sve CREATE, UPDATE, DELETE operacije na entitetima.
Koristi se za debugging, compliance i pracenje aktivnosti.
"""

import enum
from datetime import datetime
from flask import request, g
from ..extensions import db


class AuditAction(enum.Enum):
    """
    Tip akcije koja se loguje.

    CREATE - Kreiran novi entitet
    UPDATE - Azuriran postojeci entitet
    DELETE - Obrisan entitet
    STATUS_CHANGE - Promena statusa (posebna kategorija UPDATE-a)
    LOGIN - Uspesno logovanje
    LOGOUT - Odjava
    LOGIN_FAILED - Neuspesno logovanje
    """
    CREATE = 'CREATE'
    UPDATE = 'UPDATE'
    DELETE = 'DELETE'
    STATUS_CHANGE = 'STATUS_CHANGE'
    LOGIN = 'LOGIN'
    LOGOUT = 'LOGOUT'
    LOGIN_FAILED = 'LOGIN_FAILED'


class AuditLog(db.Model):
    """
    Audit log zapis - jedan red za svaku promenu u sistemu.

    Cuva ko je napravio promenu, na kom entitetu, sta je bilo pre
    i sta je posle promene. Koristi se za:
    - Debugging problema
    - Pracenje ko je sta menjao
    - Compliance i security audit
    - Vracanje prethodnih verzija podataka
    """
    __tablename__ = 'audit_log'

    # Primarni kljuc
    id = db.Column(db.BigInteger, primary_key=True)

    # Veza sa preduzecem (nullable za platform-level events)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )

    # Koji entitet je promenjen
    entity_type = db.Column(db.String(50), nullable=False, index=True)  # "ticket", "phone", "user"
    entity_id = db.Column(db.BigInteger, nullable=False)  # ID entiteta

    # Tip akcije
    action = db.Column(
        db.Enum(AuditAction),
        nullable=False,
        index=True
    )

    # Ko je izvrsio akciju
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant_user.id', ondelete='SET NULL'),
        nullable=True
    )
    user_email = db.Column(db.String(100))  # Denormalizovano - da imamo podatak i ako se user obrise

    # Sta je promenjeno (JSON)
    # Format: {"field_name": {"old": "stara vrednost", "new": "nova vrednost"}}
    changes_json = db.Column(db.JSON, default=dict)

    # Kontekst zahteva
    ip_address = db.Column(db.String(50))    # IP adresa korisnika
    user_agent = db.Column(db.String(500))   # Browser/klijent info
    request_id = db.Column(db.String(50))    # Za korelaciju vise logova iz istog zahteva

    # Timestamp
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True
    )

    # Indeksi za brze pretrage
    __table_args__ = (
        db.Index('ix_audit_tenant_entity', 'tenant_id', 'entity_type', 'entity_id'),
        db.Index('ix_audit_tenant_created', 'tenant_id', 'created_at'),
        db.Index('ix_audit_user_created', 'user_id', 'created_at'),
    )

    def __repr__(self):
        return f'<AuditLog {self.id}: {self.action.value} {self.entity_type}:{self.entity_id}>'

    @classmethod
    def log(cls, entity_type, entity_id, action, changes=None, tenant_id=None, user=None, user_id=None):
        """
        Kreira novi audit log zapis.

        Args:
            entity_type: Tip entiteta ("ticket", "phone", "user", itd.)
            entity_id: ID entiteta koji je promenjen
            action: AuditAction enum vrednost
            changes: Dict sa promenama {field: {old: x, new: y}}
            tenant_id: ID tenanta (opciono, uzima iz g.current_tenant)
            user: User objekat (opciono, uzima iz g.current_user)

        Returns:
            Kreirani AuditLog objekat
        """
        # Pokusaj da dohvatis kontekst iz Flask g objekta
        if tenant_id is None and hasattr(g, 'current_tenant') and g.current_tenant:
            tenant_id = g.current_tenant.id
        if user is None and hasattr(g, 'current_user'):
            user = g.current_user

        # Dohvati IP i user agent iz request-a ako postoji
        ip_address = None
        user_agent = None
        request_id = None
        try:
            if request:
                ip_address = request.remote_addr
                user_agent = request.headers.get('User-Agent', '')[:500]
                request_id = request.headers.get('X-Request-ID')
        except RuntimeError:
            # Van request konteksta (npr. CLI, background job)
            pass

        log_entry = cls(
            tenant_id=tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            user_id=user.id if user else user_id,
            user_email=user.email if user else None,
            changes_json=changes or {},
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )

        db.session.add(log_entry)
        # Ne radimo commit ovde - to ce uraditi pozivalac ili ce se desiti na kraju request-a

        return log_entry

    @classmethod
    def log_create(cls, entity_type, entity_id, data, **kwargs):
        """Pomocna metoda za logovanje CREATE akcije."""
        changes = {'created': {'old': None, 'new': data}}
        return cls.log(entity_type, entity_id, AuditAction.CREATE, changes, **kwargs)

    @classmethod
    def log_update(cls, entity_type, entity_id, changes, **kwargs):
        """Pomocna metoda za logovanje UPDATE akcije."""
        return cls.log(entity_type, entity_id, AuditAction.UPDATE, changes, **kwargs)

    @classmethod
    def log_delete(cls, entity_type, entity_id, data, **kwargs):
        """Pomocna metoda za logovanje DELETE akcije."""
        changes = {'deleted': {'old': data, 'new': None}}
        return cls.log(entity_type, entity_id, AuditAction.DELETE, changes, **kwargs)

    @classmethod
    def log_status_change(cls, entity_type, entity_id, old_status, new_status, **kwargs):
        """Pomocna metoda za logovanje promene statusa."""
        changes = {'status': {'old': old_status, 'new': new_status}}
        return cls.log(entity_type, entity_id, AuditAction.STATUS_CHANGE, changes, **kwargs)


def calculate_changes(old_data, new_data, fields=None):
    """
    Racuna razlike izmedju stare i nove verzije podataka.

    Args:
        old_data: Dict sa starim podacima
        new_data: Dict sa novim podacima
        fields: Lista polja za praćenje (ako None, prati sva)

    Returns:
        Dict sa promenama: {field: {old: x, new: y}}
    """
    changes = {}

    if fields is None:
        fields = set(old_data.keys()) | set(new_data.keys())

    for field in fields:
        old_val = old_data.get(field)
        new_val = new_data.get(field)

        # Konvertuj datetime u string za uporedjivanje
        if hasattr(old_val, 'isoformat'):
            old_val = old_val.isoformat()
        if hasattr(new_val, 'isoformat'):
            new_val = new_val.isoformat()

        if old_val != new_val:
            changes[field] = {'old': old_val, 'new': new_val}

    return changes
