"""
Ticket Parts testovi — dodaj/ukloni deo, stock dedukcija, negativni scenariji.
"""
import pytest
import json
from app.models.inventory import SparePart, SparePartUsage, PartVisibility, PartCategory
from app.models.ticket import ServiceTicket, TicketStatus


@pytest.fixture
def spare_part(db, tenant_a, location_a1):
    """Rezervni deo sa 10 komada na stanju."""
    part = SparePart(
        tenant_id=tenant_a.id,
        location_id=location_a1.id,
        part_name='Ekran iPhone 13',
        part_number='IP13-SCR',
        quantity=10,
        purchase_price=5000,
        selling_price=8000,
        visibility=PartVisibility.PRIVATE,
        part_category=PartCategory.DISPLAY,
    )
    db.session.add(part)
    db.session.flush()
    return part


@pytest.fixture
def ticket(db, tenant_a, location_a1, admin_a):
    """Servisni nalog za testiranje."""
    t = ServiceTicket(
        tenant_id=tenant_a.id,
        location_id=location_a1.id,
        created_by_id=admin_a.id,
        ticket_number=99001,
        customer_name='Test Kupac',
        customer_phone='0601234567',
        device_type='PHONE',
        brand='Apple',
        model='iPhone 13',
        problem_description='Razbijen ekran',
        status=TicketStatus.IN_PROGRESS,
    )
    db.session.add(t)
    db.session.flush()
    return t


class TestAddParts:
    """Dodavanje delova na tiket."""

    def test_add_part_to_ticket(self, client_a, ticket, spare_part):
        res = client_a.post(f'/api/v1/tickets/{ticket.id}/parts', json={
            'spare_part_id': spare_part.id,
            'quantity': 1
        })
        assert res.status_code == 201

    def test_add_part_reduces_stock(self, client_a, db, ticket, spare_part):
        """Dodavanje dela umanjuje zalihu."""
        initial_qty = spare_part.quantity
        client_a.post(f'/api/v1/tickets/{ticket.id}/parts', json={
            'spare_part_id': spare_part.id,
            'quantity': 2
        })
        db.session.refresh(spare_part)
        assert spare_part.quantity == initial_qty - 2

    def test_add_part_insufficient_stock(self, client_a, ticket, spare_part):
        """Negativan test: dodavanje dela bez dovoljno zalihe."""
        res = client_a.post(f'/api/v1/tickets/{ticket.id}/parts', json={
            'spare_part_id': spare_part.id,
            'quantity': 999
        })
        assert res.status_code == 409

    def test_list_parts(self, client_a, ticket, spare_part):
        # Add a part first
        client_a.post(f'/api/v1/tickets/{ticket.id}/parts', json={
            'spare_part_id': spare_part.id,
            'quantity': 1
        })
        res = client_a.get(f'/api/v1/tickets/{ticket.id}/parts')
        assert res.status_code == 200
        data = json.loads(res.data)
        assert len(data['items']) == 1
        assert data['total_cost'] > 0


class TestRemoveParts:
    """Uklanjanje delova sa tiketa."""

    def test_remove_part_returns_stock(self, client_a, db, ticket, spare_part):
        """Uklanjanje dela vraca zalihu."""
        # Add
        res = client_a.post(f'/api/v1/tickets/{ticket.id}/parts', json={
            'spare_part_id': spare_part.id,
            'quantity': 3
        })
        usage_id = json.loads(res.data).get('id')
        db.session.refresh(spare_part)
        qty_after_add = spare_part.quantity

        # Remove
        res = client_a.delete(f'/api/v1/tickets/{ticket.id}/parts/{usage_id}')
        assert res.status_code == 200
        db.session.refresh(spare_part)
        assert spare_part.quantity == qty_after_add + 3


class TestPartsValidation:
    """Validacioni testovi."""

    def test_add_without_spare_part_id_fails(self, client_a, ticket):
        res = client_a.post(f'/api/v1/tickets/{ticket.id}/parts', json={
            'quantity': 1
        })
        assert res.status_code == 400

    def test_add_zero_quantity_fails(self, client_a, ticket, spare_part):
        res = client_a.post(f'/api/v1/tickets/{ticket.id}/parts', json={
            'spare_part_id': spare_part.id,
            'quantity': 0
        })
        assert res.status_code == 400