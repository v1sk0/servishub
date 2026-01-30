"""
Script to update Viper tenant's Google integration and theme
Run on Heroku: heroku run python scripts/update_viper_google.py
"""
from app import create_app
from app.models import Tenant, TenantPublicProfile, TenantGoogleIntegration
from app.extensions import db

app = create_app()

with app.app_context():
    # Find Viper tenant by name
    tenant = Tenant.query.filter(Tenant.name.ilike('%viper%')).first()

    if not tenant:
        # Try to find by profile subdomain
        profile = TenantPublicProfile.query.filter(
            TenantPublicProfile.subdomain.ilike('%viper%')
        ).first()
        if profile:
            tenant = Tenant.query.get(profile.tenant_id)

    if not tenant:
        print("Viper tenant not found!")
        print("\nAll tenants:")
        for t in Tenant.query.all():
            print(f"  {t.id}: {t.name}")
        exit(1)

    print(f"Found tenant: {tenant.name} (ID: {tenant.id})")

    # Get or create public profile
    profile = TenantPublicProfile.query.filter_by(tenant_id=tenant.id).first()
    if profile:
        # Activate premium theme
        profile.theme = 'premium'
        print(f"Theme set to: premium")

        # Set flash categories - only phones, no computers
        profile.flash_service_categories = {
            'telefoni': True,
            'racunari': False,
            'konzole': False,
            'trotineti': False,
            'ostalo': False
        }
        print(f"Flash categories: samo telefoni (racunari OFF)")

    # Check if Google integration exists
    google = TenantGoogleIntegration.query.filter_by(tenant_id=tenant.id).first()

    if not google:
        print("Creating new Google integration...")
        google = TenantGoogleIntegration(tenant_id=tenant.id)
        db.session.add(google)

    # Update Google data
    google.google_place_id = "ChIJExample_ViperMobile"  # Placeholder - needs real Place ID
    google.google_rating = 4.8
    google.total_reviews = 608

    db.session.commit()

    print(f"Updated Google integration:")
    print(f"  Place ID: {google.google_place_id}")
    print(f"  Rating: {google.google_rating}")
    print(f"  Reviews: {google.total_reviews}")
    print("\nDone!")
