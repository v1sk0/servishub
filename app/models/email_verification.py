"""
PendingEmailVerification model - za verifikaciju emaila pre registracije.

Korisnik mora da verifikuje email adresu pre nego sto moze da zavrsi
registraciju servisa. Ovo sprecava lazne registracije i osigurava
da korisnik ima pristup email adresi koju unosi.
"""

import secrets
import hashlib
from datetime import datetime, timezone, timedelta
from app.extensions import db


class PendingEmailVerification(db.Model):
    """
    Tabela za cuvanje pending email verifikacija.

    Flow:
    1. Korisnik unese email na registracionoj formi
    2. Sistem generise token i salje email sa linkom
    3. Korisnik klikne link i token se markira kao verified
    4. Pri registraciji, sistem proverava da li je email verifikovan
    5. Nakon uspesne registracije, zapis se brise
    """
    __tablename__ = 'pending_email_verification'

    id = db.Column(db.Integer, primary_key=True)

    # Email adresa koja se verifikuje
    email = db.Column(db.String(100), nullable=False, unique=True, index=True)

    # Hash tokena (nikad ne cuvamo plain token u bazi)
    token_hash = db.Column(db.String(64), nullable=False)

    # Da li je verifikovan
    verified = db.Column(db.Boolean, default=False, index=True)
    verified_at = db.Column(db.DateTime(timezone=True))

    # Istek tokena (24 sata od kreiranja)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)

    # Broj pokusaja slanja (rate limiting)
    send_count = db.Column(db.Integer, default=1)
    last_sent_at = db.Column(db.DateTime(timezone=True))

    # Timestamps
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Indeksi za brze pretrage
    __table_args__ = (
        db.Index('ix_pending_email_verified', 'email', 'verified'),
    )

    def __repr__(self):
        return f'<PendingEmailVerification {self.email} verified={self.verified}>'

    @staticmethod
    def generate_token():
        """
        Generise sigurnosni token za verifikaciju.
        Returns: (plain_token, token_hash)
        """
        # 32-byte token = 64 hex karaktera
        plain_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(plain_token.encode()).hexdigest()
        return plain_token, token_hash

    @staticmethod
    def hash_token(plain_token: str) -> str:
        """Hashira plain token za poredjenje sa bazom."""
        return hashlib.sha256(plain_token.encode()).hexdigest()

    @classmethod
    def create_or_update(cls, email: str) -> tuple:
        """
        Kreira novi zapis ili azurira postojeci za dati email.

        Returns:
            tuple: (PendingEmailVerification, plain_token, is_new)
        """
        # Normalizuj email
        email = email.lower().strip()

        # Generisi novi token
        plain_token, token_hash = cls.generate_token()

        # Nadji postojeci zapis
        existing = cls.query.filter_by(email=email).first()

        if existing:
            # Azuriraj postojeci
            existing.token_hash = token_hash
            existing.verified = False
            existing.verified_at = None
            existing.expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
            existing.send_count += 1
            existing.last_sent_at = datetime.now(timezone.utc)
            db.session.commit()
            return existing, plain_token, False
        else:
            # Kreiraj novi
            verification = cls(
                email=email,
                token_hash=token_hash,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
                last_sent_at=datetime.now(timezone.utc)
            )
            db.session.add(verification)
            db.session.commit()
            return verification, plain_token, True

    @classmethod
    def verify_token(cls, plain_token: str) -> tuple:
        """
        Verifikuje token i markira email kao verifikovan.

        Args:
            plain_token: Plain token iz URL-a

        Returns:
            tuple: (success: bool, email_or_error: str)
        """
        token_hash = cls.hash_token(plain_token)

        verification = cls.query.filter_by(token_hash=token_hash).first()

        if not verification:
            return False, "Nevazeci verifikacioni link."

        if verification.verified:
            return True, verification.email  # Vec verifikovan, OK

        if verification.expires_at < datetime.now(timezone.utc):
            return False, "Verifikacioni link je istekao. Zatrazite novi."

        # Markiraj kao verifikovan
        verification.verified = True
        verification.verified_at = datetime.now(timezone.utc)
        db.session.commit()

        return True, verification.email

    @classmethod
    def is_verified(cls, email: str) -> bool:
        """
        Proverava da li je email verifikovan.

        Args:
            email: Email adresa za proveru

        Returns:
            bool: True ako je verifikovan i nije istekao
        """
        email = email.lower().strip()

        verification = cls.query.filter_by(
            email=email,
            verified=True
        ).first()

        if not verification:
            return False

        # Verifikacija vazi 24 sata nakon sto je potvrdjena
        if verification.verified_at:
            expiry = verification.verified_at + timedelta(hours=24)
            if expiry < datetime.now(timezone.utc):
                return False

        return True

    @classmethod
    def delete_for_email(cls, email: str):
        """Brise verifikacioni zapis za dati email (posle uspesne registracije)."""
        email = email.lower().strip()
        cls.query.filter_by(email=email).delete()
        db.session.commit()

    @classmethod
    def can_resend(cls, email: str) -> tuple:
        """
        Proverava da li moze da se posalje novi email (rate limiting).

        Returns:
            tuple: (can_send: bool, seconds_remaining: int)
        """
        email = email.lower().strip()

        verification = cls.query.filter_by(email=email).first()

        if not verification:
            return True, 0

        # Max 5 pokusaja po email adresi
        if verification.send_count >= 5:
            return False, -1  # Blokiran

        # Cooldown od 60 sekundi izmedju pokusaja
        if verification.last_sent_at:
            elapsed = (datetime.now(timezone.utc) - verification.last_sent_at).total_seconds()
            if elapsed < 60:
                return False, int(60 - elapsed)

        return True, 0

    @classmethod
    def cleanup_expired(cls):
        """Brise istekle i neverifikovane zapise starije od 7 dana."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        cls.query.filter(
            cls.verified == False,
            cls.created_at < cutoff
        ).delete()
        db.session.commit()