"""
Platform Admin model - administratori platforme.

Platform admini su odvojeni od tenant korisnika i imaju pristup
celom ekosistemu - mogu upravljati servisima, uplatama, KYC-om itd.
"""

import enum
from datetime import datetime
import bcrypt
from ..extensions import db


class AdminRole(enum.Enum):
    """
    Role platform admina.

    SUPER_ADMIN - Full pristup, moze brisati tenante i druge admine
    ADMIN - Standardni admin, sve osim brisanja
    SUPPORT - Read-only pristup, za korisnicku podrsku
    """
    SUPER_ADMIN = 'SUPER_ADMIN'
    ADMIN = 'ADMIN'
    SUPPORT = 'SUPPORT'


class PlatformAdmin(db.Model):
    """
    Platform admin - administrator ServisHub platforme.

    Odvojen od TenantUser jer ima pristup celom ekosistemu,
    ne samo jednom preduzecu.
    """
    __tablename__ = 'platform_admin'

    # Primarni kljuc
    id = db.Column(db.Integer, primary_key=True)

    # Auth podaci
    email = db.Column(db.String(100), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(200), nullable=False)

    # Profil
    ime = db.Column(db.String(50), nullable=False)
    prezime = db.Column(db.String(50), nullable=False)

    # Rola
    role = db.Column(
        db.Enum(AdminRole),
        default=AdminRole.ADMIN,
        nullable=False
    )

    # Status
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # Pracenje aktivnosti
    last_login_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<PlatformAdmin {self.id}: {self.email}>'

    @property
    def full_name(self):
        """Puno ime admina."""
        return f'{self.ime} {self.prezime}'

    def set_password(self, password):
        """
        Hashira i postavlja lozinku admina.
        """
        password_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt()
        self.password_hash = bcrypt.hashpw(password_bytes, salt).decode('utf-8')

    def check_password(self, password):
        """
        Proverava da li je lozinka ispravna.
        """
        password_bytes = password.encode('utf-8')
        hash_bytes = self.password_hash.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hash_bytes)

    def update_last_login(self):
        """Azurira vreme poslednjeg logina."""
        self.last_login_at = datetime.utcnow()

    def is_super_admin(self):
        """Da li je super admin."""
        return self.role == AdminRole.SUPER_ADMIN

    def can_delete_tenants(self):
        """Da li moze brisati tenante - samo SUPER_ADMIN."""
        return self.role == AdminRole.SUPER_ADMIN

    def can_manage_admins(self):
        """Da li moze upravljati drugim adminima - samo SUPER_ADMIN."""
        return self.role == AdminRole.SUPER_ADMIN

    def to_dict(self):
        """Konvertuje admina u dict za API response."""
        return {
            'id': self.id,
            'email': self.email,
            'ime': self.ime,
            'prezime': self.prezime,
            'full_name': self.full_name,
            'role': self.role.value,
            'is_active': self.is_active,
            'last_login_at': self.last_login_at.isoformat() if self.last_login_at else None,
        }
