"""Delete a tenant and all related data."""
import sys
from app import create_app
from app.extensions import db
from app.models import (
    Tenant, TenantUser, ServiceLocation, UserLocation,
    ServiceTicket, PhoneListing, SparePart, ServiceRepresentative,
    AuditLog
)

def delete_tenant(tenant_id):
    """Delete tenant and all related data."""
    app = create_app()
    with app.app_context():
        tenant = Tenant.query.get(tenant_id)
        if not tenant:
            print(f"Tenant with ID {tenant_id} not found!")
            return False

        print(f"\n=== Deleting tenant: {tenant.name} (ID={tenant.id}) ===\n")

        # Count related data
        users = TenantUser.query.filter_by(tenant_id=tenant_id).all()
        locations = ServiceLocation.query.filter_by(tenant_id=tenant_id).all()
        tickets = ServiceTicket.query.filter_by(tenant_id=tenant_id).all()
        phones = PhoneListing.query.filter_by(tenant_id=tenant_id).all()
        parts = SparePart.query.filter_by(tenant_id=tenant_id).all()
        reps = ServiceRepresentative.query.filter_by(tenant_id=tenant_id).all()
        audits = AuditLog.query.filter_by(tenant_id=tenant_id).all()

        print(f"Found:")
        print(f"  - {len(users)} users")
        print(f"  - {len(locations)} locations")
        print(f"  - {len(tickets)} tickets")
        print(f"  - {len(phones)} phones")
        print(f"  - {len(parts)} parts")
        print(f"  - {len(reps)} representatives")
        print(f"  - {len(audits)} audit logs")
        print()

        # Delete in correct order (respect foreign keys)

        # 1. Delete audit logs first
        print("Deleting audit logs...")
        AuditLog.query.filter_by(tenant_id=tenant_id).delete()

        # 2. Delete user-location mappings
        print("Deleting user-location mappings...")
        for user in users:
            UserLocation.query.filter_by(user_id=user.id).delete()

        # 3. Delete tickets
        print("Deleting tickets...")
        ServiceTicket.query.filter_by(tenant_id=tenant_id).delete()

        # 4. Delete inventory
        print("Deleting phones...")
        PhoneListing.query.filter_by(tenant_id=tenant_id).delete()

        print("Deleting spare parts...")
        SparePart.query.filter_by(tenant_id=tenant_id).delete()

        # 5. Delete representatives
        print("Deleting representatives...")
        ServiceRepresentative.query.filter_by(tenant_id=tenant_id).delete()

        # 6. Delete users
        print("Deleting users...")
        TenantUser.query.filter_by(tenant_id=tenant_id).delete()

        # 7. Delete locations
        print("Deleting locations...")
        ServiceLocation.query.filter_by(tenant_id=tenant_id).delete()

        # 8. Finally delete tenant
        print("Deleting tenant...")
        db.session.delete(tenant)

        # Commit all changes
        db.session.commit()

        print(f"\n=== Tenant '{tenant.name}' successfully deleted! ===\n")
        return True

if __name__ == '__main__':
    tenant_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    delete_tenant(tenant_id)