"""
Script to delete tenant 'tritel' and all related data.
Run this on Heroku: heroku run python delete_tenant_tritel.py --app servishub
"""
from app import create_app
from app.extensions import db
from app.models.tenant import Tenant, ServiceLocation
from app.models.ticket import ServiceTicket
from app.models.user import TenantUser

app = create_app()
with app.app_context():
    # Find tenant by slug or name
    tenant = Tenant.query.filter(
        (Tenant.slug == 'tritel') |
        (Tenant.name.ilike('%tritel%'))
    ).first()

    if not tenant:
        print('Tenant tritel not found')
        exit(0)

    print(f'Found tenant:')
    print(f'  ID: {tenant.id}')
    print(f'  Name: {tenant.name}')
    print(f'  Slug: {tenant.slug}')
    print(f'  Status: {tenant.status}')
    print(f'  Created: {tenant.created_at}')

    # Count related records
    tickets = ServiceTicket.query.filter_by(tenant_id=tenant.id).count()
    users = TenantUser.query.filter_by(tenant_id=tenant.id).count()
    locations = ServiceLocation.query.filter_by(tenant_id=tenant.id).count()

    print(f'\nRelated records that will be deleted:')
    print(f'  Tickets: {tickets}')
    print(f'  Users: {users}')
    print(f'  Locations: {locations}')

    # Delete tenant (CASCADE will handle related records)
    print(f'\nDeleting tenant {tenant.name} (ID: {tenant.id})...')
    db.session.delete(tenant)
    db.session.commit()
    print('DONE! Tenant and all related data have been deleted.')