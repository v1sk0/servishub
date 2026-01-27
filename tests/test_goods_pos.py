"""
v3.08 testovi — GoodsItem CRUD, POS sa GOODS stavkama, idempotency,
dual-mode (fiskalna/interna kasa), auto-receipt na ticket delivery,
stock korekcije, void/refund stock restore, X/Z izveštaji.
"""
import pytest
import json
from decimal import Decimal
from datetime import date, datetime

from app.extensions import db as _db
from app.models.feature_flag import FeatureFlag
from app.models.goods import (
    GoodsItem, PurchaseInvoice, PurchaseInvoiceItem,
    StockAdjustment, PosAuditLog, InvoiceStatus, suggest_selling_price
)
from app.models.pos import (
    CashRegisterSession, Receipt, ReceiptItem, DailyReport,
    CashRegisterStatus, ReceiptStatus, SaleItemType, PaymentMethod,
    FISCAL_TRANSITIONS
)
from app.models.user import PosRole
from app.models.ticket import ServiceTicket, TicketStatus
from app.models.inventory import SparePart, PartCategory, PartVisibility
from app.services.goods_service import GoodsService
from app.services.pos_service import POSService


# ============================================
# FIXTURES
# ============================================

@pytest.fixture
def pos_enabled(db, tenant_a):
    ff = FeatureFlag(feature_key='pos_enabled', tenant_id=tenant_a.id, enabled=True)
    db.session.add(ff)
    db.session.commit()
    return ff


@pytest.fixture
def goods_item(db, tenant_a, location_a1):
    """GoodsItem sa stanjem 10 komada."""
    item = GoodsItem(
        tenant_id=tenant_a.id,
        location_id=location_a1.id,
        name='Samsung punjač',
        barcode='8806090123456',
        sku='CHG-SAM-01',
        category='Punjači',
        purchase_price=Decimal('500'),
        selling_price=Decimal('990'),
        default_margin_pct=Decimal('98'),
        current_stock=10,
        min_stock_level=2,
        tax_label='A',
    )
    db.session.add(item)
    db.session.flush()
    return item


@pytest.fixture
def goods_item_b(db, tenant_b, location_b1):
    """GoodsItem tenanta B."""
    item = GoodsItem(
        tenant_id=tenant_b.id,
        location_id=location_b1.id,
        name='iPhone case',
        purchase_price=Decimal('300'),
        selling_price=Decimal('700'),
        current_stock=5,
    )
    db.session.add(item)
    db.session.flush()
    return item


@pytest.fixture
def fiscal_location(db, tenant_a, location_a1):
    """Lokacija sa uključenim fiskalnim režimom."""
    location_a1.fiscal_mode = True
    location_a1.pfr_url = 'http://localhost:3333/api/v3'
    db.session.flush()
    return location_a1


@pytest.fixture
def open_session(db, tenant_a, location_a1, admin_a, pos_enabled):
    """Otvorena kasa sesija."""
    session = CashRegisterSession(
        tenant_id=tenant_a.id,
        location_id=location_a1.id,
        date=date.today(),
        opened_by_id=admin_a.id,
        opened_at=datetime.utcnow(),
        opening_cash=Decimal('5000'),
        status=CashRegisterStatus.OPEN,
        fiscal_mode=False,
    )
    db.session.add(session)
    db.session.flush()
    return session


@pytest.fixture
def fiscal_session(db, tenant_a, fiscal_location, admin_a, pos_enabled):
    """Otvorena fiskalna kasa sesija."""
    session = CashRegisterSession(
        tenant_id=tenant_a.id,
        location_id=fiscal_location.id,
        date=date.today(),
        opened_by_id=admin_a.id,
        opened_at=datetime.utcnow(),
        opening_cash=Decimal('0'),
        status=CashRegisterStatus.OPEN,
        fiscal_mode=True,
    )
    db.session.add(session)
    db.session.flush()
    return session


