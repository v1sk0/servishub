"""
Goods Service — biznis logika za magacin i ulazne fakture.

Operacije: CRUD artikala, prijem faktura, kalkulacija marže,
stock ažuriranje, korekcija stanja.
"""

from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import text
from ..extensions import db
from ..models.goods import (
    GoodsItem, PurchaseInvoice, PurchaseInvoiceItem,
    StockAdjustment, PosAuditLog,
    InvoiceStatus, StockAdjustmentType,
    suggest_selling_price
)


class GoodsService:
    """Static metode za magacin operacije."""

    # ============================================
    # ARTIKLI
    # ============================================

    @staticmethod
    def create_goods_item(tenant_id, data, user_id=None):
        """Kreiraj novi artikl robe."""
        barcode = data.get('barcode')
        if barcode:
            barcode = barcode.upper().strip()
        item = GoodsItem(
            tenant_id=tenant_id,
            location_id=data.get('location_id'),
            name=data['name'],
            barcode=barcode,
            sku=data.get('sku'),
            category=data.get('category'),
            description=data.get('description'),
            purchase_price=Decimal(str(data.get('purchase_price', 0))),
            selling_price=Decimal(str(data.get('selling_price', 0))),
            default_margin_pct=Decimal(str(data.get('default_margin_pct', 0))) if data.get('default_margin_pct') else None,
            currency=data.get('currency', 'RSD'),
            current_stock=data.get('current_stock', 0),
            min_stock_level=data.get('min_stock_level', 0),
            tax_label=data.get('tax_label', 'A'),
            unit_of_measure=data.get('unit_of_measure', 'kom'),
        )
        db.session.add(item)
        db.session.flush()
        return item

    @staticmethod
    def update_goods_item(item_id, tenant_id, data):
        """Ažuriraj artikl."""
        item = GoodsItem.query.filter_by(id=item_id, tenant_id=tenant_id).first()
        if not item:
            raise ValueError('Artikl nije pronađen')

        # Normalizuj barcode pre čuvanja
        if 'barcode' in data and data['barcode']:
            data['barcode'] = data['barcode'].upper().strip()

        for field in ['name', 'barcode', 'sku', 'category', 'description',
                      'currency', 'min_stock_level', 'tax_label', 'unit_of_measure', 'is_active']:
            if field in data:
                setattr(item, field, data[field])

        if 'purchase_price' in data:
            item.purchase_price = Decimal(str(data['purchase_price']))
        if 'selling_price' in data:
            item.selling_price = Decimal(str(data['selling_price']))
        if 'default_margin_pct' in data:
            item.default_margin_pct = Decimal(str(data['default_margin_pct'])) if data['default_margin_pct'] else None

        db.session.flush()
        return item

    # ============================================
    # ULAZNE FAKTURE
    # ============================================

    @staticmethod
    def _parse_date(val):
        """Parsiraj datum iz stringa ili vrati date objekat."""
        if val is None:
            return None
        if isinstance(val, date):
            return val
        return date.fromisoformat(str(val))

    @staticmethod
    def create_invoice(tenant_id, data, user_id=None):
        """Kreiraj ulaznu fakturu (DRAFT)."""
        invoice = PurchaseInvoice(
            tenant_id=tenant_id,
            location_id=data.get('location_id'),
            supplier_name=data['supplier_name'],
            supplier_pib=data.get('supplier_pib'),
            invoice_number=data['invoice_number'],
            invoice_date=GoodsService._parse_date(data['invoice_date']),
            received_date=GoodsService._parse_date(data.get('received_date')),
            currency=data.get('currency', 'RSD'),
            notes=data.get('notes'),
            received_by_id=user_id,
            status=InvoiceStatus.DRAFT,
        )
        db.session.add(invoice)
        db.session.flush()
        return invoice

    @staticmethod
    def add_invoice_item(invoice_id, data):
        """Dodaj stavku na fakturu."""
        invoice = PurchaseInvoice.query.get(invoice_id)
        if not invoice or invoice.status != InvoiceStatus.DRAFT:
            raise ValueError('Faktura nije u DRAFT statusu')

        quantity = data.get('quantity', 1)
        purchase_price = Decimal(str(data['purchase_price']))
        selling_price = Decimal(str(data.get('selling_price', 0)))
        line_total = purchase_price * quantity

        # Izračunaj maržu
        margin_pct = None
        if purchase_price > 0 and selling_price > 0:
            margin_pct = float((selling_price - purchase_price) / purchase_price * 100)

        item = PurchaseInvoiceItem(
            invoice_id=invoice_id,
            goods_item_id=data.get('goods_item_id'),
            spare_part_id=data.get('spare_part_id'),
            item_name=data['item_name'],
            quantity=quantity,
            purchase_price=purchase_price,
            selling_price=selling_price,
            margin_pct=Decimal(str(round(margin_pct, 2))) if margin_pct is not None else None,
            line_total=line_total,
        )
        db.session.add(item)

        # Ažuriraj ukupan iznos fakture
        invoice.total_amount = (invoice.total_amount or Decimal('0')) + line_total
        db.session.flush()
        return item

    @staticmethod
    def receive_invoice(invoice_id, tenant_id, user_id=None):
        """
        Primi fakturu — ažuriraj stanje robe/delova.

        Za svaku stavku:
        - Ako ima goods_item_id → ažuriraj GoodsItem stanje i cene
        - Ako ima spare_part_id → ažuriraj SparePart stanje i cene
        """
        invoice = PurchaseInvoice.query.filter_by(
            id=invoice_id, tenant_id=tenant_id
        ).first()
        if not invoice:
            raise ValueError('Faktura nije pronađena')
        if invoice.status != InvoiceStatus.DRAFT:
            raise ValueError('Samo DRAFT faktura se može primiti')

        items = PurchaseInvoiceItem.query.filter_by(invoice_id=invoice_id).all()
        if not items:
            raise ValueError('Faktura nema stavki')

        for item in items:
            if item.goods_item_id:
                goods = GoodsItem.query.get(item.goods_item_id)
                if goods:
                    goods.current_stock += item.quantity
                    goods.purchase_price = item.purchase_price
                    if item.selling_price:
                        goods.selling_price = item.selling_price
                    if item.margin_pct is not None:
                        goods.default_margin_pct = item.margin_pct

            elif item.spare_part_id:
                from ..models.inventory import SparePart
                part = SparePart.query.get(item.spare_part_id)
                if part:
                    part.quantity += item.quantity
                    part.purchase_price = item.purchase_price
                    if item.selling_price:
                        part.selling_price = item.selling_price

        invoice.status = InvoiceStatus.RECEIVED
        invoice.received_date = date.today()
        invoice.received_by_id = user_id

        db.session.flush()
        return invoice

    # ============================================
    # STOCK KOREKCIJA
    # ============================================

    @staticmethod
    def adjust_goods_stock(goods_item_id, tenant_id, quantity_change, adjustment_type, reason, user_id=None):
        """Koriguj stanje artikla (otpis, inventura, oštećenje)."""
        item = GoodsItem.query.filter_by(id=goods_item_id, tenant_id=tenant_id).first()
        if not item:
            raise ValueError('Artikl nije pronađen')

        stock_before = item.current_stock
        new_stock = stock_before + quantity_change
        if new_stock < 0:
            raise ValueError(f'Stanje ne može biti negativno (trenutno: {stock_before}, promena: {quantity_change})')

        item.current_stock = new_stock

        adjustment = StockAdjustment(
            tenant_id=tenant_id,
            goods_item_id=goods_item_id,
            adjustment_type=StockAdjustmentType(adjustment_type) if isinstance(adjustment_type, str) else adjustment_type,
            quantity_change=quantity_change,
            stock_before=stock_before,
            stock_after=new_stock,
            reason=reason,
            adjusted_by_id=user_id,
        )
        db.session.add(adjustment)

        # Audit log
        PosAuditLog.log_action(
            tenant_id=tenant_id,
            user_id=user_id,
            action='STOCK_ADJUST',
            entity_type='goods_item',
            entity_id=goods_item_id,
            details={
                'adjustment_type': adjustment_type if isinstance(adjustment_type, str) else adjustment_type.value,
                'quantity_change': quantity_change,
                'stock_before': stock_before,
                'stock_after': new_stock,
                'reason': reason,
            }
        )

        db.session.flush()
        return adjustment

    # ============================================
    # ATOMIC STOCK DEDUKCIJA (za POS)
    # ============================================

    @staticmethod
    def safe_deduct_goods_stock(goods_item_id, quantity):
        """Atomično smanji stanje robe — sprečava race condition."""
        result = db.session.execute(
            text("UPDATE goods_item SET current_stock = current_stock - :qty "
                 "WHERE id = :id AND current_stock >= :qty RETURNING current_stock"),
            {'id': goods_item_id, 'qty': quantity}
        )
        row = result.fetchone()
        if not row:
            raise ValueError('Nedovoljno robe na stanju')
        return row[0]

    @staticmethod
    def restore_goods_stock(goods_item_id, quantity):
        """Vrati stanje robe (void/refund)."""
        db.session.execute(
            text("UPDATE goods_item SET current_stock = current_stock + :qty WHERE id = :id"),
            {'id': goods_item_id, 'qty': quantity}
        )