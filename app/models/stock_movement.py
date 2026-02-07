"""
StockMovement - Jedinstven ledger za sve promene zaliha.

PRAVILO: Svaka promena zaliha MORA proći kroz ovaj model.
Nikad direktno menjati quantity na LocationStock!

Tipovi pokreta:
- INITIAL_BALANCE: Početno stanje (import, ručni unos)
- RECEIVE: Prijem robe (faktura, otkup)
- SALE: Prodaja kroz POS
- USE_TICKET: Utrošak na servisnom nalogu
- USE_INTERNAL: Interni utrošak (potrošni materijal)
- RETURN: Povrat od kupca
- ADJUST: Korekcija (inventura) - samo admin
- DAMAGE: Oštećenje/otpis
- TRANSFER_OUT: Izlaz za transfer (između lokacija)
- TRANSFER_IN: Ulaz od transfera
"""

import enum
from datetime import datetime
from decimal import Decimal
from ..extensions import db


class MovementType(enum.Enum):
    """Tip promene zaliha."""
    INITIAL_BALANCE = 'INITIAL_BALANCE'  # Početno stanje (import, ručni unos)
    RECEIVE = 'RECEIVE'           # Prijem robe (faktura, otkup)
    SALE = 'SALE'                 # Prodaja kroz POS
    USE_TICKET = 'USE_TICKET'     # Utrošak na servisnom nalogu
    USE_INTERNAL = 'USE_INTERNAL' # Interni utrošak (potrošni materijal)
    RETURN = 'RETURN'             # Povrat od kupca
    ADJUST = 'ADJUST'             # Korekcija (inventura) - samo admin
    DAMAGE = 'DAMAGE'             # Oštećenje/otpis
    TRANSFER_OUT = 'TRANSFER_OUT' # Izlaz za transfer (između lokacija)
    TRANSFER_IN = 'TRANSFER_IN'   # Ulaz od transfera