@pytest.fixture
def ticket_ready(db, tenant_a, location_a1, admin_a):
    """Servisni nalog u READY statusu."""
    ticket = ServiceTicket(
        tenant_id=tenant_a.id,
        location_id=location_a1.id,
        ticket_number=1,
        customer_name='Marko Marković',
        customer_phone='0641234567',
        brand='Samsung',
        model='Galaxy S24',
        problem_description='Zamena ekrana - pukao displej',
        status=TicketStatus.READY,
        final_price=Decimal('12000'),
        created_by_id=admin_a.id,
    )
    db.session.add(ticket)
    db.session.flush()
    return ticket


# ============================================
# HELPER FUNCTIONS
# ============================================

def _open_register(client, location_id, opening_cash=0):
    res = client.post('/api/v1/pos/register/open', json={
        'opening_cash': opening_cash,
        'location_id': location_id
    })
    return json.loads(res.data)


def _create_receipt(client, session_id):
    res = client.post('/api/v1/pos/receipts', json={'session_id': session_id})
    return json.loads(res.data)


def _add_goods_item(client, receipt_id, goods_id, quantity=1, unit_price=None):
    payload = {
        'item_type': 'GOODS',
        'item_id': goods_id,
        'quantity': quantity,
    }
    if unit_price is not None:
        payload['unit_price'] = unit_price
    return client.post(f'/api/v1/pos/receipts/{receipt_id}/items', json=payload)


def _issue_receipt(client, receipt_id, **kwargs):
    payload = {'payment_method': 'CASH', **kwargs}
    return client.post(f'/api/v1/pos/receipts/{receipt_id}/issue', json=payload)


# ============================================
# TEST: suggest_selling_price
# ============================================

class TestSuggestPrice:

    def test_small_amount_rounds_to_10(self):
        assert suggest_selling_price(200, 50) == 300  # 200*1.5=300, round_to=10

    def test_medium_amount_rounds_to_50(self):
        assert suggest_selling_price(500, 55) == 800  # 500*1.55=775, ceil(775/50)*50=800

    def test_large_amount_rounds_to_100(self):
        assert suggest_selling_price(1500, 50) == 2300  # 1500*1.5=2250, ceil to 100 → 2300

    def test_exact_boundary(self):
        # 250 * 2 = 500, boundary → round_to=10, ceil(500/10)*10 = 500
        assert suggest_selling_price(250, 100) == 500


# ============================================
# TEST: GoodsItem CRUD API
# ============================================

class TestGoodsCRUD:

    def test_create_goods_item(self, client_a, pos_enabled):
        res = client_a.post('/api/v1/goods', json={
            'name': 'USB kabl',
            'barcode': '123456789',
            'purchase_price': 200,
            'selling_price': 500,
            'category': 'Kablovi',
            'tax_label': 'A',
        })
        assert res.status_code == 201
        data = json.loads(res.data)
        assert data['item']['name'] == 'USB kabl'
        assert data['item']['selling_price'] == 500.0

    def test_create_goods_without_name_fails(self, client_a, pos_enabled):
        res = client_a.post('/api/v1/goods', json={'purchase_price': 100})
        assert res.status_code == 400

    def test_list_goods(self, client_a, pos_enabled, goods_item):
        _db.session.commit()
        res = client_a.get('/api/v1/goods')
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data['total'] >= 1
        assert any(i['name'] == 'Samsung punjač' for i in data['items'])

    def test_search_goods(self, client_a, pos_enabled, goods_item):
        _db.session.commit()
        res = client_a.get('/api/v1/goods?q=Samsung')
        data = json.loads(res.data)
        assert len(data['items']) >= 1

    def test_update_goods_item(self, client_a, pos_enabled, goods_item):
        _db.session.commit()
        res = client_a.put(f'/api/v1/goods/{goods_item.id}', json={
            'selling_price': 1100
        })
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data['item']['selling_price'] == 1100.0

    def test_idor_tenant_b_cannot_see_tenant_a_goods(self, client_b, pos_enabled, goods_item, tenant_b):
        """Tenant B ne sme videti artikle tenanta A."""
        # Enable POS for tenant B too
        ff = FeatureFlag(feature_key='pos_enabled', tenant_id=tenant_b.id, enabled=True)
        _db.session.add(ff)
        _db.session.commit()
        res = client_b.get(f'/api/v1/goods/{goods_item.id}')
        assert res.status_code == 404

    def test_pos_disabled_returns_403(self, client_a):
        res = client_a.get('/api/v1/goods')
        assert res.status_code == 403


