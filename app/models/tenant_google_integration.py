"""
Tenant Google Integration Models

Modeli za integraciju sa Google Business Profile (Places API):
- TenantGoogleIntegration: OAuth tokeni i osnovni podaci
- TenantGoogleReview: Keširane recenzije sa Google-a
"""

from datetime import datetime
from app.extensions import db


class TenantGoogleIntegration(db.Model):
    """
    Google Business Profile integracija za tenant.

    Čuva OAuth tokene i osnovne podatke o Google profilu
    (rating, broj recenzija, place_id).
    """
    __tablename__ = 'tenant_google_integration'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), unique=True, nullable=False)

    # Google Place ID - jedinstveni identifikator lokacije na Google Maps
    google_place_id = db.Column(db.String(255))

    # Agregirani podaci sa Google-a
    google_rating = db.Column(db.Numeric(2, 1))  # npr. 4.8
    total_reviews = db.Column(db.Integer, default=0)

    # OAuth tokeni (enkriptovani u produkciji)
    access_token = db.Column(db.Text)
    refresh_token = db.Column(db.Text)
    token_expires_at = db.Column(db.DateTime)

    # Sync status
    last_sync_at = db.Column(db.DateTime)
    sync_error = db.Column(db.Text)  # Poslednja greška pri sync-u

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    tenant = db.relationship('Tenant', backref=db.backref('google_integration', uselist=False))
    reviews = db.relationship('TenantGoogleReview', backref='integration', lazy='dynamic',
                              cascade='all, delete-orphan')

    def __repr__(self):
        return f'<TenantGoogleIntegration tenant_id={self.tenant_id} rating={self.google_rating}>'

    def to_dict(self):
        """Serijalizacija za API odgovore."""
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'google_place_id': self.google_place_id,
            'google_rating': float(self.google_rating) if self.google_rating else None,
            'total_reviews': self.total_reviews,
            'last_sync_at': self.last_sync_at.isoformat() if self.last_sync_at else None,
            'has_valid_token': self.has_valid_token,
        }

    @property
    def has_valid_token(self):
        """Provera da li je OAuth token validan."""
        if not self.access_token or not self.token_expires_at:
            return False
        return datetime.utcnow() < self.token_expires_at

    @property
    def needs_sync(self):
        """Provera da li je potreban sync (stariji od 6 sati)."""
        if not self.last_sync_at:
            return True
        from datetime import timedelta
        return datetime.utcnow() - self.last_sync_at > timedelta(hours=6)


class TenantGoogleReview(db.Model):
    """
    Keširana Google recenzija.

    Čuva recenzije sa Google-a za prikaz na javnom sajtu tenanta.
    Recenzije se sync-uju periodično (svakih 6 sati).
    """
    __tablename__ = 'tenant_google_review'

    id = db.Column(db.Integer, primary_key=True)
    integration_id = db.Column(db.Integer, db.ForeignKey('tenant_google_integration.id'), nullable=False)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)

    # Google Review ID - za dedup prilikom sync-a
    google_review_id = db.Column(db.String(255), unique=True, nullable=False)

    # Review podaci
    author_name = db.Column(db.String(200))
    author_photo_url = db.Column(db.String(500))
    rating = db.Column(db.Integer)  # 1-5 zvezda
    text = db.Column(db.Text)
    language = db.Column(db.String(10))  # npr. 'sr', 'en'

    # Vreme recenzije (sa Google-a)
    review_time = db.Column(db.DateTime)

    # Vidljivost - admin može sakriti pojedine recenzije
    is_visible = db.Column(db.Boolean, default=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    tenant = db.relationship('Tenant', backref=db.backref('google_reviews', lazy='dynamic'))

    def __repr__(self):
        return f'<TenantGoogleReview {self.author_name} rating={self.rating}>'

    def to_dict(self):
        """Serijalizacija za API i template prikaz."""
        return {
            'id': self.id,
            'author_name': self.author_name,
            'author_photo_url': self.author_photo_url,
            'rating': self.rating,
            'text': self.text,
            'review_time': self.review_time.isoformat() if self.review_time else None,
            'is_visible': self.is_visible,
        }

    @property
    def author_initials(self):
        """Dobija inicijale autora za avatar placeholder."""
        if not self.author_name:
            return '?'
        parts = self.author_name.split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return self.author_name[0].upper()

    @property
    def relative_time(self):
        """Relativno vreme recenzije (npr. 'pre 2 meseca')."""
        if not self.review_time:
            return ''

        from datetime import timedelta
        now = datetime.utcnow()
        diff = now - self.review_time

        if diff < timedelta(days=1):
            return 'danas'
        elif diff < timedelta(days=2):
            return 'juče'
        elif diff < timedelta(days=7):
            return f'pre {diff.days} dana'
        elif diff < timedelta(days=30):
            weeks = diff.days // 7
            return f'pre {weeks} {"nedelju" if weeks == 1 else "nedelje" if weeks < 5 else "nedelja"}'
        elif diff < timedelta(days=365):
            months = diff.days // 30
            return f'pre {months} {"mesec" if months == 1 else "meseca" if months < 5 else "meseci"}'
        else:
            years = diff.days // 365
            return f'pre {years} {"godinu" if years == 1 else "godine" if years < 5 else "godina"}'
