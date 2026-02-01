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

    # SMS Cenovnik
    sms_price_credits = db.Column(db.Numeric(10, 4), default=Decimal('0.20'))  # Cena SMS u kreditima

    # Trial i pretplate
    trial_days = db.Column(db.Integer, default=90)  # DEPRECATED: koristi promo_months
    demo_days = db.Column(db.Integer, default=7)  # Trajanje demo perioda
    grace_period_days = db.Column(db.Integer, default=7)  # Grace period pre suspenzije
    promo_months = db.Column(db.Integer, default=2)  # v3.05: PROMO period u mesecima

    # Dobavljaci
    default_commission = db.Column(db.Numeric(4, 2), default=Decimal('5.00'))  # % provizije

    # =========================================================================
    # Podaci o firmi ServisHub - koristi se na fakturama, notifikacijama, itd.
    # =========================================================================
    company_name = db.Column(db.String(200), default='ServisHub DOO')
    company_address = db.Column(db.String(300), default='')
    company_city = db.Column(db.String(100), default='Beograd')
    company_postal_code = db.Column(db.String(20), default='')
    company_country = db.Column(db.String(100), default='Srbija')
    company_pib = db.Column(db.String(20), default='')  # PIB
    company_mb = db.Column(db.String(20), default='')  # Matični broj
    company_phone = db.Column(db.String(50), default='')
    company_email = db.Column(db.String(100), default='')
    company_website = db.Column(db.String(200), default='')
    company_bank_name = db.Column(db.String(100), default='')
    company_bank_account = db.Column(db.String(50), default='')  # Broj računa

    # =========================================================================
    # v303 Billing - IPS QR Settings
    # =========================================================================
    ips_purpose_code = db.Column(db.String(4), default='221')  # 221 = B2B usluge

    # =========================================================================
    # Kontakt podaci za landing page
    # =========================================================================
    contact_email = db.Column(db.String(100), default='')  # Email za kontakt na landing page
    contact_phone = db.Column(db.String(50), default='')  # Telefon za kontakt na landing page
    contact_location = db.Column(db.String(200), default='')  # Lokacija (npr. "Beograd, Srbija")

    # Social media linkovi
    social_twitter = db.Column(db.String(255), default='')
    social_facebook = db.Column(db.String(255), default='')
    social_instagram = db.Column(db.String(255), default='')
    social_linkedin = db.Column(db.String(255), default='')
    social_youtube = db.Column(db.String(255), default='')

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
            'trial_days', 'demo_days', 'grace_period_days', 'promo_months',
            'default_commission',
            # SMS Pricing
            'sms_price_credits',
            # Company data (includes social for landing page)
            'company_name', 'company_address', 'company_city',
            'company_postal_code', 'company_country', 'company_pib',
            'company_mb', 'company_phone', 'company_email',
            'company_website', 'company_bank_name', 'company_bank_account',
            # IPS settings (v303)
            'ips_purpose_code',
            # Social media (koristi se na landing page)
            'social_twitter', 'social_facebook', 'social_instagram',
            'social_linkedin', 'social_youtube'
        ]

        for field in allowed_fields:
            if field in data and data[field] is not None:
                # Konvertuj u Decimal za numericka polja
                if field in ['base_price', 'location_price', 'default_commission', 'sms_price_credits']:
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
        promo_months = self.promo_months or 2
        return {
            'base_price': float(self.base_price) if self.base_price else 3600,
            'location_price': float(self.location_price) if self.location_price else 1800,
            'currency': self.currency or 'RSD',
            'trial_days': self.trial_days or 90,  # DEPRECATED: koristi promo_days
            'promo_months': promo_months,
            'promo_days': promo_months * 30,  # Aproksimacija za prikaz
            'demo_days': self.demo_days or 7,
            'grace_period_days': self.grace_period_days or 7,
            'default_commission': float(self.default_commission) if self.default_commission else 5.0,
            # SMS pricing
            'sms_price_credits': float(self.sms_price_credits) if self.sms_price_credits else 0.20,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            # Company data
            'company': self.get_company_data()
        }

    def get_company_data(self):
        """Vraca podatke o firmi ServisHub (ukljucuje i social za landing)."""
        return {
            'name': self.company_name or 'ServisHub DOO',
            'address': self.company_address or '',
            'city': self.company_city or 'Beograd',
            'postal_code': self.company_postal_code or '',
            'country': self.company_country or 'Srbija',
            'pib': self.company_pib or '',
            'mb': self.company_mb or '',
            'phone': self.company_phone or '',
            'email': self.company_email or '',
            'website': self.company_website or '',
            'bank_name': self.company_bank_name or '',
            'bank_account': self.company_bank_account or '',
            # IPS QR settings (v303)
            'ips_purpose_code': self.ips_purpose_code or '221',
            # Social media za landing page
            'social_twitter': self.social_twitter or '',
            'social_facebook': self.social_facebook or '',
            'social_instagram': self.social_instagram or '',
            'social_linkedin': self.social_linkedin or '',
            'social_youtube': self.social_youtube or ''
        }

    @classmethod
    def get_company_info(cls):
        """
        Staticka metoda za dobijanje podataka o firmi.
        Koristi se u fakturama, emailovima, itd.
        """
        settings = cls.get_settings()
        return settings.get_company_data()

    def get_contact_data(self):
        """
        Vraca kontakt podatke za landing page.
        Koristi company_* polja direktno.
        """
        return {
            'email': self.company_email or '',
            'phone': self.company_phone or '',
            'location': f"{self.company_city or 'Beograd'}, {self.company_country or 'Srbija'}",
            'social': {
                'twitter': self.social_twitter or '',
                'facebook': self.social_facebook or '',
                'instagram': self.social_instagram or '',
                'linkedin': self.social_linkedin or '',
                'youtube': self.social_youtube or ''
            }
        }

    @classmethod
    def get_landing_contact(cls):
        """
        Staticka metoda za dobijanje kontakt podataka za landing page.
        """
        settings = cls.get_settings()
        return settings.get_contact_data()