# ============================================
# TEST: Purchase Invoice
# ============================================

class TestPurchaseInvoice:

    def test_create_and_receive_invoice(self, client_a, pos_enabled, goods_item):
        _db.session.commit()
        # Create invoice
        res = client_a.post('/api/v1/goods/invoices', json={
            'supplier_name': 'Mobil Plus',
            'invoice_number': 'F-2026-001',
            'invoice_date': '2026-01-27',
        })
        assert res.status_code == 201
        invoice_id = json.loads(res.data)['invoice_id']

        # Add item
        res = client_a.post(f'/api/v1/goods/invoices/{invoice_id}/items', json={
            'goods_item_id': goods_item.id,
            'item_name': 'Samsung punjač',
            'quantity': 20,
            'purchase_price': 450,
            'selling_price': 990,
        })
        assert res.status_code == 201

        # Receive
        res = client_a.post(f'/api/v1/goods/invoices/{invoice_id}/receive')
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data['status'] == 'RECEIVED'

        # Verify stock increased
        _db.session.expire_all()
        item = GoodsItem.query.get(goods_item.id)
        assert item.current_stock == 30  # 10 + 20
        assert float(item.purchase_price) == 450.0

    def test_receive_empty_invoice_fails(self, client_a, pos_enabled):
        _db.session.commit()
        res = client_a.post('/api/v1/goods/invoices', json={
            'supplier_name': 'Test',
            'invoice_number': 'X-001',
            'invoice_date': '2026-01-27',
        })
        invoice_id = json.loads(res.data)['invoice_id']
        res = client_a.post(f'/api/v1/goods/invoices/{invoice_id}/receive')
        assert res.status_code == 400


# ============================================
# TEST: Stock Adjustment
# ============================================

class TestStockAdjustment:

    def test_write_off(self, client_a, pos_enabled, goods_item):
        _db.session.commit()
        res = client_a.post(f'/api/v1/goods/{goods_item.id}/adjust', json={
            'quantity_change': -3,
            'adjustment_type': 'WRITE_OFF',
            'reason': 'Oštećeni proizvodi',
        })
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data['stock_before'] == 10
        assert data['stock_after'] == 7

    def test_adjustment_prevents_negative_stock(self, client_a, pos_enabled, goods_item):
        _db.session.commit()
        res = client_a.post(f'/api/v1/goods/{goods_item.id}/adjust', json={
            'quantity_change': -20,
            'adjustment_type': 'CORRECTION',
            'reason': 'Inventura',
        })
        assert res.status_code == 400

    def test_stock_adjust_creates_audit_log(self, db, tenant_a, goods_item, admin_a, pos_enabled):
        db.session.commit()
        GoodsService.adjust_goods_stock(
            goods_item.id, tenant_a.id, -2, 'WRITE_OFF', 'Test otpis', admin_a.id
        )
        db.session.commit()

        log = PosAuditLog.query.filter_by(
            tenant_id=tenant_a.id, action='STOCK_ADJUST'
        ).first()
        assert log is not None
        assert log.details_json['stock_before'] == 10
        assert log.details_json['stock_after'] == 8


# ============================================
# TEST: POS sa GOODS stavkama
# ============================================

