"""
TenantPublicProfile - podešavanja javne stranice tenanta.

Omogućava tenantu da kreira javnu prezentacijsku stranicu sa:
- Osnovnim informacijama (naziv, opis, slogan)
- Kontakt podacima i radnim vremenom
- Brandingom (logo, cover slika, boje)
- Cenovnikom usluga (iz ServiceItem tabele)
- Custom domenom (pored subdomena na servishub.rs)
"""

from datetime import datetime
from ..extensions import db


class TenantPublicProfile(db.Model):
    """
    Podešavanja javne stranice tenanta.

    Svaki tenant može imati javnu stranicu dostupnu na:
    - {slug}.servishub.rs (subdomena)
    - custom_domain (npr. mojservis.rs) ako je podešen i verifikovan
    """
    __tablename__ = 'tenant_public_profile'

    # Primarni ključ
    id = db.Column(db.Integer, primary_key=True)

    # Veza sa tenantom (1:1)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        unique=True,
        index=True
    )

    # ============================================
    # VIDLJIVOST
    # ============================================
    is_public = db.Column(db.Boolean, default=False)  # Da li je stranica javna

    # ============================================
    # OSNOVNI PODACI (override tenant data)
    # ============================================
    display_name = db.Column(db.String(200))      # Ako je drugačije od tenant.name
    tagline = db.Column(db.String(300))           # Kratki slogan
    description = db.Column(db.Text)               # Opis firme (može markdown)

    # ============================================
    # KONTAKT
    # ============================================
    phone = db.Column(db.String(50))
    phone_secondary = db.Column(db.String(50))    # Drugi telefon
    email = db.Column(db.String(100))
    address = db.Column(db.String(300))
    city = db.Column(db.String(100))
    postal_code = db.Column(db.String(20))
    maps_url = db.Column(db.String(500))          # Google Maps embed link
    maps_embed_url = db.Column(db.String(500))    # Google Maps iframe src

    # ============================================
    # RADNO VREME (JSON)
    # ============================================
    # Format: {"mon": "09:00-18:00", "tue": "09:00-18:00", ..., "sun": "Zatvoreno"}
    working_hours = db.Column(db.JSON, default=dict)

    # ============================================
    # BRANDING
    # ============================================
    logo_url = db.Column(db.String(500))          # Cloudinary URL
    cover_image_url = db.Column(db.String(500))   # Header slika
    primary_color = db.Column(db.String(7), default='#3b82f6')    # Hex boja
    secondary_color = db.Column(db.String(7), default='#1e40af')  # Hex boja

    # ============================================
    # SOCIAL LINKOVI
    # ============================================
    facebook_url = db.Column(db.String(300))
    instagram_url = db.Column(db.String(300))
    twitter_url = db.Column(db.String(300))
    linkedin_url = db.Column(db.String(300))
    youtube_url = db.Column(db.String(300))
    tiktok_url = db.Column(db.String(300))
    website_url = db.Column(db.String(300))       # Eksterni website

    # ============================================
    # SEO
    # ============================================
    meta_title = db.Column(db.String(100))
    meta_description = db.Column(db.String(200))
    meta_keywords = db.Column(db.String(300))

    # ============================================
    # CENOVNIK PRIKAZ
    # ============================================
    show_prices = db.Column(db.Boolean, default=True)  # Prikaži cene
    price_disclaimer = db.Column(
        db.String(500),
        default='Cene su okvirne i podložne promenama nakon dijagnostike.'
    )

    # ============================================
    # CUSTOM DOMEN
    # ============================================
    custom_domain = db.Column(db.String(255), unique=True, index=True)  # npr. "mojservis.rs"
    custom_domain_verified = db.Column(db.Boolean, default=False)
    custom_domain_verification_token = db.Column(db.String(64))  # Token za DNS TXT verifikaciju
    custom_domain_verified_at = db.Column(db.DateTime)

    # SSL status za custom domen (Let's Encrypt)
    custom_domain_ssl_status = db.Column(db.String(20), default='pending')  # pending, active, failed

    # ============================================
    # DODATNE SEKCIJE
    # ============================================
    # About sekcija - više teksta
    about_title = db.Column(db.String(200))
    about_content = db.Column(db.Text)

    # Zašto mi sekcija
    why_us_title = db.Column(db.String(200))
    why_us_items = db.Column(db.JSON, default=list)  # [{"icon": "...", "title": "...", "text": "..."}]

    # Galerija
    gallery_images = db.Column(db.JSON, default=list)  # ["url1", "url2", ...]

    # Testimonijali
    testimonials = db.Column(db.JSON, default=list)  # [{"name": "...", "text": "...", "rating": 5}]

    # ============================================
    # FAQ - Često postavljana pitanja
    # ============================================
    faq_title = db.Column(db.String(200), default='Često postavljana pitanja')
    faq_items = db.Column(db.JSON, default=list)  # [{"question": "...", "answer": "..."}]

    # ============================================
    # BRENDOVI
    # ============================================
    show_brands_section = db.Column(db.Boolean, default=True)
    supported_brands = db.Column(db.JSON, default=list)  # ["apple", "samsung", "xiaomi", ...]

    # ============================================
    # PROCES RADA
    # ============================================
    show_process_section = db.Column(db.Boolean, default=True)
    process_title = db.Column(db.String(200), default='Kako funkcioniše')
    process_steps = db.Column(db.JSON, default=list)
    # Format: [{"step": 1, "icon": "📱", "title": "...", "description": "..."}]

    # ============================================
    # WHATSAPP
    # ============================================
    show_whatsapp_button = db.Column(db.Boolean, default=False)
    whatsapp_number = db.Column(db.String(20))  # Bez + i razmaka, npr: "381641234567"
    whatsapp_message = db.Column(db.String(300), default='Zdravo! Imam pitanje u vezi servisa.')

    # ============================================
    # STATUS TRACKING WIDGET
    # ============================================
    show_tracking_widget = db.Column(db.Boolean, default=True)
    tracking_widget_title = db.Column(db.String(200), default='Pratite status Vaše popravke')

    # ============================================
    # HERO STIL
    # ============================================
    hero_style = db.Column(db.String(20), default='centered')  # 'centered', 'split', 'minimal'

    # ============================================
    # TRUST BADGES
    # ============================================
    warranty_days = db.Column(db.Integer, default=90)  # Za trust badge
    show_trust_badges = db.Column(db.Boolean, default=True)
    fast_service_text = db.Column(db.String(50), default='1-3 sata')  # Npr: "1-3h", "Isti dan"

    # ============================================
    # KURIR SEKCIJA
    # ============================================
    show_courier_section = db.Column(db.Boolean, default=False)
    courier_price = db.Column(db.Integer)  # Cena u RSD
    courier_title = db.Column(db.String(100), default='Ne možete doći? Šaljemo kurira!')
    courier_description = db.Column(db.String(300), default='Besplatno preuzimanje i dostava na Vašu adresu.')

    # ============================================
    # POPULARNI SERVISI
    # ============================================
    show_popular_services = db.Column(db.Boolean, default=True)
    popular_services_title = db.Column(db.String(100), default='Najpopularnije usluge')
    popular_services_limit = db.Column(db.Integer, default=6)

    # ============================================
    # TEMA SAJTA
    # ============================================
    # Tri predefinisane teme sa različitim stilovima:
    # - starter: Čista, profesionalna, plava paleta (default)
    # - premium: Moderna, glassmorphism efekti, ljubičasta paleta
    # - elite: Luksuzna, dark mode, zlatni akcenti
    theme = db.Column(db.String(20), default='starter')

    # ============================================
    # TIMESTAMPS
    # ============================================
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # ============================================
    # RELACIJE
    # ============================================
    tenant = db.relationship('Tenant', backref=db.backref('public_profile', uselist=False))

    def __repr__(self):
        return f'<TenantPublicProfile tenant_id={self.tenant_id}>'

    def get_domain_verification_instructions(self):
        """Vraća instrukcije za DNS verifikaciju custom domena."""
        if not self.custom_domain or not self.custom_domain_verification_token:
            return None

        return {
            'type': 'CNAME',
            'host': f'_servishub-verify.{self.custom_domain}',
            'value': f'{self.custom_domain_verification_token}.verify.servishub.rs',
            'alternative': {
                'type': 'TXT',
                'host': f'_servishub-verify.{self.custom_domain}',
                'value': f'servishub-verify={self.custom_domain_verification_token}'
            }
        }

    def to_dict(self, include_private=False):
        """Serijalizuje profil za API."""
        data = {
            'is_public': self.is_public,
            'display_name': self.display_name,
            'tagline': self.tagline,
            'description': self.description,
            'contact': {
                'phone': self.phone,
                'phone_secondary': self.phone_secondary,
                'email': self.email,
                'address': self.address,
                'city': self.city,
                'postal_code': self.postal_code,
                'maps_url': self.maps_url,
                'maps_embed_url': self.maps_embed_url,
            },
            'working_hours': self.working_hours or {},
            'branding': {
                'logo_url': self.logo_url,
                'cover_image_url': self.cover_image_url,
                'primary_color': self.primary_color,
                'secondary_color': self.secondary_color,
            },
            'social': {
                'facebook': self.facebook_url,
                'instagram': self.instagram_url,
                'twitter': self.twitter_url,
                'linkedin': self.linkedin_url,
                'youtube': self.youtube_url,
                'tiktok': self.tiktok_url,
                'website': self.website_url,
            },
            'seo': {
                'meta_title': self.meta_title,
                'meta_description': self.meta_description,
                'meta_keywords': self.meta_keywords,
            },
            'pricing': {
                'show_prices': self.show_prices,
                'disclaimer': self.price_disclaimer,
            },
            'sections': {
                'about_title': self.about_title,
                'about_content': self.about_content,
                'why_us_title': self.why_us_title,
                'why_us_items': self.why_us_items or [],
                'gallery_images': self.gallery_images or [],
                'testimonials': self.testimonials or [],
            },
            'faq': {
                'title': self.faq_title,
                'items': self.faq_items or [],
            },
            'brands': {
                'show_section': self.show_brands_section,
                'supported': self.supported_brands or [],
            },
            'process': {
                'show_section': self.show_process_section,
                'title': self.process_title,
                'steps': self.process_steps or [],
            },
            'whatsapp': {
                'show_button': self.show_whatsapp_button,
                'number': self.whatsapp_number,
                'message': self.whatsapp_message,
            },
            'tracking': {
                'show_widget': self.show_tracking_widget,
                'title': self.tracking_widget_title,
            },
            'hero_style': self.hero_style,
            'theme': self.theme or 'starter',
            'trust_badges': {
                'show': self.show_trust_badges,
                'warranty_days': self.warranty_days or 90,
                'fast_service_text': self.fast_service_text or '1-3 sata',
            },
            'courier': {
                'show_section': self.show_courier_section,
                'price': self.courier_price,
                'title': self.courier_title,
                'description': self.courier_description,
            },
            'popular_services': {
                'show': self.show_popular_services,
                'title': self.popular_services_title,
                'limit': self.popular_services_limit or 6,
            },
        }

        if include_private:
            data['custom_domain'] = {
                'domain': self.custom_domain,
                'verified': self.custom_domain_verified,
                'verified_at': self.custom_domain_verified_at.isoformat() if self.custom_domain_verified_at else None,
                'ssl_status': self.custom_domain_ssl_status,
                'verification_instructions': self.get_domain_verification_instructions(),
            }

        return data

    def to_public_dict(self, tenant):
        """
        Vraća podatke za javnu stranicu (bez privatnih informacija).
        Kombinuje podatke iz profila i tenanta.
        """
        return {
            'name': self.display_name or tenant.name,
            'slug': tenant.slug,
            'subdomain_url': f'https://{tenant.slug}.servishub.rs',
            'custom_domain_url': f'https://{self.custom_domain}' if self.custom_domain and self.custom_domain_verified else None,
            'tagline': self.tagline,
            'description': self.description,
            'contact': {
                'phone': self.phone or tenant.telefon,
                'phone_secondary': self.phone_secondary,
                'email': self.email or tenant.email,
                'address': self.address or tenant.adresa_sedista,
                'city': self.city or tenant.grad,
                'postal_code': self.postal_code or tenant.postanski_broj,
                'maps_url': self.maps_url,
                'maps_embed_url': self.maps_embed_url,
            },
            'working_hours': self.working_hours or {},
            'branding': {
                'logo_url': self.logo_url,
                'cover_image_url': self.cover_image_url,
                'primary_color': self.primary_color or '#3b82f6',
                'secondary_color': self.secondary_color or '#1e40af',
            },
            'social': {
                'facebook': self.facebook_url,
                'instagram': self.instagram_url,
                'twitter': self.twitter_url,
                'linkedin': self.linkedin_url,
                'youtube': self.youtube_url,
                'tiktok': self.tiktok_url,
                'website': self.website_url,
            },
            'seo': {
                'title': self.meta_title or (self.display_name or tenant.name),
                'description': self.meta_description or self.tagline,
                'keywords': self.meta_keywords,
            },
            'pricing': {
                'show_prices': self.show_prices,
                'disclaimer': self.price_disclaimer,
            },
            'sections': {
                'about_title': self.about_title,
                'about_content': self.about_content,
                'why_us_title': self.why_us_title,
                'why_us_items': self.why_us_items or [],
                'gallery_images': self.gallery_images or [],
                'testimonials': self.testimonials or [],
            },
            'faq': {
                'title': self.faq_title or 'Često postavljana pitanja',
                'items': self.faq_items or [],
            },
            'brands': {
                'show_section': self.show_brands_section,
                'supported': self.supported_brands or [],
            },
            'process': {
                'show_section': self.show_process_section,
                'title': self.process_title or 'Kako funkcioniše',
                'steps': self.process_steps or [],
            },
            'whatsapp': {
                'show_button': self.show_whatsapp_button,
                'number': self.whatsapp_number,
                'message': self.whatsapp_message,
            },
            'tracking': {
                'show_widget': self.show_tracking_widget,
                'title': self.tracking_widget_title or 'Pratite status Vaše popravke',
            },
            'hero_style': self.hero_style or 'centered',
            'theme': self.theme or 'starter',
            'trust_badges': {
                'show': self.show_trust_badges if self.show_trust_badges is not None else True,
                'warranty_days': self.warranty_days or 90,
                'fast_service_text': self.fast_service_text or '1-3 sata',
            },
            'courier': {
                'show_section': self.show_courier_section,
                'price': self.courier_price,
                'title': self.courier_title or 'Ne možete doći? Šaljemo kurira!',
                'description': self.courier_description or 'Besplatno preuzimanje i dostava na Vašu adresu.',
            },
            'popular_services': {
                'show': self.show_popular_services if self.show_popular_services is not None else True,
                'title': self.popular_services_title or 'Najpopularnije usluge',
                'limit': self.popular_services_limit or 6,
            },
        }
