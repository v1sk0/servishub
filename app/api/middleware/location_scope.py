"""
Location scoping middleware.

Dekorator @location_scoped garantuje da g.effective_location_id
postoji za svaki scoped endpoint. OWNER/ADMIN mogu proslediti
?location_id= za cross-location pristup.
"""

from functools import wraps
from flask import g, request, abort
from app.models.tenant import ServiceLocation, LocationStatus
from app.models.user import UserRole
from app.extensions import db


def location_scoped(f):
    """Garantuje da g.effective_location_id postoji za svaki scoped endpoint.
    OWNER/ADMIN mogu proslediti ?location_id= za cross-location pristup."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = g.current_user

        # Ako nema current_location, fallback na primary
        if not user.current_location_id:
            primary = ServiceLocation.query.filter_by(
                tenant_id=g.tenant_id, is_primary=True, status=LocationStatus.ACTIVE
            ).first()
            if primary:
                user.current_location_id = primary.id
                db.session.commit()
            else:
                abort(400, description='Nema aktivne lokacije')

        # Override za OWNER/ADMIN
        override_id = request.args.get('location_id', type=int)
        if override_id and override_id != user.current_location_id:
            if user.role not in (UserRole.OWNER, UserRole.ADMIN):
                abort(403, description='Nemate pristup drugoj lokaciji')
            loc = ServiceLocation.query.filter_by(
                id=override_id, tenant_id=g.tenant_id, status=LocationStatus.ACTIVE
            ).first()
            if not loc:
                abort(404, description='Lokacija ne postoji')
            g.effective_location_id = override_id
        else:
            g.effective_location_id = user.current_location_id

        return f(*args, **kwargs)
    return decorated