class TestPOSWithGoods:

    def test_sell_goods_item(self, client_a, pos_enabled, location_a1, goods_item):
        _db.session.commit()
        session_data = _open_register(client_a, location_a1.id, 5000)
        session_id = session_data['session_id']

        receipt_data = _create_receipt(client_a, session_id)
        receipt_id = receipt_data['receipt_id']

        res = _add_goods_item(client_a, receipt_id, goods_item.id, quantity=2)
        assert res.status_code == 201

        res = _issue_receipt(client_a, receipt_id)
        assert res.status_code == 200

        # Stock should decrease
        _db.session.expire_all()
        item = GoodsItem.query.get(goods_item.id)
        assert item.current_stock == 8  # 10 - 2

    def test_sell_goods_insufficient_stock(self, client_a, pos_enabled, location_a1, goods_item):
        _db.session.commit()
        session_data = _open_register(client_a, location_a1.id)
        receipt_data = _create_receipt(client_a, session_data['session_id'])

        res = _add_goods_item(client_a, receipt_data['receipt_id'], goods_item.id, quantity=50)
        assert res.status_code == 400

    def test_search_items_finds_goods(self, client_a, pos_enabled, goods_item):
        _db.session.commit()
        res = client_a.get('/api/v1/pos/search-items?q=Samsung')
        assert res.status_code == 200
        data = json.loads(res.data)
        items = [i for i in data['items'] if i['type'] == 'GOODS']
        assert len(items) >= 1
        assert items[0]['name'] == 'Samsung punjač'

    def test_search_items_by_barcode(self, client_a, pos_enabled, goods_item):
        _db.session.commit()
        res = client_a.get('/api/v1/pos/search-items?q=8806090')
        data = json.loads(res.data)
        items = [i for i in data['items'] if i['type'] == 'GOODS']
        assert len(items) >= 1

    def test_search_items_min_length(self, client_a, pos_enabled, goods_item):
        _db.session.commit()
        res = client_a.get('/api/v1/pos/search-items?q=S')
        data = json.loads(res.data)
        assert data['items'] == []


# ============================================
# TEST: Idempotency
# ============================================

class TestIdempotency:

    def test_issue_with_idempotency_key_prevents_duplicate(self, client_a, pos_enabled, location_a1):
        _db.session.commit()
        session_data = _open_register(client_a, location_a1.id)
        receipt_data = _create_receipt(client_a, session_data['session_id'])
        receipt_id = receipt_data['receipt_id']

        # Add item
        client_a.post(f'/api/v1/pos/receipts/{receipt_id}/items', json={
            'item_type': 'CUSTOM', 'item_name': 'Test', 'unit_price': 1000
        })

        # Issue with idempotency key
        res1 = _issue_receipt(client_a, receipt_id, idempotency_key='test-key-123')
        assert res1.status_code == 200

        # Second issue with same key returns same receipt (no error)
        res2 = _issue_receipt(client_a, receipt_id, idempotency_key='test-key-123')
        assert res2.status_code == 200

        # Only one receipt should be ISSUED
        count = Receipt.query.filter_by(idempotency_key='test-key-123').count()
        assert count == 1


# ============================================
# TEST: Dual-Mode — Fiskalna vs Interna kasa
# ============================================

class TestDualMode:

    def test_internal_register_no_fiscal_status(self, db, tenant_a, location_a1, admin_a, pos_enabled):
        """Interna kasa — fiscal_status ostaje None."""
        db.session.commit()
        session = POSService.open_register(tenant_a.id, location_a1.id, admin_a.id)
        assert session.fiscal_mode is False

        receipt = POSService.create_receipt(session.id, admin_a.id)
        POSService.add_item_to_receipt(receipt.id, 'CUSTOM', item_name='Test', unit_price=1000)
        issued = POSService.issue_receipt(receipt.id, 'CASH')
        db.session.commit()

        assert issued.fiscal_status is None

    def test_fiscal_register_sets_pending(self, db, tenant_a, fiscal_location, admin_a, pos_enabled):
        """Fiskalna kasa — fiscal_status = 'pending'."""
        db.session.commit()
        session = POSService.open_register(tenant_a.id, fiscal_location.id, admin_a.id)
        assert session.fiscal_mode is True

        receipt = POSService.create_receipt(session.id, admin_a.id)
        POSService.add_item_to_receipt(receipt.id, 'CUSTOM', item_name='Test', unit_price=1000)
        issued = POSService.issue_receipt(receipt.id, 'CASH')
        db.session.commit()

        assert issued.fiscal_status == 'pending'

    def test_open_register_api_returns_fiscal_mode(self, client_a, pos_enabled, fiscal_location):
        _db.session.commit()
        res = client_a.post('/api/v1/pos/register/open', json={
            'location_id': fiscal_location.id,
        })
        assert res.status_code == 201
        data = json.loads(res.data)
        assert data['fiscal_mode'] is True


# ============================================
# TEST: Auto-receipt na ticket delivery
# ============================================

