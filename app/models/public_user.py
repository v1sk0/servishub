"""
PublicUser model - fizičko lice (krajnji korisnik) u B2C marketplace-u.
"""

import enum
from datetime import datetime
import bcrypt
from ..extensions import db


class PublicUserStatus(enum.Enum):
    """Status javnog korisnika."""
    PENDING = 'PENDING'
    ACTIVE = 'ACTIVE'
    SUSPENDED = 'SUSPENDED'
    BANNED = 'BANNED'


class PublicUser(db.Model):
    """Fizičko lice koje traži servis usluge."""
    __tablename__ = 'public_user'

    id = db.Column(db.BigInteger, primary_key=True)

    # Auth
    email = db.Column(db.String(100), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(200))
    email_verified = db.Column(db.Boolean, default=False)

    # OAuth
    google_id = db.Column(db.String(100), unique=True)
    auth_provider = db.Column(db.String(20), default='email')  # 'email' | 'google'

    # Profil
    ime = db.Column(db.String(50), nullable=False)
    prezime = db.Column(db.String(50), nullable=False)
    telefon = db.Column(db.String(30))
    grad = db.Column(db.String(100), index=True)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

    # Status
    status = db.Column(
        db.Enum(PublicUserStatus),
        default=PublicUserStatus.PENDING,
        nullable=False,
        index=True
    )

    # Rating
    rating = db.Column(db.Numeric(2, 1))
    rating_count = db.Column(db.Integer, default=0)

    # GDPR
    consent_given_at = db.Column(db.DateTime)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = db.Column(db.DateTime)

    def __repr__(self):
        return f'<PublicUser {self.id}: {self.email}>'

    @property
    def full_name(self):
        return f'{self.ime} {self.prezime}'

    def set_password(self, password):
        password_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt()
        self.password_hash = bcrypt.hashpw(password_bytes, salt).decode('utf-8')

    def check_password(self, password):
        if not self.password_hash:
            return False
        password_bytes = password.encode('utf-8')
        hash_bytes = self.password_hash.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hash_bytes)