"""
Google Business Profile Integration Service

Handles OAuth 2.0 flow and Places API (New) interactions for
fetching reviews, photos and ratings from Google Business Profile.

Uses the new Places API (v1) which provides better photo support.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode

import requests
from flask import current_app, url_for

from app.extensions import db
from app.models import TenantGoogleIntegration, TenantGoogleReview, Tenant

logger = logging.getLogger(__name__)


class GoogleIntegrationService:
    """Service for Google Business Profile integration using Places API (New)."""

    # OAuth endpoints
    OAUTH_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"

    # Places API (New) endpoints
    PLACES_API_BASE = "https://places.googleapis.com/v1"

    # Required OAuth scopes
    SCOPES = [
        "https://www.googleapis.com/auth/business.manage",  # Business Profile
        "openid",
        "email",
    ]

    def __init__(self):
        self.client_id = os.environ.get('GOOGLE_OAUTH_CLIENT_ID')
        self.client_secret = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET')
        self.places_api_key = os.environ.get('GOOGLE_PLACES_API_KEY')

    @property
    def is_configured(self) -> bool:
        """Check if Google integration is properly configured."""
        return all([self.client_id, self.client_secret, self.places_api_key])

    def _get_api_headers(self, field_mask: str = None) -> Dict[str, str]:
        """Get headers for Places API (New) requests."""
        headers = {
            'X-Goog-Api-Key': self.places_api_key,
            'Content-Type': 'application/json',
        }
        if field_mask:
            headers['X-Goog-FieldMask'] = field_mask
        return headers

    def get_authorization_url(self, tenant_id: int, redirect_uri: str) -> str:
        """
        Generate OAuth authorization URL for tenant to connect their Google account.

        Args:
            tenant_id: ID of the tenant initiating the connection
            redirect_uri: URL to redirect after authorization

        Returns:
            Full authorization URL to redirect the user to
        """
        if not self.client_id:
            raise ValueError("GOOGLE_OAUTH_CLIENT_ID not configured")

        params = {
            'client_id': self.client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': ' '.join(self.SCOPES),
            'access_type': 'offline',  # Get refresh token
            'prompt': 'consent',  # Always show consent screen for refresh token
            'state': str(tenant_id),  # Pass tenant_id through OAuth flow
        }

        return f"{self.OAUTH_AUTH_URL}?{urlencode(params)}"

    def exchange_code_for_tokens(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """
        Exchange authorization code for access and refresh tokens.

        Args:
            code: Authorization code from OAuth callback
            redirect_uri: Same redirect_uri used in authorization request

        Returns:
            Dict with access_token, refresh_token, expires_in
        """
        if not self.client_id or not self.client_secret:
            raise ValueError("Google OAuth credentials not configured")

        response = requests.post(self.OAUTH_TOKEN_URL, data={
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri,
        })

        if response.status_code != 200:
            logger.error(f"Token exchange failed: {response.text}")
            raise Exception(f"Token exchange failed: {response.json().get('error_description', 'Unknown error')}")

        return response.json()

    def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh an expired access token.

        Args:
            refresh_token: The refresh token to use

        Returns:
            Dict with new access_token and expires_in
        """
        if not self.client_id or not self.client_secret:
            raise ValueError("Google OAuth credentials not configured")

        response = requests.post(self.OAUTH_TOKEN_URL, data={
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token',
        })

        if response.status_code != 200:
            logger.error(f"Token refresh failed: {response.text}")
            raise Exception("Token refresh failed")

        return response.json()

    def search_place_by_name(self, business_name: str, address: str = None) -> List[Dict]:
        """
        Search for businesses on Google Places by name using Places API (New).

        Args:
            business_name: Name of the business
            address: Optional address to narrow search

        Returns:
            List of place data dicts (normalized format)
        """
        if not self.places_api_key:
            raise ValueError("GOOGLE_PLACES_API_KEY not configured")

        query = business_name
        if address:
            query = f"{business_name} {address}"

        url = f"{self.PLACES_API_BASE}/places:searchText"

        logger.info(f"Searching Google Places (New) for: {query}")

        # Field mask for search results
        field_mask = "places.id,places.displayName,places.formattedAddress,places.rating,places.userRatingCount"

        headers = self._get_api_headers(field_mask)

        # Request body for Places API (New)
        body = {
            'textQuery': query,
            'languageCode': 'sr',
            'regionCode': 'RS',
        }

        response = requests.post(url, headers=headers, json=body)

        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response body: {response.text[:500] if response.text else 'empty'}")

        if response.status_code != 200:
            logger.error(f"Place search failed: {response.status_code} - {response.text}")
            error_data = response.json() if response.text else {}
            error_msg = error_data.get('error', {}).get('message', f'HTTP {response.status_code}')
            raise Exception(f"Google API error: {error_msg}")

        data = response.json()
        results = data.get('places', [])

        # If no results, try without region restriction
        if not results:
            logger.info("No results with region restriction, trying global search")
            body_global = {'textQuery': query}
            response = requests.post(url, headers=headers, json=body_global)
            if response.status_code == 200:
                data = response.json()
                results = data.get('places', [])
                logger.info(f"Global search found {len(results)} places")

        logger.info(f"Found {len(results)} places total")

        # Normalize results
        places = []
        for r in results:
            places.append({
                'id': r.get('id'),
                'displayName': r.get('displayName', {}),
                'formattedAddress': r.get('formattedAddress', ''),
                'rating': r.get('rating'),
                'userRatingCount': r.get('userRatingCount'),
            })

        if places:
            logger.info(f"First place: {places[0]}")
        return places

    def get_place_details(self, place_id: str) -> Optional[Dict]:
        """
        Get detailed information about a place including rating, reviews and photos.
        Uses Places API (New) for better photo support.

        Args:
            place_id: Google Place ID

        Returns:
            Place details dict with photos, reviews, rating
        """
        if not self.places_api_key:
            raise ValueError("GOOGLE_PLACES_API_KEY not configured")

        url = f"{self.PLACES_API_BASE}/places/{place_id}"

        # Field mask for detailed info including photos
        field_mask = "id,displayName,formattedAddress,rating,userRatingCount,reviews,photos"

        headers = self._get_api_headers(field_mask)

        # Add language parameter
        params = {'languageCode': 'sr'}

        logger.info(f"Getting place details for: {place_id}")

        response = requests.get(url, headers=headers, params=params)

        if response.status_code != 200:
            logger.error(f"Place details failed: {response.text}")
            return None

        result = response.json()

        logger.info(f"Place details response: {str(result)[:500]}")

        # Normalize to common format
        normalized = {
            'id': result.get('id'),
            'displayName': result.get('displayName', {}),
            'formattedAddress': result.get('formattedAddress', ''),
            'rating': result.get('rating'),
            'userRatingCount': result.get('userRatingCount'),
            'reviews': [],
            'photos': [],
        }

        # Process photos - New API returns photo names that we can use to get URLs
        for photo in result.get('photos', [])[:8]:  # Max 8 photos
            photo_name = photo.get('name')  # e.g., "places/xxx/photos/yyy"
            if photo_name:
                # Build the photo URL using Places API (New) media endpoint
                photo_url = f"{self.PLACES_API_BASE}/{photo_name}/media?key={self.places_api_key}&maxHeightPx=800&maxWidthPx=1200"
                normalized['photos'].append({
                    'url': photo_url,
                    'name': photo_name,
                    'width': photo.get('widthPx'),
                    'height': photo.get('heightPx'),
                    'attributions': photo.get('authorAttributions', []),
                })
                logger.info(f"Added photo: {photo_name}")

        # Process reviews
        for review in result.get('reviews', []):
            normalized['reviews'].append({
                'name': review.get('name', ''),
                'authorAttribution': {
                    'displayName': review.get('authorAttribution', {}).get('displayName', 'Anonymous'),
                    'photoUri': review.get('authorAttribution', {}).get('photoUri'),
                },
                'rating': review.get('rating'),
                'text': {
                    'text': review.get('text', {}).get('text', '') if isinstance(review.get('text'), dict) else review.get('text', ''),
                    'languageCode': review.get('text', {}).get('languageCode') if isinstance(review.get('text'), dict) else None,
                },
                'publishTime': review.get('publishTime'),
                'relativePublishTimeDescription': review.get('relativePublishTimeDescription'),
            })

        logger.info(f"Normalized {len(normalized['photos'])} photos and {len(normalized['reviews'])} reviews")

        return normalized

    def get_photo_url(self, photo_name: str, max_width: int = 800, max_height: int = 600) -> str:
        """
        Get a direct URL for a photo from Places API (New).

        Args:
            photo_name: The photo resource name from the API (e.g., "places/xxx/photos/yyy")
            max_width: Maximum width in pixels
            max_height: Maximum height in pixels

        Returns:
            Direct URL to the photo
        """
        return f"{self.PLACES_API_BASE}/{photo_name}/media?key={self.places_api_key}&maxWidthPx={max_width}&maxHeightPx={max_height}"

    def connect_tenant(self, tenant_id: int, code: str, redirect_uri: str) -> TenantGoogleIntegration:
        """
        Complete the OAuth flow and create/update the integration record.

        Args:
            tenant_id: ID of the tenant
            code: Authorization code from callback
            redirect_uri: OAuth redirect URI

        Returns:
            TenantGoogleIntegration instance
        """
        # Exchange code for tokens
        tokens = self.exchange_code_for_tokens(code, redirect_uri)

        access_token = tokens['access_token']
        refresh_token = tokens.get('refresh_token')
        expires_in = tokens.get('expires_in', 3600)

        # Calculate token expiry
        token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        # Get or create integration record
        integration = TenantGoogleIntegration.query.filter_by(tenant_id=tenant_id).first()

        if not integration:
            integration = TenantGoogleIntegration(tenant_id=tenant_id)
            db.session.add(integration)

        # Update tokens
        integration.access_token = access_token
        if refresh_token:  # May not be returned on re-auth
            integration.refresh_token = refresh_token
        integration.token_expires_at = token_expires_at

        db.session.commit()

        logger.info(f"Google integration connected for tenant {tenant_id}")

        return integration

    def set_place_id(self, tenant_id: int, place_id: str) -> TenantGoogleIntegration:
        """
        Set the Google Place ID for a tenant and fetch initial data.

        Args:
            tenant_id: ID of the tenant
            place_id: Google Place ID to associate

        Returns:
            Updated integration record
        """
        integration = TenantGoogleIntegration.query.filter_by(tenant_id=tenant_id).first()

        if not integration:
            integration = TenantGoogleIntegration(tenant_id=tenant_id)
            db.session.add(integration)

        integration.google_place_id = place_id
        db.session.commit()

        # Fetch initial data
        self.sync_reviews(tenant_id)

        return integration

    def sync_reviews(self, tenant_id: int) -> bool:
        """
        Sync reviews and photos from Google for a tenant.

        Args:
            tenant_id: ID of the tenant to sync

        Returns:
            True if sync was successful
        """
        integration = TenantGoogleIntegration.query.filter_by(tenant_id=tenant_id).first()

        if not integration or not integration.google_place_id:
            logger.warning(f"No Google integration for tenant {tenant_id}")
            return False

        try:
            # Get place details with reviews and photos
            place_data = self.get_place_details(integration.google_place_id)

            if not place_data:
                integration.sync_error = "Failed to fetch place details"
                db.session.commit()
                return False

            # Update rating and count
            integration.google_rating = place_data.get('rating')
            integration.total_reviews = place_data.get('userRatingCount', 0)
            integration.last_sync_at = datetime.utcnow()
            integration.sync_error = None

            # Update photos from new API
            photos = place_data.get('photos', [])
            if photos:
                integration.google_photos = photos[:8]  # Max 8 photos
                logger.info(f"Saved {len(photos[:8])} photos for tenant {tenant_id}")

            # Process reviews
            reviews = place_data.get('reviews', [])

            for review_data in reviews:
                self._upsert_review(integration, review_data)

            db.session.commit()

            logger.info(f"Synced {len(reviews)} reviews and {len(photos)} photos for tenant {tenant_id}")
            return True

        except Exception as e:
            logger.error(f"Review sync failed for tenant {tenant_id}: {e}")
            integration.sync_error = str(e)
            db.session.commit()
            return False

    def _upsert_review(self, integration: TenantGoogleIntegration, review_data: Dict):
        """
        Insert or update a single review.

        Args:
            integration: The integration record
            review_data: Review data from Google API
        """
        # Google review ID is in the 'name' field
        google_review_id = review_data.get('name', '')

        if not google_review_id:
            return

        # Check if review exists
        review = TenantGoogleReview.query.filter_by(
            google_review_id=google_review_id
        ).first()

        if not review:
            review = TenantGoogleReview(
                integration_id=integration.id,
                tenant_id=integration.tenant_id,
                google_review_id=google_review_id,
            )
            db.session.add(review)

        # Update review data
        author_attribution = review_data.get('authorAttribution', {})
        review.author_name = author_attribution.get('displayName', 'Anonymous')
        review.author_photo_url = author_attribution.get('photoUri')
        review.rating = review_data.get('rating', 0)

        # Get text - may be in 'text' object with 'text' property
        text_obj = review_data.get('text', {})
        if isinstance(text_obj, dict):
            review.text = text_obj.get('text', '')
            review.language = text_obj.get('languageCode')
        else:
            review.text = str(text_obj) if text_obj else ''

        # Parse publish time
        publish_time = review_data.get('publishTime')
        if publish_time:
            try:
                # ISO 8601 format
                review.review_time = datetime.fromisoformat(publish_time.replace('Z', '+00:00'))
            except:
                pass

    def disconnect_tenant(self, tenant_id: int) -> bool:
        """
        Disconnect Google integration for a tenant.

        Args:
            tenant_id: ID of the tenant

        Returns:
            True if disconnection was successful
        """
        integration = TenantGoogleIntegration.query.filter_by(tenant_id=tenant_id).first()

        if integration:
            # Delete all reviews
            TenantGoogleReview.query.filter_by(tenant_id=tenant_id).delete()

            # Delete integration
            db.session.delete(integration)
            db.session.commit()

            logger.info(f"Google integration disconnected for tenant {tenant_id}")
            return True

        return False

    def get_visible_reviews(self, tenant_id: int, limit: int = 6, min_rating: int = 4) -> List[TenantGoogleReview]:
        """
        Get visible reviews for display on public site.

        Args:
            tenant_id: ID of the tenant
            limit: Maximum number of reviews to return
            min_rating: Minimum rating to include (default 4)

        Returns:
            List of visible reviews with rating >= min_rating
        """
        return TenantGoogleReview.query.filter(
            TenantGoogleReview.tenant_id == tenant_id,
            TenantGoogleReview.is_visible == True,
            TenantGoogleReview.rating >= min_rating
        ).order_by(
            TenantGoogleReview.review_time.desc()
        ).limit(limit).all()


# Singleton instance
google_service = GoogleIntegrationService()


def sync_all_google_reviews():
    """
    Sync Google reviews for all tenants with valid integration.
    This is meant to be called by a scheduler (Celery/APScheduler).
    """
    integrations = TenantGoogleIntegration.query.filter(
        TenantGoogleIntegration.google_place_id.isnot(None)
    ).all()

    service = GoogleIntegrationService()

    for integration in integrations:
        if integration.needs_sync:
            try:
                service.sync_reviews(integration.tenant_id)
            except Exception as e:
                logger.error(f"Sync failed for tenant {integration.tenant_id}: {e}")

    logger.info(f"Completed Google review sync for {len(integrations)} tenants")