class TestServiceReceipt:

    def test_create_service_receipt(self, db, tenant_a, location_a1, admin_a, ticket_ready, pos_enabled):
        db.session.commit()
        receipt = POSService.create_service_receipt(
            ticket=ticket_ready,
            payment_method='CASH',
            user_id=admin_a.id,
            location_id=location_a1.id,
        )
        db.session.commit()

        assert receipt.status == ReceiptStatus.ISSUED
        assert float(receipt.total_amount) == 12000.0
        assert receipt.idempotency_key == f'ticket-deliver-{ticket_ready.id}'
        assert 'Zamena ekrana' in receipt.items.first().item_name

    def test_service_receipt_idempotent(self, db, tenant_a, location_a1, admin_a, ticket_ready, pos_enabled):
        """Calling twice returns same receipt."""
        db.session.commit()
        r1 = POSService.create_service_receipt(ticket_ready, 'CASH', admin_a.id, location_a1.id)
        r2 = POSService.create_service_receipt(ticket_ready, 'CASH', admin_a.id, location_a1.id)
        assert r1.id == r2.id

    def test_service_receipt_fiscal_mode(self, db, tenant_a, fiscal_location, admin_a, ticket_ready, pos_enabled):
        """Service receipt on fiscal location gets fiscal_status='pending'."""
        ticket_ready.location_id = fiscal_location.id
        db.session.commit()

        receipt = POSService.create_service_receipt(
            ticket=ticket_ready,
            payment_method='CARD',
            user_id=admin_a.id,
            location_id=fiscal_location.id,
        )
        db.session.commit()
        assert receipt.fiscal_status == 'pending'

    def test_service_receipt_auto_opens_session(self, db, tenant_a, location_a1, admin_a, ticket_ready, pos_enabled):
        """Auto-opens CashRegisterSession if none exists."""
        db.session.commit()
        # No session exists
        sessions_before = CashRegisterSession.query.filter_by(
            tenant_id=tenant_a.id, location_id=location_a1.id
        ).count()
        assert sessions_before == 0

        POSService.create_service_receipt(ticket_ready, 'CASH', admin_a.id, location_a1.id)
        db.session.commit()

        sessions_after = CashRegisterSession.query.filter_by(
            tenant_id=tenant_a.id, location_id=location_a1.id
        ).count()
        assert sessions_after == 1


# ============================================
# TEST: Void/Refund restores GOODS stock
# ============================================

class TestVoidRefundStock:

    def test_void_restores_goods_stock(self, db, tenant_a, location_a1, admin_a, goods_item, open_session):
        db.session.commit()
        receipt = POSService.create_receipt(open_session.id, admin_a.id)
        POSService.add_item_to_receipt(receipt.id, 'GOODS', goods_item.id, quantity=3)
        POSService.issue_receipt(receipt.id, 'CASH')
        db.session.commit()

        assert GoodsItem.query.get(goods_item.id).current_stock == 7

        POSService.void_receipt(receipt.id, admin_a.id, 'Pogrešno')
        db.session.commit()

        _db.session.expire_all()
        assert GoodsItem.query.get(goods_item.id).current_stock == 10

    def test_refund_restores_goods_stock(self, db, tenant_a, location_a1, admin_a, goods_item, open_session):
        db.session.commit()
        receipt = POSService.create_receipt(open_session.id, admin_a.id)
        POSService.add_item_to_receipt(receipt.id, 'GOODS', goods_item.id, quantity=2)
        POSService.issue_receipt(receipt.id, 'CASH')
        db.session.commit()

        assert GoodsItem.query.get(goods_item.id).current_stock == 8

        POSService.refund_receipt(receipt.id, admin_a.id)
        db.session.commit()

        _db.session.expire_all()
        assert GoodsItem.query.get(goods_item.id).current_stock == 10


# ============================================
# TEST: X/Z izveštaji
# ============================================

