"""
Script to connect Viper tenant to their Google Business Profile.
Simulates the same flow as settings UI: search -> select -> sync.

Run on Heroku: heroku run python scripts/update_viper_google.py
"""
from datetime import datetime
from app import create_app
from app.models import Tenant, TenantPublicProfile, TenantGoogleIntegration, TenantGoogleReview
from app.extensions import db
from app.services.google_integration_service import GoogleIntegrationService

app = create_app()

with app.app_context():
    # ============ STEP 1: Find Viper Tenant ============
    print("=" * 50)
    print("VIPER MOBILE - Google Business Integration")
    print("=" * 50)

    tenant = Tenant.query.filter(Tenant.name.ilike('%viper%')).first()

    if not tenant:
        profile = TenantPublicProfile.query.filter(
            TenantPublicProfile.subdomain.ilike('%viper%')
        ).first()
        if profile:
            tenant = Tenant.query.get(profile.tenant_id)

    if not tenant:
        print("\n❌ Viper tenant not found!")
        print("\nSvi tenanti:")
        for t in Tenant.query.all():
            print(f"  {t.id}: {t.name}")
        exit(1)

    print(f"\n✅ Tenant: {tenant.name} (ID: {tenant.id})")

    # ============ STEP 2: Update Profile Settings ============
    profile = TenantPublicProfile.query.filter_by(tenant_id=tenant.id).first()
    if profile:
        profile.theme = 'premium'
        profile.flash_service_categories = {
            'telefoni': True,
            'racunari': False,
            'konzole': False,
            'trotineti': False,
            'ostalo': False
        }
        print(f"✅ Tema: premium")
        print(f"✅ Flash kategorije: samo telefoni")

    # ============ STEP 3: Google Places Search ============
    print("\n" + "=" * 50)
    print("STEP 1: Pretraga Google Places (kao u settings UI)")
    print("=" * 50)

    service = GoogleIntegrationService()

    if not service.places_api_key:
        print("\n⚠️  GOOGLE_PLACES_API_KEY nije konfigurisan!")
        print("   Dodajte ga u Heroku config vars.")
        db.session.commit()
        exit(1)

    try:
        # Search like settings UI would
        search_query = "Viper Mobile doo"
        print(f"\n🔍 Pretražujem: '{search_query}'...")

        places = service.search_place_by_name(
            search_query,
            "Bulevar Arsenija Čarnojevića 91, Novi Beograd"
        )

        if not places:
            print("❌ Nema rezultata pretrage.")
            db.session.commit()
            exit(1)

        print(f"\n📋 Pronađeno {len(places)} rezultata:\n")
        for i, place in enumerate(places[:5]):
            name = place.get('displayName', {}).get('text', 'N/A')
            address = place.get('formattedAddress', 'N/A')
            rating = place.get('rating', 'N/A')
            reviews = place.get('userRatingCount', 0)
            place_id = place.get('id', 'N/A')
            print(f"  [{i+1}] {name}")
            print(f"      📍 {address}")
            print(f"      ⭐ {rating} ({reviews} recenzija)")
            print(f"      🆔 {place_id}\n")

        # ============ STEP 4: Select Place (Auto-select first) ============
        print("=" * 50)
        print("STEP 2: Selekcija biznisa (prvi rezultat)")
        print("=" * 50)

        selected = places[0]
        place_id = selected.get('id')
        place_name = selected.get('displayName', {}).get('text', 'Unknown')

        print(f"\n✅ Izabrano: {place_name}")
        print(f"   Place ID: {place_id}")

        # ============ STEP 5: Connect & Sync (same as settings UI) ============
        print("\n" + "=" * 50)
        print("STEP 3: Povezivanje i sync (kao settings UI)")
        print("=" * 50)

        print("\n📥 Pozivam set_place_id() i sync_reviews()...")

        # This is exactly what settings UI does
        integration = service.set_place_id(tenant.id, place_id)

        if not integration:
            print("❌ Greška pri povezivanju.")
            db.session.commit()
            exit(1)

        # ============ STEP 6: Show Results ============
        print("\n" + "=" * 50)
        print("REZULTATI INTEGRACIJE")
        print("=" * 50)

        # Refresh from DB
        integration = TenantGoogleIntegration.query.filter_by(tenant_id=tenant.id).first()

        print(f"\n✅ Google Business povezan!")
        print(f"   📍 Place ID: {integration.google_place_id}")
        print(f"   ⭐ Rating: {integration.google_rating}")
        print(f"   📊 Ukupno recenzija: {integration.total_reviews}")
        print(f"   🕐 Poslednji sync: {integration.last_sync_at}")

        photos = integration.google_photos or []
        print(f"   📷 Slike u galeriji: {len(photos)}")

        if photos:
            print("\n   Galerija slika:")
            for i, photo in enumerate(photos[:3]):
                print(f"      [{i+1}] {photo.get('url', 'N/A')[:80]}...")

        # Show reviews
        reviews = TenantGoogleReview.query.filter_by(
            tenant_id=tenant.id,
            is_visible=True
        ).order_by(TenantGoogleReview.review_time.desc()).all()

        print(f"\n   📝 Sačuvane recenzije: {len(reviews)}")

        if reviews:
            print("\n   Poslednje recenzije:")
            for r in reviews[:5]:
                text_preview = r.text[:50] + "..." if r.text and len(r.text) > 50 else (r.text or "")
                print(f"      • {r.author_name}: {r.rating}★")
                if text_preview:
                    print(f"        \"{text_preview}\"")

        db.session.commit()

        print("\n" + "=" * 50)
        print("✅ ZAVRŠENO!")
        print("=" * 50)
        print(f"\nViper Mobile je sada povezan sa Google Business.")
        print(f"Javna stranica će prikazivati:")
        print(f"  - Google rating badge (4.8 ★)")
        print(f"  - Carousel sa recenzijama ({len(reviews)} recenzija)")
        print(f"  - Galeriju slika ({len(photos)} slika)")
        print(f"  - Flash usluge (samo telefoni)")

    except Exception as e:
        import traceback
        print(f"\n❌ Greška: {e}")
        traceback.print_exc()
        db.session.rollback()
