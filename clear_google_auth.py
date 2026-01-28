"""Clear Google auth for a specific user."""
from app import create_app
from app.extensions import db
from app.models import TenantUser

app = create_app()
with app.app_context():
    user = TenantUser.query.filter_by(email='vipergsm@gmail.com').first()
    if user:
        print(f'Found user: id={user.id}, google_id={user.google_id}')
        user.google_id = None
        user.auth_provider = None
        db.session.commit()
        print('Cleared google_id and auth_provider')
    else:
        print('User not found with that email')
