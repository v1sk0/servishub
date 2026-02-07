"""
Service model - usluge koje tenant nudi.

ServiceItem predstavlja jednu uslugu u cenovniku tenanta.
Svaki tenant moze definisati svoje usluge sa cenama i kategorijama.
Kategorije su potpuno fleksibilne - tenant moze definisati bilo koju kategoriju.
"""

from datetime import datetime
from ..extensions import db


# Predefinisane kategorije kao sugestije (tenant moze koristiti bilo koju)
DEFAULT_CATEGORIES = [
    'Mobilni telefoni',
    'Tableti',
    'Laptopovi',
    'Racunari',
    'Konzole',
    'Trotineti',
    'Satovi',
    'Slusalice',
    'Ostalo',
]


class ServiceItem(db.Model):
    """
    ServiceItem - usluga u cenovniku tenanta.

    Svaki tenant moze definisati svoje usluge sa cenama, opisima i kategorijama.
    Kategorija je slobodan string - tenant moze koristiti predefinisane
    ili kreirati potpuno nove kategorije.
    Naziv usluge mora biti jedinstven unutar tenanta.
    """
    __tablename__ = 'service_item'

    # Primarni kljuc
    id = db.Column(db.BigInteger, primary_key=True)

    # Veza sa tenantom
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Identifikator za POS
    code = db.Column(db.String(20), index=True)  # USL-001

    # Osnovni podaci usluge
    name = db.Column(db.String(200), nullable=False)  # Naziv usluge
    description = db.Column(db.Text)  # Opis usluge

    # Kategorija - slobodan string (npr. "Konzole", "Laptopovi", "Trotineti")
    category = db.Column(db.String(100), default='Ostalo', nullable=False, index=True)

    # Cena
    price = db.Column(db.Numeric(10, 2), nullable=False)  # Cena usluge
    currency = db.Column(db.String(3), default='RSD', nullable=False)  # Valuta (RSD, EUR)
    price_note = db.Column(db.String(200))  # Napomena o ceni ("od", "po satu", "po uredjaju")
    is_variable_price = db.Column(db.Boolean, default=False)  # Dozvoljeno menjanje cene pri prodaji

    # Fiskalno
    tax_label = db.Column(db.String(1), default='A')  # A=20%, B=10%, C=0%

    # Redosled i status
    display_order = db.Column(db.Integer, default=0, index=True)  # Redosled prikaza
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)  # Da li je aktivna

    # Timestampovi
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Relacije
    tenant = db.relationship('Tenant', backref=db.backref('services', lazy='dynamic'))

    # Unique constraint: naziv mora biti jedinstven po tenantu
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'name', name='uq_service_tenant_name'),
        db.Index('ix_service_tenant_order', 'tenant_id', 'display_order'),
        db.Index('ix_service_tenant_category', 'tenant_id', 'category'),
    )

    def __repr__(self):
        return f'<ServiceItem {self.id}: {self.name}>'

    def to_dict(self, include_tenant=False):
        """Serijalizuje uslugu u dictionary za API."""
        data = {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'description': self.description,
            'category': self.category,
            'price': float(self.price) if self.price else 0,
            'currency': self.currency,
            'price_note': self.price_note,
            'is_variable_price': self.is_variable_price,
            'tax_label': self.tax_label,
            'display_order': self.display_order,
            'is_active': self.is_active,
            'item_type': 'SERVICE',  # Za razlikovanje od GoodsItem u POS
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_tenant:
            data['tenant_id'] = self.tenant_id
        return data

    @staticmethod
    def generate_code(tenant_id: int) -> str:
        """Generiše sledeći kod usluge: USL-001, USL-002..."""
        last = ServiceItem.query.filter_by(tenant_id=tenant_id).filter(
            ServiceItem.code.like('USL-%')
        ).order_by(ServiceItem.code.desc()).first()

        next_num = 1
        if last and last.code:
            try:
                next_num = int(last.code.split('-')[-1]) + 1
            except ValueError:
                pass
        return f"USL-{next_num:03d}"
