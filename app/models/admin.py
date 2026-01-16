"""
Platform Admin model - administratori platforme.

Platform admini su odvojeni od tenant korisnika i imaju pristup
celom ekosistemu - mogu upravljati servisima, uplatama, KYC-om itd.

Podrska za 2FA (TOTP) autentifikaciju.
"""

import enum
from datetime import datetime
import bcrypt
import pyotp
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

    # 2FA (TOTP) polja
    totp_secret = db.Column(db.String(32), nullable=True)  # Base32 TOTP secret
    is_2fa_enabled = db.Column(db.Boolean, default=False, nullable=False)
    totp_verified_at = db.Column(db.DateTime, nullable=True)  # Kada je 2FA verifikovan
    backup_codes = db.Column(db.Text, nullable=True)  # JSON lista backup kodova (hashirani)

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

    # =====================
    # 2FA (TOTP) metode
    # =====================

    def generate_totp_secret(self) -> str:
        """
        Generise novi TOTP secret za 2FA.
        Vraca Base32 enkodiran secret.
        """
        self.totp_secret = pyotp.random_base32()
        self.is_2fa_enabled = False  # Nije omoguceno dok korisnik ne verifikuje
        return self.totp_secret

    def get_totp_uri(self) -> str:
        """
        Vraca TOTP URI za QR kod.
        Format: otpauth://totp/ServisHub:email?secret=XXX&issuer=ServisHub
        """
        if not self.totp_secret:
            return None

        totp = pyotp.TOTP(self.totp_secret)
        return totp.provisioning_uri(
            name=self.email,
            issuer_name='ServisHub Admin'
        )

    def verify_totp(self, code: str) -> bool:
        """
        Verifikuje TOTP kod.

        Args:
            code: 6-cifreni TOTP kod

        Returns:
            True ako je kod validan
        """
        if not self.totp_secret:
            return False

        totp = pyotp.TOTP(self.totp_secret)
        # valid_window=1 dozvoljava kod iz prethodnog/sledeceg 30s intervala
        return totp.verify(code, valid_window=1)

    def enable_2fa(self, code: str) -> bool:
        """
        Omogucava 2FA nakon verifikacije prvog koda.

        Args:
            code: 6-cifreni TOTP kod za verifikaciju

        Returns:
            True ako je 2FA uspesno omogucen
        """
        if self.verify_totp(code):
            self.is_2fa_enabled = True
            self.totp_verified_at = datetime.utcnow()
            return True
        return False

    def disable_2fa(self) -> None:
        """Onemogucava 2FA."""
        self.is_2fa_enabled = False
        self.totp_secret = None
        self.totp_verified_at = None
        self.backup_codes = None

    def generate_backup_codes(self) -> list:
        """
        Generise backup kodove za 2FA recovery.
        Vraca listu od 10 kodova.
        Hashirani kodovi se cuvaju u bazi.
        """
        import secrets
        import json

        codes = [secrets.token_hex(4).upper() for _ in range(10)]  # 8 karaktera svaki

        # Hashiraj kodove pre cuvanja
        hashed_codes = []
        for code in codes:
            code_bytes = code.encode('utf-8')
            salt = bcrypt.gensalt()
            hashed = bcrypt.hashpw(code_bytes, salt).decode('utf-8')
            hashed_codes.append(hashed)

        self.backup_codes = json.dumps(hashed_codes)
        return codes  # Vrati originalne kodove korisniku (prikazuju se samo jednom)

    def use_backup_code(self, code: str) -> bool:
        """
        Koristi backup kod umesto TOTP koda.
        Kod se moze koristiti samo jednom.

        Args:
            code: 8-karakterni backup kod

        Returns:
            True ako je kod validan i iskoriscen
        """
        import json

        if not self.backup_codes:
            return False

        code = code.upper().replace('-', '').replace(' ', '')
        code_bytes = code.encode('utf-8')
        hashed_codes = json.loads(self.backup_codes)

        for i, hashed in enumerate(hashed_codes):
            hash_bytes = hashed.encode('utf-8')
            if bcrypt.checkpw(code_bytes, hash_bytes):
                # Ukloni iskoriscen kod
                hashed_codes.pop(i)
                self.backup_codes = json.dumps(hashed_codes)
                return True

        return False

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
            'is_2fa_enabled': self.is_2fa_enabled,
            'last_login_at': self.last_login_at.isoformat() if self.last_login_at else None,
        }
