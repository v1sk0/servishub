"""
Platform Settings Model - Globalna podesavanja platforme.

Cuva sve konfiguracione parametre platforme u bazi.
Koristi singleton pattern - postoji samo jedan red u tabeli.
"""

from datetime import datetime, timezone
from decimal import Decimal
from ..extensions import db


class PlatformSettings(db.Model):
    """
    Globalna podesavanja platforme.
    Singleton - uvek koristi PlatformSettings.get_settings()
    """
    __tablename__ = 'platform_settings'

    id = db.Column(db.Integer, primary_key=True)

    # Cenovnik
    base_price = db.Column(db.Numeric(10, 2), default=Decimal('3600.00'))  # Bazni paket RSD/mesec
    location_price = db.Column(db.Numeric(10, 2), default=Decimal('1800.00'))  # Dodatna lokacija RSD/mesec
    currency = db.Column(db.String(3), default='RSD')  # Valuta cenovnika

    # Trial i pretplate
    trial_days = db.Column(db.Integer, default=90)  # Trajanje trial perioda
    demo_days = db.Column(db.Integer, default=7)  # Trajanje demo perioda
    grace_period_days = db.Column(db.Integer, default=7)  # Grace period pre suspenzije

    # Dobavljaci
    default_commission = db.Column(db.Numeric(4, 2), default=Decimal('5.00'))  # % provizije

    # Timestamps
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc))
    updated_by_id = db.Column(db.Integer, db.ForeignKey('platform_admin.id'), nullable=True)

    # Relationships
    updated_by = db.relationship('PlatformAdmin', foreign_keys=[updated_by_id])

    @classmethod
    def get_settings(cls):
        """
        Vraca singleton instancu settings-a.
        Ako ne postoji, kreira sa default vrednostima.
        """
        settings = cls.query.first()
        if not settings:
            settings = cls()
            db.session.add(settings)
            db.session.commit()
        return settings

    @classmethod
    def update_settings(cls, data: dict, admin_id: int = None):
        """
        Azurira settings.

        Args:
            data: Dictionary sa novim vrednostima
            admin_id: ID admina koji menja

        Returns:
            Azurirana PlatformSettings instanca
        """
        settings = cls.get_settings()

        # Polja koja se mogu menjati
        allowed_fields = [
            'base_price', 'location_price', 'currency',
            'trial_days', 'demo_days', 'grace_period_days',
            'default_commission'
        ]

        for field in allowed_fields:
            if field in data and data[field] is not None:
                # Konvertuj u Decimal za numericka polja
                if field in ['base_price', 'location_price', 'default_commission']:
                    setattr(settings, field, Decimal(str(data[field])))
                else:
                    setattr(settings, field, data[field])

        if admin_id:
            settings.updated_by_id = admin_id

        settings.updated_at = datetime.now(timezone.utc)
        db.session.commit()

        return settings

    def to_dict(self):
        """Konvertuje u dictionary za API response."""
        return {
            'base_price': float(self.base_price) if self.base_price else 3600,
            'location_price': float(self.location_price) if self.location_price else 1800,
            'currency': self.currency or 'RSD',
            'trial_days': self.trial_days or 90,
            'demo_days': self.demo_days or 7,
            'grace_period_days': self.grace_period_days or 7,
            'default_commission': float(self.default_commission) if self.default_commission else 5.0,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }