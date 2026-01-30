"""
Script to update Viper tenant's Google integration and theme
Run on Heroku: heroku run python scripts/update_viper_google.py
"""
from datetime import datetime, timedelta
from app import create_app
from app.models import Tenant, TenantPublicProfile, TenantGoogleIntegration, TenantGoogleReview
from app.extensions import db

app = create_app()

# Demo recenzije - kao da su sync-ovane sa Google-a
DEMO_REVIEWS = [
    {
        'author_name': 'Marko Petrović',
        'rating': 5,
        'text': 'Odlična usluga! Zamenili su ekran na mom iPhone-u za samo sat vremena. Sve radi perfektno, cena fer. Preporučujem!',
        'days_ago': 3
    },
    {
        'author_name': 'Ana Jovanović',
        'rating': 5,
        'text': 'Profesionalan pristup i brza usluga. Telefon mi je pao u vodu, mislila sam da je gotov, ali su uspeli da izvade sve podatke. Hvala!',
        'days_ago': 7
    },
    {
        'author_name': 'Nikola Đorđević',
        'rating': 5,
        'text': 'Treći put dolazim ovde i uvek sam zadovoljan. Zamena baterije na Samsung-u završena za 30 minuta. Top servis!',
        'days_ago': 12
    },
    {
        'author_name': 'Jelena Milosavljević',
        'rating': 4,
        'text': 'Dobra usluga, telefon popravljen kako treba. Jedino što je trebalo malo duže nego što su rekli, ali sve u svemu zadovoljna sam.',
        'days_ago': 18
    },
    {
        'author_name': 'Stefan Nikolić',
        'rating': 5,
        'text': 'Konačno servis koji zna šta radi! Popravili su mi matičnu ploču koju su drugi odbili. Svaka čast momcima!',
        'days_ago': 25
    },
    {
        'author_name': 'Milica Stanković',
        'rating': 5,
        'text': 'Zamena ekrana na Xiaomi telefonu - brzo, kvalitetno i povoljno. Garancija na popravku je super stvar. Preporuka!',
        'days_ago': 30
    },
    {
        'author_name': 'Dušan Ilić',
        'rating': 5,
        'text': 'Sjajan servis! Otključali su mi telefon koji sam zaboravio šifru. Ljubazno osoblje i profesionalna usluga.',
        'days_ago': 35
    },
    {
        'author_name': 'Ivana Pavlović',
        'rating': 4,
        'text': 'Zadovoljna sam popravkom. Konektor za punjenje je zamenjen i telefon se sada puni normalno. Hvala!',
        'days_ago': 42
    },
    {
        'author_name': 'Aleksandar Todorović',
        'rating': 5,
        'text': 'Već godinama nosim telefone ovde na popravku. Pouzdan servis sa fer cenama. Preporučujem svima!',
        'days_ago': 50
    },
    {
        'author_name': 'Maja Kostić',
        'rating': 5,
        'text': 'Zamenili su mi kameru na telefonu. Slike su sada kristalno jasne kao na novom. Super servis!',
        'days_ago': 60
    },
]

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

    # Update Google data - pravi Place ID za Viper Mobile Novi Beograd
    # Place ID se može naći na: https://developers.google.com/maps/documentation/javascript/examples/places-placeid-finder
    google.google_place_id = "ChIJnZ5qx5V6WkcRaFhCLCsH1f0"  # Viper Mobile placeholder
    google.google_rating = 4.8
    google.total_reviews = 608
    google.last_sync_at = datetime.utcnow()

    db.session.flush()  # Da dobijemo google.id

    print(f"Updated Google integration:")
    print(f"  Place ID: {google.google_place_id}")
    print(f"  Rating: {google.google_rating}")
    print(f"  Reviews: {google.total_reviews}")

    # Delete existing reviews for this tenant (fresh sync simulation)
    existing_reviews = TenantGoogleReview.query.filter_by(tenant_id=tenant.id).all()
    if existing_reviews:
        print(f"\nDeleting {len(existing_reviews)} existing reviews...")
        for r in existing_reviews:
            db.session.delete(r)

    # Add demo reviews
    print(f"\nAdding {len(DEMO_REVIEWS)} demo reviews...")
    for i, review_data in enumerate(DEMO_REVIEWS):
        review = TenantGoogleReview(
            integration_id=google.id,
            tenant_id=tenant.id,
            google_review_id=f"viper_demo_review_{i+1}_{tenant.id}",
            author_name=review_data['author_name'],
            rating=review_data['rating'],
            text=review_data['text'],
            language='sr',
            review_time=datetime.utcnow() - timedelta(days=review_data['days_ago']),
            is_visible=True
        )
        db.session.add(review)
        print(f"  + {review_data['author_name']} ({review_data['rating']}★)")

    db.session.commit()

    print(f"\n✅ Done! Viper tenant updated with:")
    print(f"   - Premium theme")
    print(f"   - Flash categories: samo telefoni")
    print(f"   - Google rating: {google.google_rating} ({google.total_reviews} reviews)")
    print(f"   - {len(DEMO_REVIEWS)} demo reviews for carousel")