class TestXZReports:

    def test_x_report(self, client_a, pos_enabled, location_a1):
        _db.session.commit()
        session_data = _open_register(client_a, location_a1.id, 5000)
        session_id = session_data['session_id']

        # Create and issue a receipt
        receipt_data = _create_receipt(client_a, session_id)
        client_a.post(f'/api/v1/pos/receipts/{receipt_data["receipt_id"]}/items', json={
            'item_type': 'CUSTOM', 'item_name': 'Test', 'unit_price': 2000
        })
        _issue_receipt(client_a, receipt_data['receipt_id'])

        # X report
        res = client_a.get(f'/api/v1/pos/reports/x?location_id={location_a1.id}')
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data['report_type'] == 'X'
        assert data['total_revenue'] == 2000.0
        assert data['receipt_count'] == 1

    def test_z_report_closes_register(self, client_a, pos_enabled, location_a1):
        _db.session.commit()
        _open_register(client_a, location_a1.id, 5000)

        res = client_a.post('/api/v1/pos/reports/z', json={
            'location_id': location_a1.id,
            'closing_cash': 5000,
        })
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data['report_type'] == 'Z'
        assert 'report_id' in data

        # Register should be closed now
        res = client_a.get(f'/api/v1/pos/reports/x?location_id={location_a1.id}')
        assert res.status_code == 404  # No open register


# ============================================
# TEST: B2B buyer fields
# ============================================

class TestB2BBuyer:

    def test_issue_with_buyer_pib(self, client_a, pos_enabled, location_a1):
        _db.session.commit()
        session_data = _open_register(client_a, location_a1.id)
        receipt_data = _create_receipt(client_a, session_data['session_id'])
        receipt_id = receipt_data['receipt_id']

        client_a.post(f'/api/v1/pos/receipts/{receipt_id}/items', json={
            'item_type': 'CUSTOM', 'item_name': 'B2B usluga', 'unit_price': 5000
        })

        res = _issue_receipt(client_a, receipt_id, buyer_pib='111222333', buyer_name='Firma DOO')
        assert res.status_code == 200

        receipt = Receipt.query.get(receipt_id)
        assert receipt.buyer_pib == '111222333'
        assert receipt.buyer_name == 'Firma DOO'

    def test_invalid_buyer_pib(self, client_a, pos_enabled, location_a1):
        """PIB sa slovima ili pogrešnim brojem cifara → 400."""
        _db.session.commit()
        session_data = _open_register(client_a, location_a1.id)
        receipt_data = _create_receipt(client_a, session_data['session_id'])
        receipt_id = receipt_data['receipt_id']

        client_a.post(f'/api/v1/pos/receipts/{receipt_id}/items', json={
            'item_type': 'CUSTOM', 'item_name': 'Test', 'unit_price': 1000
        })

        # PIB sa slovima
        res = _issue_receipt(client_a, receipt_id, buyer_pib='ABC123456')
        assert res.status_code == 400

    def test_invalid_buyer_pib_wrong_length(self, client_a, pos_enabled, location_a1):
        """PIB sa 8 cifara (treba 9) → 400."""
        _db.session.commit()
        session_data = _open_register(client_a, location_a1.id)
        receipt_data = _create_receipt(client_a, session_data['session_id'])
        receipt_id = receipt_data['receipt_id']

        client_a.post(f'/api/v1/pos/receipts/{receipt_id}/items', json={
            'item_type': 'CUSTOM', 'item_name': 'Test', 'unit_price': 1000
        })

        res = _issue_receipt(client_a, receipt_id, buyer_pib='12345678')
        assert res.status_code == 400


# ============================================
# TEST: Issue receipt on closed register
# ============================================

class TestClosedRegister:

    def test_issue_receipt_closed_register(self, client_a, pos_enabled, location_a1):
        """Pokušaj izdavanja računa na zatvorenoj kasi → 400."""
        _db.session.commit()
        session_data = _open_register(client_a, location_a1.id)
        receipt_data = _create_receipt(client_a, session_data['session_id'])
        receipt_id = receipt_data['receipt_id']

        client_a.post(f'/api/v1/pos/receipts/{receipt_id}/items', json={
            'item_type': 'CUSTOM', 'item_name': 'Test', 'unit_price': 1000
        })

        # Zatvori kasu
        client_a.post('/api/v1/pos/register/close', json={
            'session_id': session_data['session_id'],
            'closing_cash': 1000,
        })

        # Pokušaj izdavanja na zatvorenoj kasi
        res = _issue_receipt(client_a, receipt_id)
        assert res.status_code == 400


