"""
POS Service - biznis logika za kasu.

Operacije: otvaranje/zatvaranje kase, kreiranje/izdavanje/storno/refund računa,
dodavanje/brisanje stavki, dnevni izveštaji.
"""

import re
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import text, func
from ..extensions import db
from ..models.pos import (
    CashRegisterSession, Receipt, ReceiptItem, DailyReport,
    PaymentMethod, ReceiptStatus, ReceiptType, CashRegisterStatus, SaleItemType
)
from ..models.inventory import PhoneListing, SparePart
from ..models.service import ServiceItem
from ..models.ticket import ServiceTicket
from ..models.tenant import ServiceLocation
from ..models.audit import AuditLog, AuditAction
from ..models.goods import GoodsItem, PosAuditLog
from ..models.user import TenantUser, PosRole


class POSService:
    """Static metode za POS operacije."""

    @staticmethod
    def get_or_create_session(tenant_id, location_id, user_id):
        """Vrati današnju sesiju ili je kreiraj. Kasa je uvek otvorena."""
        today = date.today()

        session = CashRegisterSession.query.filter_by(
            tenant_id=tenant_id,
            location_id=location_id,
            date=today
        ).first()

        if session:
            return session

        # Kreiraj novu za danas
        location = ServiceLocation.query.get(location_id)
        fiscal = bool(location and location.fiscal_mode)

        session = CashRegisterSession(
            tenant_id=tenant_id,
            location_id=location_id,
            date=today,
            opened_by_id=user_id,
            opened_at=datetime.utcnow(),
            opening_cash=Decimal('0'),
            status=CashRegisterStatus.OPEN,
            fiscal_mode=fiscal,
        )
        db.session.add(session)
        db.session.flush()

        AuditLog.log(
            entity_type='cash_register_session',
            entity_id=session.id,
            action=AuditAction.CREATE,
            changes={'action': 'REGISTER_OPEN'},
            tenant_id=tenant_id,
            user_id=user_id,
        )

        return session

    @staticmethod
    def quick_issue(tenant_id, location_id, user_id, items, payment_method,
                    cash_received=None, card_amount=None, transfer_amount=None,
                    buyer_pib=None, buyer_name=None, discount_pct=None,
                    idempotency_key=None):
        """Atomic: kreira receipt + dodaje stavke + izdaje — sve u jednom koraku.

        Args:
            items: [{type, id, quantity, unit_price?, discount_pct?, item_name?}]
            payment_method: 'CASH', 'CARD', 'TRANSFER', 'MIXED'
        Returns:
            Receipt (ISSUED)
        """
        if buyer_pib and not re.match(r'^\d{9}$', str(buyer_pib)):
            raise ValueError('PIB mora imati tačno 9 cifara')

        if idempotency_key:
            existing = Receipt.query.filter_by(idempotency_key=idempotency_key).first()
            if existing:
                return existing

        if not items:
            raise ValueError('Račun mora imati stavke')

        session = POSService.get_or_create_session(tenant_id, location_id, user_id)

        # Kreiraj receipt number
        today_str = date.today().strftime('%Y%m%d')
        count = Receipt.query.filter(
            Receipt.tenant_id == tenant_id,
            Receipt.receipt_number.like(f'{today_str}-%')
        ).count()
        receipt_number = f'{today_str}-{count + 1:03d}'

        receipt = Receipt(
            tenant_id=tenant_id,
            session_id=session.id,
            receipt_number=receipt_number,
            receipt_type=ReceiptType.SALE,
            status=ReceiptStatus.ISSUED,
            issued_by_id=user_id,
            issued_at=datetime.utcnow(),
            payment_method=PaymentMethod(payment_method) if isinstance(payment_method, str) else payment_method,
        )
        if idempotency_key:
            receipt.idempotency_key = idempotency_key
        if buyer_pib:
            receipt.buyer_pib = buyer_pib
        if buyer_name:
            receipt.buyer_name = buyer_name

        db.session.add(receipt)
        db.session.flush()

        # Dodaj stavke
        for item_data in items:
            item_type = item_data.get('type', 'CUSTOM')
            item_id = item_data.get('id')
            quantity = item_data.get('quantity', 1)
            item_discount = Decimal(str(item_data.get('discount_pct', 0)))
            purchase_price = Decimal('0')
            unit_price = Decimal('0')
            item_name = item_data.get('item_name', '')

            item_type_enum = SaleItemType(item_type) if isinstance(item_type, str) else item_type

            if item_type_enum == SaleItemType.GOODS and item_id:
                from ..services.goods_service import GoodsService
                goods = GoodsItem.query.get(item_id)
                if not goods:
                    raise ValueError(f'Artikl {item_id} nije pronađen')
                GoodsService.safe_deduct_goods_stock(item_id, quantity)
                purchase_price = Decimal(str(goods.purchase_price or 0))
                unit_price = Decimal(str(item_data.get('unit_price') or goods.selling_price or 0))
                item_name = item_name or goods.name

            elif item_type_enum == SaleItemType.SPARE_PART and item_id:
                part = SparePart.query.get(item_id)
                if not part:
                    raise ValueError(f'Deo {item_id} nije pronađen')
                POSService.safe_deduct_stock(item_id, quantity)
                purchase_price = Decimal(str(part.purchase_price or 0))
                unit_price = Decimal(str(item_data.get('unit_price') or part.selling_price or 0))
                item_name = item_name or part.part_name

            elif item_type_enum == SaleItemType.PHONE and item_id:
                phone = PhoneListing.query.get(item_id)
                if not phone:
                    raise ValueError(f'Telefon {item_id} nije pronađen')
                purchase_price = Decimal(str(phone.purchase_price or 0))
                unit_price = Decimal(str(item_data.get('unit_price') or phone.sales_price or 0))
                item_name = item_name or f'{phone.brand} {phone.model}'
                phone.sold = True

            elif item_type_enum == SaleItemType.SERVICE and item_id:
                service = ServiceItem.query.get(item_id)
                if not service:
                    raise ValueError(f'Usluga {item_id} nije pronađena')
                unit_price = Decimal(str(item_data.get('unit_price') or service.price or 0))
                item_name = item_name or service.name

            elif item_type_enum == SaleItemType.CUSTOM:
                purchase_price = Decimal(str(item_data.get('purchase_price') or 0))
                unit_price = Decimal(str(item_data.get('unit_price') or 0))
                item_name = item_name or 'Stavka'

            line_total = Decimal(str(quantity)) * unit_price * (Decimal('1') - item_discount / Decimal('100'))
            line_cost = Decimal(str(quantity)) * purchase_price
            line_profit = line_total - line_cost

            ri = ReceiptItem(
                receipt_id=receipt.id,
                item_type=item_type_enum,
                item_name=item_name,
                quantity=quantity,
                phone_listing_id=item_id if item_type_enum == SaleItemType.PHONE else None,
                spare_part_id=item_id if item_type_enum == SaleItemType.SPARE_PART else None,
                service_item_id=item_id if item_type_enum == SaleItemType.SERVICE else None,
                goods_item_id=item_id if item_type_enum == SaleItemType.GOODS else None,
                purchase_price=purchase_price,
                unit_price=unit_price,
                discount_pct=item_discount,
                line_total=line_total,
                line_cost=line_cost,
                line_profit=line_profit,
            )
            db.session.add(ri)

        # Rekalkulacija totala
        db.session.flush()
        POSService._recalculate_receipt(receipt)

        # Popust na ceo račun
        if discount_pct and Decimal(str(discount_pct)) > 0:
            disc = Decimal(str(discount_pct))
            receipt.discount_amount = receipt.subtotal * disc / Decimal('100')
            receipt.total_amount = receipt.subtotal - receipt.discount_amount
            receipt.profit = receipt.total_amount - receipt.total_cost

        # Plaćanje
        if cash_received is not None:
            receipt.cash_received = Decimal(str(cash_received))
            receipt.cash_change = max(receipt.cash_received - receipt.total_amount, Decimal('0'))
        if card_amount is not None:
            receipt.card_amount = Decimal(str(card_amount))
        if transfer_amount is not None:
            receipt.transfer_amount = Decimal(str(transfer_amount))

        # Fiscal mode
        if session.fiscal_mode:
            receipt.fiscal_status = 'pending'

        AuditLog.log(
            entity_type='receipt',
            entity_id=receipt.id,
            action=AuditAction.CREATE,
            changes={'action': 'QUICK_ISSUE', 'total': float(receipt.total_amount), 'items': len(items)},
            tenant_id=tenant_id,
            user_id=user_id,
        )

        db.session.flush()
        return receipt

    @staticmethod
    def generate_daily_report(session_id, user_id=None):
        """Generiši DailyReport za sesiju (ručni Z izveštaj). Sesija ostaje OPEN."""
        session = CashRegisterSession.query.get(session_id)
        if not session:
            raise ValueError('Sesija nije pronađena')

        # Ako već postoji report, ažuriraj ga
        existing_report = DailyReport.query.filter_by(
            tenant_id=session.tenant_id,
            location_id=session.location_id,
            date=session.date,
        ).first()

        receipts = Receipt.query.filter_by(
            session_id=session_id,
            status=ReceiptStatus.ISSUED
        ).all()

        total_revenue = sum(r.total_amount or 0 for r in receipts)
        total_cost = sum(r.total_cost or 0 for r in receipts)
        total_profit = sum(r.profit or 0 for r in receipts)
        total_cash = sum(r.cash_received - (r.cash_change or 0) for r in receipts if r.payment_method == PaymentMethod.CASH and r.cash_received)
        total_card = sum(r.card_amount or 0 for r in receipts if r.card_amount)
        total_transfer = sum(r.transfer_amount or 0 for r in receipts if r.transfer_amount)
        receipt_count = len(receipts)
        voided_count = Receipt.query.filter_by(session_id=session_id, status=ReceiptStatus.VOIDED).count()

        items_query = db.session.query(
            func.sum(ReceiptItem.quantity).label('total'),
            func.sum(db.case((ReceiptItem.item_type == SaleItemType.PHONE, ReceiptItem.quantity), else_=0)).label('phones'),
            func.sum(db.case((ReceiptItem.item_type == SaleItemType.SPARE_PART, ReceiptItem.quantity), else_=0)).label('parts'),
            func.sum(db.case((ReceiptItem.item_type == SaleItemType.SERVICE, ReceiptItem.quantity), else_=0)).label('services'),
        ).join(Receipt).filter(
            Receipt.session_id == session_id,
            Receipt.status == ReceiptStatus.ISSUED
        ).first()

        profit_margin = (float(total_profit) / float(total_revenue) * 100) if total_revenue else 0

        report_data = dict(
            total_revenue=total_revenue,
            total_cost=total_cost,
            total_profit=total_profit,
            profit_margin_pct=Decimal(str(round(profit_margin, 2))),
            total_cash=total_cash,
            total_card=total_card,
            total_transfer=total_transfer,
            opening_cash=session.opening_cash,
            closing_cash=total_cash,
            cash_difference=Decimal('0'),
            receipt_count=receipt_count,
            voided_count=voided_count,
            items_sold=items_query.total or 0 if items_query else 0,
            phones_sold=items_query.phones or 0 if items_query else 0,
            parts_sold=items_query.parts or 0 if items_query else 0,
            services_sold=items_query.services or 0 if items_query else 0,
        )

        if existing_report:
            for k, v in report_data.items():
                setattr(existing_report, k, v)
            report = existing_report
        else:
            report = DailyReport(
                tenant_id=session.tenant_id,
                location_id=session.location_id,
                session_id=session_id,
                date=session.date,
                **report_data,
            )
            db.session.add(report)

        # Ažuriraj session totale
        session.total_revenue = total_revenue
        session.total_cost = total_cost
        session.total_profit = total_profit
        session.total_cash = total_cash
        session.total_card = total_card
        session.total_transfer = total_transfer
        session.receipt_count = receipt_count
        session.voided_count = voided_count

        db.session.flush()
        return report

    @staticmethod
    def auto_daily_close():
        """Zatvori sve otvorene sesije za danas i generiši Z izveštaje.
        Poziva se iz schedulera u 23:59."""
        today = date.today()
        open_sessions = CashRegisterSession.query.filter_by(
            date=today,
            status=CashRegisterStatus.OPEN
        ).all()

        closed = []
        for session in open_sessions:
            # Generiši/ažuriraj DailyReport
            POSService.generate_daily_report(session.id)

            # Zatvori sesiju
            session.closed_at = datetime.utcnow()
            session.status = CashRegisterStatus.CLOSED

            AuditLog.log(
                entity_type='cash_register_session',
                entity_id=session.id,
                action=AuditAction.UPDATE,
                changes={'action': 'AUTO_DAILY_CLOSE'},
                tenant_id=session.tenant_id,
                user_id=session.opened_by_id,
            )
            closed.append(session.id)

        db.session.flush()
        return closed

    @staticmethod
    def create_receipt(session_id, user_id):
        """Kreiraj prazan DRAFT račun."""
        session = CashRegisterSession.query.get(session_id)
        if not session or session.status != CashRegisterStatus.OPEN:
            raise ValueError('Kasa nije otvorena')

        # Auto-increment receipt number: YYYYMMDD-NNN
        today_str = date.today().strftime('%Y%m%d')
        count = Receipt.query.filter(
            Receipt.tenant_id == session.tenant_id,
            Receipt.receipt_number.like(f'{today_str}-%')
        ).count()
        receipt_number = f'{today_str}-{count + 1:03d}'

        receipt = Receipt(
            tenant_id=session.tenant_id,
            session_id=session_id,
            receipt_number=receipt_number,
            receipt_type=ReceiptType.SALE,
            status=ReceiptStatus.DRAFT,
            issued_by_id=user_id,
        )
        db.session.add(receipt)
        db.session.flush()
        return receipt

    @staticmethod
    def add_item_to_receipt(receipt_id, item_type, item_id=None, **kwargs):
        """Dodaj stavku na račun."""
        receipt = Receipt.query.get(receipt_id)
        if not receipt or receipt.status != ReceiptStatus.DRAFT:
            raise ValueError('Račun nije u DRAFT statusu')

        item_type_enum = SaleItemType(item_type) if isinstance(item_type, str) else item_type
        quantity = kwargs.get('quantity', 1)
        purchase_price = Decimal('0')
        unit_price = Decimal('0')
        item_name = kwargs.get('item_name', '')

        if item_type_enum == SaleItemType.PHONE and item_id:
            phone = PhoneListing.query.get(item_id)
            if not phone:
                raise ValueError('Telefon nije pronađen')
            purchase_price = Decimal(str(phone.purchase_price or 0))
            unit_price = Decimal(str(kwargs.get('unit_price') or phone.sales_price or 0))
            item_name = item_name or f'{phone.brand} {phone.model}'

        elif item_type_enum == SaleItemType.SPARE_PART and item_id:
            part = SparePart.query.get(item_id)
            if not part:
                raise ValueError('Deo nije pronađen')
            POSService.safe_deduct_stock(item_id, quantity)
            purchase_price = Decimal(str(part.purchase_price or 0))
            unit_price = Decimal(str(kwargs.get('unit_price') or part.selling_price or 0))
            item_name = item_name or part.part_name

        elif item_type_enum == SaleItemType.SERVICE and item_id:
            service = ServiceItem.query.get(item_id)
            if not service:
                raise ValueError('Usluga nije pronađena')
            purchase_price = Decimal('0')
            unit_price = Decimal(str(kwargs.get('unit_price') or service.price or 0))
            item_name = item_name or service.name

        elif item_type_enum == SaleItemType.TICKET and item_id:
            ticket = ServiceTicket.query.get(item_id)
            if not ticket:
                raise ValueError('Nalog nije pronađen')
            purchase_price = Decimal(str(ticket.parts_cost or 0))
            unit_price = Decimal(str(kwargs.get('unit_price') or ticket.final_price or 0))
            item_name = item_name or f'Servis #{ticket.ticket_number}'

        elif item_type_enum == SaleItemType.GOODS and item_id:
            from ..services.goods_service import GoodsService
            goods = GoodsItem.query.get(item_id)
            if not goods:
                raise ValueError('Artikl nije pronađen')
            GoodsService.safe_deduct_goods_stock(item_id, quantity)
            purchase_price = Decimal(str(goods.purchase_price or 0))
            unit_price = Decimal(str(kwargs.get('unit_price') or goods.selling_price or 0))
            item_name = item_name or goods.name

        elif item_type_enum == SaleItemType.CUSTOM:
            purchase_price = Decimal(str(kwargs.get('purchase_price') or 0))
            unit_price = Decimal(str(kwargs.get('unit_price') or 0))
            item_name = item_name or 'Stavka'

        discount_pct = Decimal(str(kwargs.get('discount_pct', 0)))
        line_total = Decimal(str(quantity)) * unit_price * (Decimal('1') - discount_pct / Decimal('100'))
        line_cost = Decimal(str(quantity)) * purchase_price
        line_profit = line_total - line_cost

        item = ReceiptItem(
            receipt_id=receipt_id,
            item_type=item_type_enum,
            item_name=item_name,
            quantity=quantity,
            phone_listing_id=item_id if item_type_enum == SaleItemType.PHONE else None,
            spare_part_id=item_id if item_type_enum == SaleItemType.SPARE_PART else None,
            service_item_id=item_id if item_type_enum == SaleItemType.SERVICE else None,
            service_ticket_id=item_id if item_type_enum == SaleItemType.TICKET else None,
            goods_item_id=item_id if item_type_enum == SaleItemType.GOODS else None,
            purchase_price=purchase_price,
            unit_price=unit_price,
            discount_pct=discount_pct,
            line_total=line_total,
            line_cost=line_cost,
            line_profit=line_profit,
        )
        db.session.add(item)
        POSService._recalculate_receipt(receipt)
        db.session.flush()
        return item

    @staticmethod
    def remove_item_from_receipt(item_id):
        """Ukloni stavku sa DRAFT računa."""
        item = ReceiptItem.query.get(item_id)
        if not item:
            raise ValueError('Stavka nije pronađena')

        receipt = Receipt.query.get(item.receipt_id)
        if not receipt or receipt.status != ReceiptStatus.DRAFT:
            raise ValueError('Račun nije u DRAFT statusu')

        # Vrati zalihu
        if item.item_type == SaleItemType.SPARE_PART and item.spare_part_id:
            POSService._restore_stock(item.spare_part_id, item.quantity)
        elif item.item_type == SaleItemType.GOODS and item.goods_item_id:
            from ..services.goods_service import GoodsService
            GoodsService.restore_goods_stock(item.goods_item_id, item.quantity)

        db.session.delete(item)
        POSService._recalculate_receipt(receipt)
        db.session.flush()

    @staticmethod
    def issue_receipt(receipt_id, payment_method, cash_received=None, card_amount=None,
                      transfer_amount=None, idempotency_key=None, buyer_pib=None, buyer_name=None):
        """Izdaj račun sa idempotency podrškom."""
        # PIB validacija (srpski PIB = tačno 9 cifara)
        if buyer_pib and not re.match(r'^\d{9}$', str(buyer_pib)):
            raise ValueError('PIB mora imati tačno 9 cifara')

        # Idempotency check
        if idempotency_key:
            existing = Receipt.query.filter_by(idempotency_key=idempotency_key).first()
            if existing:
                return existing

        receipt = Receipt.query.get(receipt_id)
        if not receipt or receipt.status != ReceiptStatus.DRAFT:
            raise ValueError('Račun nije u DRAFT statusu')

        # Provera da je kasa otvorena
        session = CashRegisterSession.query.get(receipt.session_id)
        if session and session.status != CashRegisterStatus.OPEN:
            raise ValueError('Kasa je zatvorena — nije moguće izdati račun')

        items = ReceiptItem.query.filter_by(receipt_id=receipt_id).all()
        if not items:
            raise ValueError('Račun nema stavki')

        receipt.payment_method = PaymentMethod(payment_method) if isinstance(payment_method, str) else payment_method
        receipt.status = ReceiptStatus.ISSUED
        receipt.issued_at = datetime.utcnow()
        if idempotency_key:
            receipt.idempotency_key = idempotency_key
        if buyer_pib:
            receipt.buyer_pib = buyer_pib
        if buyer_name:
            receipt.buyer_name = buyer_name

        # Fiscal mode
        session = CashRegisterSession.query.get(receipt.session_id)
        if session and session.fiscal_mode:
            receipt.fiscal_status = 'pending'

        if cash_received is not None:
            receipt.cash_received = Decimal(str(cash_received))
            receipt.cash_change = receipt.cash_received - receipt.total_amount
        if card_amount is not None:
            receipt.card_amount = Decimal(str(card_amount))
        if transfer_amount is not None:
            receipt.transfer_amount = Decimal(str(transfer_amount))

        # Označi telefone kao prodane
        for item in items:
            if item.item_type == SaleItemType.PHONE and item.phone_listing_id:
                phone = PhoneListing.query.get(item.phone_listing_id)
                if phone:
                    phone.sold = True

        AuditLog.log(
            entity_type='receipt',
            entity_id=receipt.id,
            action=AuditAction.UPDATE,
            changes={'action': 'RECEIPT_ISSUED', 'total': float(receipt.total_amount)},
            tenant_id=receipt.tenant_id,
            user_id=receipt.issued_by_id,
        )

        db.session.flush()
        return receipt

    @staticmethod
    def _check_pos_permission(user_id, required_role=PosRole.MANAGER):
        """Proveri da li korisnik ima dovoljnu POS rolu.

        Ako pos_role nije eksplicitno postavljen (None), dozvoli operaciju
        za backwards kompatibilnost.
        """
        user = TenantUser.query.get(user_id)
        if user and user.pos_role is not None and user.pos_role == PosRole.CASHIER and required_role != PosRole.CASHIER:
            raise ValueError('Nemate dozvolu za ovu operaciju')

    @staticmethod
    def void_receipt(receipt_id, user_id, reason):
        """Storniraj izdati račun."""
        POSService._check_pos_permission(user_id, PosRole.MANAGER)
        receipt = Receipt.query.get(receipt_id)
        if not receipt or receipt.status != ReceiptStatus.ISSUED:
            raise ValueError('Samo izdati računi se mogu stornirati')

        items = ReceiptItem.query.filter_by(receipt_id=receipt_id).all()
        for item in items:
            if item.item_type == SaleItemType.SPARE_PART and item.spare_part_id:
                POSService._restore_stock(item.spare_part_id, item.quantity)
            elif item.item_type == SaleItemType.GOODS and item.goods_item_id:
                from ..services.goods_service import GoodsService
                GoodsService.restore_goods_stock(item.goods_item_id, item.quantity)
            if item.item_type == SaleItemType.PHONE and item.phone_listing_id:
                phone = PhoneListing.query.get(item.phone_listing_id)
                if phone:
                    phone.sold = False

        receipt.status = ReceiptStatus.VOIDED
        receipt.voided_by_id = user_id
        receipt.voided_at = datetime.utcnow()
        receipt.void_reason = reason

        AuditLog.log(
            entity_type='receipt',
            entity_id=receipt.id,
            action=AuditAction.UPDATE,
            changes={'action': 'RECEIPT_VOIDED', 'reason': reason},
            tenant_id=receipt.tenant_id,
            user_id=user_id,
        )

        db.session.flush()
        return receipt

    @staticmethod
    def refund_receipt(original_receipt_id, user_id, items_to_refund=None):
        """Kreiraj refund račun."""
        POSService._check_pos_permission(user_id, PosRole.MANAGER)
        original = Receipt.query.get(original_receipt_id)
        if not original or original.status != ReceiptStatus.ISSUED:
            raise ValueError('Original račun nije validan za refund')

        # Kreiraj refund receipt
        today_str = date.today().strftime('%Y%m%d')
        count = Receipt.query.filter(
            Receipt.tenant_id == original.tenant_id,
            Receipt.receipt_number.like(f'{today_str}-%')
        ).count()
        refund_number = f'{today_str}-{count + 1:03d}'

        refund = Receipt(
            tenant_id=original.tenant_id,
            session_id=original.session_id,
            receipt_number=refund_number,
            receipt_type=ReceiptType.REFUND,
            original_receipt_id=original_receipt_id,
            status=ReceiptStatus.ISSUED,
            issued_by_id=user_id,
            issued_at=datetime.utcnow(),
            payment_method=original.payment_method,
        )
        db.session.add(refund)
        db.session.flush()

        # Kopiraj stavke sa negativnim quantity
        original_items = ReceiptItem.query.filter_by(receipt_id=original_receipt_id).all()
        for orig_item in original_items:
            qty = orig_item.quantity
            if items_to_refund:
                match = next((i for i in items_to_refund if i.get('item_id') == orig_item.id), None)
                if not match:
                    continue
                qty = match.get('quantity', orig_item.quantity)

            refund_item = ReceiptItem(
                receipt_id=refund.id,
                item_type=orig_item.item_type,
                item_name=orig_item.item_name,
                quantity=-qty,
                phone_listing_id=orig_item.phone_listing_id,
                spare_part_id=orig_item.spare_part_id,
                service_item_id=orig_item.service_item_id,
                service_ticket_id=orig_item.service_ticket_id,
                purchase_price=orig_item.purchase_price,
                unit_price=orig_item.unit_price,
                discount_pct=orig_item.discount_pct,
                line_total=-orig_item.line_total * qty / orig_item.quantity,
                line_cost=-orig_item.line_cost * qty / orig_item.quantity,
                line_profit=-orig_item.line_profit * qty / orig_item.quantity,
            )
            db.session.add(refund_item)

            # Vrati zalihe
            if orig_item.item_type == SaleItemType.SPARE_PART and orig_item.spare_part_id:
                POSService._restore_stock(orig_item.spare_part_id, qty)
            elif orig_item.item_type == SaleItemType.GOODS and orig_item.goods_item_id:
                from ..services.goods_service import GoodsService
                GoodsService.restore_goods_stock(orig_item.goods_item_id, qty)
            if orig_item.item_type == SaleItemType.PHONE and orig_item.phone_listing_id:
                phone = PhoneListing.query.get(orig_item.phone_listing_id)
                if phone:
                    phone.sold = False

        POSService._recalculate_receipt(refund)

        original.status = ReceiptStatus.REFUNDED

        AuditLog.log(
            entity_type='receipt',
            entity_id=refund.id,
            action=AuditAction.CREATE,
            changes={'action': 'RECEIPT_REFUNDED', 'original_id': original_receipt_id},
            tenant_id=original.tenant_id,
            user_id=user_id,
        )

        db.session.flush()
        return refund

    @staticmethod
    def create_service_receipt(ticket, payment_method, user_id, location_id):
        """Kreiraj automatski račun za servisni nalog pri preuzimanju.

        Args:
            ticket: ServiceTicket objekat (mora imati final_price)
            payment_method: 'CASH', 'CARD', 'TRANSFER'
            user_id: ID korisnika koji izdaje
            location_id: ID lokacije

        Returns:
            Receipt objekat (ISSUED)
        """
        # Idempotency — sprečava duplo izdavanje za isti ticket
        idempotency_key = f'ticket-deliver-{ticket.id}'
        existing = Receipt.query.filter_by(idempotency_key=idempotency_key).first()
        if existing:
            return existing

        tenant_id = ticket.tenant_id

        # Koristi get_or_create_session za automatsko kreiranje
        session = POSService.get_or_create_session(tenant_id, location_id, user_id)

        # Kreiraj receipt number
        today_str = date.today().strftime('%Y%m%d')
        count = Receipt.query.filter(
            Receipt.tenant_id == tenant_id,
            Receipt.receipt_number.like(f'{today_str}-%')
        ).count()
        receipt_number = f'{today_str}-{count + 1:03d}'

        # Cene
        final_price = Decimal(str(ticket.final_price or 0))
        parts_cost = Decimal(str(ticket.parts_cost or 0))
        profit = final_price - parts_cost

        # Opis stavke
        device_info = f'{ticket.brand or ""} {ticket.model or ""}'.strip()
        fault_desc = (ticket.problem_description or 'Servis')[:100]
        item_name = f'Servis: {fault_desc}'
        if device_info:
            item_name += f' — {device_info}'

        receipt = Receipt(
            tenant_id=tenant_id,
            session_id=session.id,
            receipt_number=receipt_number,
            receipt_type=ReceiptType.SALE,
            status=ReceiptStatus.ISSUED,
            issued_by_id=user_id,
            issued_at=datetime.utcnow(),
            payment_method=PaymentMethod(payment_method) if isinstance(payment_method, str) else payment_method,
            subtotal=final_price,
            total_amount=final_price,
            total_cost=parts_cost,
            profit=profit,
            customer_name=ticket.customer_name,
            customer_phone=ticket.customer_phone,
            idempotency_key=idempotency_key,
            service_ticket_id=ticket.id,
        )
        if session.fiscal_mode:
            receipt.fiscal_status = 'pending'

        if payment_method == 'CASH':
            receipt.cash_received = final_price
            receipt.cash_change = Decimal('0')

        db.session.add(receipt)
        db.session.flush()

        # Stavka
        item = ReceiptItem(
            receipt_id=receipt.id,
            item_type=SaleItemType.TICKET,
            item_name=item_name,
            quantity=1,
            service_ticket_id=ticket.id,
            purchase_price=parts_cost,
            unit_price=final_price,
            discount_pct=Decimal('0'),
            line_total=final_price,
            line_cost=parts_cost,
            line_profit=profit,
        )
        db.session.add(item)

        AuditLog.log(
            entity_type='receipt',
            entity_id=receipt.id,
            action=AuditAction.CREATE,
            changes={'action': 'SERVICE_RECEIPT', 'ticket_id': ticket.id, 'total': float(final_price)},
            tenant_id=tenant_id,
            user_id=user_id,
        )

        db.session.flush()
        return receipt

    @staticmethod
    def close_register(session_id, user_id, closing_cash):
        """Zatvori kasu i generiši DailyReport."""
        session = CashRegisterSession.query.get(session_id)
        if not session or session.status != CashRegisterStatus.OPEN:
            raise ValueError('Kasa nije otvorena')

        closing_cash = Decimal(str(closing_cash))

        # Sumiraj sve ISSUED račune
        receipts = Receipt.query.filter_by(
            session_id=session_id,
            status=ReceiptStatus.ISSUED
        ).all()

        total_revenue = sum(r.total_amount or 0 for r in receipts)
        total_cost = sum(r.total_cost or 0 for r in receipts)
        total_profit = sum(r.profit or 0 for r in receipts)
        total_cash = sum(r.cash_received - (r.cash_change or 0) for r in receipts if r.payment_method == PaymentMethod.CASH and r.cash_received)
        total_card = sum(r.card_amount or 0 for r in receipts if r.card_amount)
        total_transfer = sum(r.transfer_amount or 0 for r in receipts if r.transfer_amount)
        receipt_count = len(receipts)
        voided_count = Receipt.query.filter_by(session_id=session_id, status=ReceiptStatus.VOIDED).count()

        expected_cash = session.opening_cash + total_cash
        cash_difference = closing_cash - expected_cash

        # Update session
        session.closed_by_id = user_id
        session.closed_at = datetime.utcnow()
        session.closing_cash = closing_cash
        session.expected_cash = expected_cash
        session.cash_difference = cash_difference
        session.status = CashRegisterStatus.CLOSED
        session.total_revenue = total_revenue
        session.total_cost = total_cost
        session.total_profit = total_profit
        session.total_cash = total_cash
        session.total_card = total_card
        session.total_transfer = total_transfer
        session.receipt_count = receipt_count
        session.voided_count = voided_count

        # Kreiraj DailyReport
        # Prebroj prodane artikle
        items_query = db.session.query(
            func.sum(ReceiptItem.quantity).label('total'),
            func.sum(db.case((ReceiptItem.item_type == SaleItemType.PHONE, ReceiptItem.quantity), else_=0)).label('phones'),
            func.sum(db.case((ReceiptItem.item_type == SaleItemType.SPARE_PART, ReceiptItem.quantity), else_=0)).label('parts'),
            func.sum(db.case((ReceiptItem.item_type == SaleItemType.SERVICE, ReceiptItem.quantity), else_=0)).label('services'),
        ).join(Receipt).filter(
            Receipt.session_id == session_id,
            Receipt.status == ReceiptStatus.ISSUED
        ).first()

        profit_margin = (float(total_profit) / float(total_revenue) * 100) if total_revenue else 0

        report = DailyReport(
            tenant_id=session.tenant_id,
            location_id=session.location_id,
            session_id=session_id,
            date=session.date,
            total_revenue=total_revenue,
            total_cost=total_cost,
            total_profit=total_profit,
            profit_margin_pct=Decimal(str(round(profit_margin, 2))),
            total_cash=total_cash,
            total_card=total_card,
            total_transfer=total_transfer,
            opening_cash=session.opening_cash,
            closing_cash=closing_cash,
            cash_difference=cash_difference,
            receipt_count=receipt_count,
            voided_count=voided_count,
            items_sold=items_query.total or 0 if items_query else 0,
            phones_sold=items_query.phones or 0 if items_query else 0,
            parts_sold=items_query.parts or 0 if items_query else 0,
            services_sold=items_query.services or 0 if items_query else 0,
        )
        db.session.add(report)

        AuditLog.log(
            entity_type='cash_register_session',
            entity_id=session.id,
            action=AuditAction.UPDATE,
            changes={'action': 'REGISTER_CLOSED', 'cash_difference': float(cash_difference)},
            tenant_id=session.tenant_id,
            user_id=user_id,
        )

        db.session.flush()
        return session, report

    # ============================================
    # HELPER METODE
    # ============================================

    @staticmethod
    def safe_deduct_stock(spare_part_id, quantity):
        """Atomično smanjenje zaliha - sprečava race condition."""
        result = db.session.execute(
            text("UPDATE spare_part SET stock_quantity = stock_quantity - :qty "
                 "WHERE id = :id AND stock_quantity >= :qty RETURNING stock_quantity"),
            {'id': spare_part_id, 'qty': quantity}
        )
        row = result.fetchone()
        if not row:
            raise ValueError('Nedovoljno zaliha')
        return row[0]

    @staticmethod
    def _restore_stock(spare_part_id, quantity):
        """Vrati zalihu."""
        db.session.execute(
            text("UPDATE spare_part SET stock_quantity = stock_quantity + :qty WHERE id = :id"),
            {'id': spare_part_id, 'qty': quantity}
        )

    @staticmethod
    def _recalculate_receipt(receipt):
        """Preračunaj totale računa."""
        items = ReceiptItem.query.filter_by(receipt_id=receipt.id).all()
        receipt.subtotal = sum(i.line_total for i in items)
        receipt.total_amount = receipt.subtotal - (receipt.discount_amount or 0)
        receipt.total_cost = sum(i.line_cost for i in items)
        receipt.profit = receipt.total_amount - receipt.total_cost