class LocationStock(db.Model):
    """
    Cache stanja artikla po lokaciji.

    Pravo stanje se računa iz StockMovement, ovo je samo cache za brze upite.
    NIKAD direktno menjati quantity - uvek kroz create_stock_movement()!
    """
    __tablename__ = 'location_stock'

    id = db.Column(db.BigInteger, primary_key=True)
    location_id = db.Column(
        db.Integer,
        db.ForeignKey('service_location.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Šta (jedno od dva)
    goods_item_id = db.Column(
        db.Integer,
        db.ForeignKey('goods_item.id', ondelete='CASCADE'),
        nullable=True
    )
    spare_part_id = db.Column(
        db.BigInteger,
        db.ForeignKey('spare_part.id', ondelete='CASCADE'),
        nullable=True
    )

    # Cache stanja
    quantity = db.Column(db.Integer, default=0, nullable=False)

    # Poslednja promena
    last_movement_id = db.Column(db.BigInteger, nullable=True)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Relacije
    location = db.relationship('ServiceLocation', backref='stock_items')
    goods_item = db.relationship('GoodsItem', backref='location_stocks')
    spare_part = db.relationship('SparePart', backref='location_stocks')

    __table_args__ = (
        db.CheckConstraint(
            '(goods_item_id IS NOT NULL AND spare_part_id IS NULL) OR '
            '(goods_item_id IS NULL AND spare_part_id IS NOT NULL)',
            name='ck_loc_stock_one_item'
        ),
        db.UniqueConstraint('location_id', 'goods_item_id', name='uq_loc_stock_goods'),
        db.UniqueConstraint('location_id', 'spare_part_id', name='uq_loc_stock_spare'),
    )

    def __repr__(self):
        item = f"goods:{self.goods_item_id}" if self.goods_item_id else f"part:{self.spare_part_id}"
        return f'<LocationStock {self.location_id}: {item} qty={self.quantity}>'


class StockMovement(db.Model):
    """
    Ledger tabela - svaka promena zaliha je novi red.

    NIKAD ne raditi UPDATE ili DELETE na ovoj tabeli!
    Za ispravku: novi red sa suprotnim predznakom + reason.
    """
    __tablename__ = 'stock_movement'

    id = db.Column(db.BigInteger, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    location_id = db.Column(
        db.Integer,
        db.ForeignKey('service_location.id', ondelete='RESTRICT'),
        nullable=False,
        index=True
    )

    # Šta se menja (jedno od dva) - RESTRICT jer ne možemo brisati artikal sa istorijom
    goods_item_id = db.Column(
        db.Integer,
        db.ForeignKey('goods_item.id', ondelete='RESTRICT'),
        nullable=True,
        index=True
    )
    spare_part_id = db.Column(
        db.BigInteger,
        db.ForeignKey('spare_part.id', ondelete='RESTRICT'),
        nullable=True,
        index=True
    )

    # Za transfere - odredišna lokacija
    target_location_id = db.Column(
        db.Integer,
        db.ForeignKey('service_location.id', ondelete='SET NULL'),
        nullable=True
    )

    # Tip i količina
    movement_type = db.Column(
        db.Enum(MovementType),
        nullable=False,
        index=True
    )
    quantity = db.Column(db.Integer, nullable=False)  # + ili -

    # Stanje PRE i POSLE (za validaciju)
    balance_before = db.Column(db.Integer, nullable=False)
    balance_after = db.Column(db.Integer, nullable=False)

    # Cena u trenutku pokreta (za FIFO/kalkulacije)
    unit_cost = db.Column(db.Numeric(10, 2), nullable=True)
    unit_price = db.Column(db.Numeric(10, 2), nullable=True)  # Prodajna cena (za SALE)

    # Referenca na dokument
    reference_type = db.Column(db.String(30), nullable=True)  # 'purchase_invoice', 'buyback', 'pos_receipt', 'ticket', 'adjustment', 'transfer_request'
    reference_id = db.Column(db.BigInteger, nullable=True)
    reference_number = db.Column(db.String(50), nullable=True)  # Broj dokumenta za prikaz

    # Audit - OBAVEZNO
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('tenant_user.id', ondelete='SET NULL'),
        nullable=False
    )
    reason = db.Column(db.String(255), nullable=True)  # Obavezno za ADJUST, DAMAGE, INITIAL_BALANCE
    notes = db.Column(db.Text, nullable=True)

    # Timestamp - nikad se ne menja
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True
    )

    # Relacije
    location = db.relationship('ServiceLocation', foreign_keys=[location_id], backref='movements')
    target_location = db.relationship('ServiceLocation', foreign_keys=[target_location_id])
    goods_item = db.relationship('GoodsItem', backref='movements')
    spare_part = db.relationship('SparePart', backref='movements')
    user = db.relationship('TenantUser', backref='stock_movements')

    # DB Constraints
    __table_args__ = (
        # Mora biti ili goods_item_id ili spare_part_id
        db.CheckConstraint(
            '(goods_item_id IS NOT NULL AND spare_part_id IS NULL) OR '
            '(goods_item_id IS NULL AND spare_part_id IS NOT NULL)',
            name='ck_movement_one_item'
        ),
        # quantity != 0
        db.CheckConstraint('quantity != 0', name='ck_movement_quantity_nonzero'),
        # balance_after >= 0 (ne može u minus)
        db.CheckConstraint('balance_after >= 0', name='ck_movement_balance_positive'),
        # Indeksi za brze upite
        db.Index('ix_movement_location_created', 'location_id', 'created_at'),
        db.Index('ix_movement_goods_created', 'goods_item_id', 'created_at'),
        db.Index('ix_movement_spare_created', 'spare_part_id', 'created_at'),
        db.Index('ix_movement_reference', 'reference_type', 'reference_id'),
    )

    def __repr__(self):
        item = f"goods:{self.goods_item_id}" if self.goods_item_id else f"part:{self.spare_part_id}"
        return f'<StockMovement {self.id}: {self.movement_type.value} {self.quantity:+d} {item}>'

    def to_dict(self):
        return {
            'id': self.id,
            'location_id': self.location_id,
            'movement_type': self.movement_type.value,
            'quantity': self.quantity,
            'balance_before': self.balance_before,
            'balance_after': self.balance_after,
            'unit_cost': float(self.unit_cost) if self.unit_cost else None,
            'unit_price': float(self.unit_price) if self.unit_price else None,
            'reference_type': self.reference_type,
            'reference_id': self.reference_id,
            'reference_number': self.reference_number,
            'reason': self.reason,
            'notes': self.notes,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ============================================
# HELPER FUNKCIJE ZA KREIRANJE MOVEMENT-A
# ============================================

def create_stock_movement(
    tenant_id: int,
    location_id: int,
    user_id: int,
    movement_type: MovementType,
    quantity: int,
    goods_item_id: int = None,
    spare_part_id: int = None,
    unit_cost: Decimal = None,
    unit_price: Decimal = None,
    reference_type: str = None,
    reference_id: int = None,
    reference_number: str = None,
    reason: str = None,
    notes: str = None,
    target_location_id: int = None,
) -> StockMovement:
    """
    Kreira StockMovement i ažurira cache u LocationStock.

    MORA se koristiti unutar transakcije!

    Args:
        tenant_id: ID tenanta
        location_id: ID lokacije (OBAVEZNO)
        user_id: ID korisnika koji radi akciju
        movement_type: Tip promene (RECEIVE, SALE, etc.)
        quantity: Količina (+ za ulaz, - za izlaz)
        goods_item_id: ID robe (XOR spare_part_id)
        spare_part_id: ID dela (XOR goods_item_id)
        unit_cost: Nabavna cena
        unit_price: Prodajna cena
        reference_type: Tip dokumenta
        reference_id: ID dokumenta
        reference_number: Broj dokumenta (za prikaz)
        reason: Razlog (obavezno za ADJUST, DAMAGE, INITIAL_BALANCE)
        notes: Dodatne napomene
        target_location_id: Odredišna lokacija (za TRANSFER)

    Returns:
        Kreirani StockMovement

    Raises:
        ValueError: Ako nema dovoljno stanja za izlaz
    """

    # Validacija
    if not location_id:
        raise ValueError("location_id je obavezan")
    if not goods_item_id and not spare_part_id:
        raise ValueError("Mora biti goods_item_id ili spare_part_id")
    if goods_item_id and spare_part_id:
        raise ValueError("Ne može biti oba: goods_item_id i spare_part_id")
    if movement_type in (MovementType.ADJUST, MovementType.DAMAGE, MovementType.INITIAL_BALANCE) and not reason:
        raise ValueError(f"{movement_type.value} zahteva reason")

    # Dohvati ili kreiraj LocationStock sa LOCK-om
    if goods_item_id:
        loc_stock = db.session.query(LocationStock).with_for_update().filter_by(
            location_id=location_id,
            goods_item_id=goods_item_id
        ).first()
        if not loc_stock:
            loc_stock = LocationStock(
                location_id=location_id,
                goods_item_id=goods_item_id,
                quantity=0
            )
            db.session.add(loc_stock)
            db.session.flush()
    else:
        loc_stock = db.session.query(LocationStock).with_for_update().filter_by(
            location_id=location_id,
            spare_part_id=spare_part_id
        ).first()
        if not loc_stock:
            loc_stock = LocationStock(
                location_id=location_id,
                spare_part_id=spare_part_id,
                quantity=0
            )
            db.session.add(loc_stock)
            db.session.flush()

    balance_before = loc_stock.quantity
    balance_after = balance_before + quantity

    # Validacija: ne može u minus
    if balance_after < 0:
        raise ValueError(
            f"Nedovoljno stanja na lokaciji: {balance_before} + ({quantity}) = {balance_after}"
        )

    # Kreiraj movement
    movement = StockMovement(
        tenant_id=tenant_id,
        location_id=location_id,
        target_location_id=target_location_id,
        goods_item_id=goods_item_id,
        spare_part_id=spare_part_id,
        movement_type=movement_type,
        quantity=quantity,
        balance_before=balance_before,
        balance_after=balance_after,
        unit_cost=unit_cost,
        unit_price=unit_price,
        reference_type=reference_type,
        reference_id=reference_id,
        reference_number=reference_number,
        user_id=user_id,
        reason=reason,
        notes=notes,
    )
    db.session.add(movement)
    db.session.flush()

    # Ažuriraj cache u LocationStock
    loc_stock.quantity = balance_after
    loc_stock.last_movement_id = movement.id

    return movement


def get_stock_card(
    goods_item_id: int = None,
    spare_part_id: int = None,
    location_id: int = None,
    from_date: datetime = None,
    to_date: datetime = None,
    limit: int = 100
) -> list:
    """
    Vraća lager karticu (stock card) za artikal.

    Prikazuje sve promene sa running balance.
    """
    query = StockMovement.query

    if goods_item_id:
        query = query.filter(StockMovement.goods_item_id == goods_item_id)
    elif spare_part_id:
        query = query.filter(StockMovement.spare_part_id == spare_part_id)
    else:
        raise ValueError("Mora biti goods_item_id ili spare_part_id")

    if location_id:
        query = query.filter(StockMovement.location_id == location_id)

    if from_date:
        query = query.filter(StockMovement.created_at >= from_date)
    if to_date:
        query = query.filter(StockMovement.created_at <= to_date)

    return query.order_by(StockMovement.created_at.desc()).limit(limit).all()


def get_stock_by_location(
    goods_item_id: int = None,
    spare_part_id: int = None
) -> list:
    """
    Vraća stanje artikla po svim lokacijama.

    Returns:
        Lista dict-ova sa location_id, location_name, quantity
    """
    query = LocationStock.query

    if goods_item_id:
        query = query.filter(LocationStock.goods_item_id == goods_item_id)
    elif spare_part_id:
        query = query.filter(LocationStock.spare_part_id == spare_part_id)
    else:
        raise ValueError("Mora biti goods_item_id ili spare_part_id")

    stocks = query.filter(LocationStock.quantity > 0).all()
    return [{
        'location_id': s.location_id,
        'location_name': s.location.name if s.location else None,
        'quantity': s.quantity,
    } for s in stocks]


def get_total_stock(
    goods_item_id: int = None,
    spare_part_id: int = None
) -> int:
    """
    Vraća ukupno stanje artikla na svim lokacijama.
    """
    from sqlalchemy import func

    query = db.session.query(func.sum(LocationStock.quantity))

    if goods_item_id:
        query = query.filter(LocationStock.goods_item_id == goods_item_id)
    elif spare_part_id:
        query = query.filter(LocationStock.spare_part_id == spare_part_id)
    else:
        raise ValueError("Mora biti goods_item_id ili spare_part_id")

    result = query.scalar()
    return result or 0


def validate_stock_balance(
    goods_item_id: int = None,
    spare_part_id: int = None,
    location_id: int = None
) -> bool:
    """
    Validira da cache u LocationStock odgovara poslednjoj vrednosti iz ledger-a.

    Returns:
        True ako je validno, False ako ima razlike
    """
    if goods_item_id:
        loc_stock = LocationStock.query.filter_by(
            location_id=location_id,
            goods_item_id=goods_item_id
        ).first()
        if not loc_stock:
            return True  # Nema zapisa = OK

        last = StockMovement.query.filter(
            StockMovement.goods_item_id == goods_item_id,
            StockMovement.location_id == location_id
        ).order_by(StockMovement.created_at.desc()).first()

        expected = last.balance_after if last else 0
        return loc_stock.quantity == expected

    elif spare_part_id:
        loc_stock = LocationStock.query.filter_by(
            location_id=location_id,
            spare_part_id=spare_part_id
        ).first()
        if not loc_stock:
            return True

        last = StockMovement.query.filter(
            StockMovement.spare_part_id == spare_part_id,
            StockMovement.location_id == location_id
        ).order_by(StockMovement.created_at.desc()).first()

        expected = last.balance_after if last else 0
        return loc_stock.quantity == expected

    return False