# ============================================
# TEST: Duplicate Z report
# ============================================

class TestDuplicateZReport:

    def test_duplicate_z_report(self, client_a, pos_enabled, location_a1):
        """Dupli Z izveštaj za isti dan → 409."""
        _db.session.commit()

        # Otvori i zatvori kasu (Z report)
        session_data = _open_register(client_a, location_a1.id)
        res = client_a.post('/api/v1/pos/reports/z', json={
            'closing_cash': 0,
            'location_id': location_a1.id,
        })
        assert res.status_code == 200

        # Pokušaj drugog Z reporta — kasa je zatvorena, nema otvorene
        res2 = client_a.post('/api/v1/pos/reports/z', json={
            'closing_cash': 0,
            'location_id': location_a1.id,
        })
        # Nema otvorene kase (404) ili dupli report (409)
        assert res2.status_code in (404, 409)


# ============================================
# TEST: Fiscal state machine
# ============================================

class TestFiscalStateMachine:

    def test_valid_transitions(self, db, tenant_a, fiscal_session):
        """Dozvoljeni prelazi: None→pending→sent→signed."""
        receipt = Receipt(
            tenant_id=tenant_a.id,
            session_id=fiscal_session.id,
            receipt_number='TEST-FSM-001',
            status=ReceiptStatus.ISSUED,
            fiscal_status=None,
        )
        db.session.add(receipt)
        db.session.flush()

        receipt.transition_fiscal('pending')
        assert receipt.fiscal_status == 'pending'

        receipt.transition_fiscal('sent')
        assert receipt.fiscal_status == 'sent'

        receipt.transition_fiscal('signed')
        assert receipt.fiscal_status == 'signed'

    def test_invalid_transition(self, db, tenant_a, fiscal_session):
        """Nedozvoljen prelaz: None→signed → ValueError."""
        receipt = Receipt(
            tenant_id=tenant_a.id,
            session_id=fiscal_session.id,
            receipt_number='TEST-FSM-002',
            status=ReceiptStatus.ISSUED,
            fiscal_status=None,
        )
        db.session.add(receipt)
        db.session.flush()

        with pytest.raises(ValueError, match='Nedozvoljen prelaz'):
            receipt.transition_fiscal('signed')

    def test_failed_to_pending_retry(self, db, tenant_a, fiscal_session):
        """Failed → pending (retry) je dozvoljen."""
        receipt = Receipt(
            tenant_id=tenant_a.id,
            session_id=fiscal_session.id,
            receipt_number='TEST-FSM-003',
            status=ReceiptStatus.ISSUED,
            fiscal_status=None,
        )
        db.session.add(receipt)
        db.session.flush()

        receipt.transition_fiscal('pending')
        receipt.transition_fiscal('failed')
        assert receipt.fiscal_status == 'failed'

        receipt.transition_fiscal('pending')
        assert receipt.fiscal_status == 'pending'


# ============================================
# TEST: Barcode case insensitive
# ============================================

class TestBarcodeNormalization:

    def test_barcode_normalized_on_create(self, db, tenant_a, location_a1):
        """Barcode se normalizuje na uppercase pri kreiranju."""
        item = GoodsService.create_goods_item(tenant_a.id, {
            'name': 'Test artikl',
            'barcode': 'abc123def',
            'purchase_price': 100,
            'selling_price': 200,
        })
        db.session.flush()
        assert item.barcode == 'ABC123DEF'

    def test_barcode_normalized_on_update(self, db, tenant_a, location_a1):
        """Barcode se normalizuje na uppercase pri ažuriranju."""
        item = GoodsService.create_goods_item(tenant_a.id, {
            'name': 'Test artikl 2',
            'barcode': 'XYZ789',
            'purchase_price': 100,
            'selling_price': 200,
        })
        db.session.flush()

        GoodsService.update_goods_item(item.id, tenant_a.id, {'barcode': 'new456abc'})
        db.session.flush()
        assert item.barcode == 'NEW456ABC'