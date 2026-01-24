"""
Security utilities for ServisHub.

Provides HTML sanitization, input validation, and rate limiting utilities.
"""

import re
import html
from typing import Optional
from functools import wraps
from flask import request, g
from datetime import datetime, timedelta


# Allowed HTML tags and attributes for user content
ALLOWED_TAGS = {
    'p', 'br', 'strong', 'b', 'em', 'i', 'u', 'ul', 'ol', 'li',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'a', 'span'
}

ALLOWED_ATTRIBUTES = {
    'a': {'href', 'title', 'target', 'rel'},
    'span': {'class'},
    '*': {'class'}
}

# Dangerous patterns to remove
DANGEROUS_PATTERNS = [
    r'javascript:',
    r'vbscript:',
    r'data:text/html',
    r'on\w+\s*=',  # onclick, onload, etc.
    r'<script',
    r'</script',
    r'<iframe',
    r'<object',
    r'<embed',
    r'<form',
    r'<input',
    r'<base',
    r'<link',
    r'<meta',
    r'<style',
]


def sanitize_html(html_content: Optional[str]) -> str:
    """
    Sanitize HTML content to prevent XSS attacks.

    Removes dangerous tags and attributes while preserving safe formatting.

    Args:
        html_content: Raw HTML content from user input

    Returns:
        Sanitized HTML string safe for rendering
    """
    if not html_content:
        return ''

    # First, check for and remove dangerous patterns
    content = html_content
    for pattern in DANGEROUS_PATTERNS:
        content = re.sub(pattern, '', content, flags=re.IGNORECASE)

    # Remove any remaining script-like content
    content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.IGNORECASE | re.DOTALL)

    # Escape any remaining HTML entities in text content
    # but preserve allowed tags
    def replace_tag(match):
        tag = match.group(1).lower()
        if tag.startswith('/'):
            tag = tag[1:]

        if tag in ALLOWED_TAGS:
            # Keep the tag but sanitize attributes
            full_tag = match.group(0)
            # Remove dangerous attributes
            sanitized = re.sub(r'\s+on\w+\s*=\s*["\'][^"\']*["\']', '', full_tag, flags=re.IGNORECASE)
            sanitized = re.sub(r'\s+style\s*=\s*["\'][^"\']*["\']', '', sanitized, flags=re.IGNORECASE)
            return sanitized
        else:
            # Escape the tag
            return html.escape(match.group(0))

    # Match all HTML tags
    content = re.sub(r'<(/?\w+)[^>]*>', replace_tag, content)

    return content


def sanitize_url(url: Optional[str]) -> str:
    """
    Sanitize URL to prevent XSS and open redirects.

    Only allows http:// and https:// URLs.

    Args:
        url: URL string to sanitize

    Returns:
        Sanitized URL or empty string if invalid
    """
    if not url:
        return ''

    url = url.strip()

    # Check for javascript: and other dangerous protocols
    lower_url = url.lower()
    dangerous_protocols = ['javascript:', 'vbscript:', 'data:', 'file:']
    for protocol in dangerous_protocols:
        if lower_url.startswith(protocol):
            return ''

    # Only allow http and https
    if not (lower_url.startswith('http://') or lower_url.startswith('https://')):
        # If no protocol, assume https for safety
        if '://' not in url:
            url = 'https://' + url
        else:
            return ''

    return url


def validate_domain(domain: str) -> bool:
    """
    Validate domain name format.

    Args:
        domain: Domain name to validate

    Returns:
        True if valid domain format
    """
    if not domain or len(domain) > 255:
        return False

    # Remove protocol if present
    domain = domain.lower().strip()
    if domain.startswith('http://') or domain.startswith('https://'):
        domain = domain.split('://', 1)[1]
    if domain.startswith('www.'):
        domain = domain[4:]
    domain = domain.rstrip('/')

    # Check format
    domain_regex = re.compile(
        r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*\.[a-z]{2,}$'
    )

    return bool(domain_regex.match(domain))


def validate_hex_color(color: Optional[str]) -> str:
    """
    Validate and normalize hex color code.

    Args:
        color: Hex color code (e.g., #3b82f6)

    Returns:
        Validated hex color or default
    """
    if not color:
        return '#3b82f6'

    color = color.strip()
    if not color.startswith('#'):
        color = '#' + color

    # Validate hex format
    if re.match(r'^#[0-9a-fA-F]{6}$', color):
        return color.lower()

    return '#3b82f6'


class RateLimiter:
    """
    Simple in-memory rate limiter for API endpoints.

    Note: For production, use Redis-based rate limiting.
    """

    def __init__(self):
        self._requests = {}
        self._cleanup_interval = 300  # 5 minutes
        self._last_cleanup = datetime.utcnow()

    def is_allowed(self, key: str, limit: int = 60, window: int = 60) -> bool:
        """
        Check if request is allowed under rate limit.

        Args:
            key: Unique identifier (e.g., IP + endpoint)
            limit: Maximum requests allowed
            window: Time window in seconds

        Returns:
            True if request is allowed
        """
        now = datetime.utcnow()

        # Periodic cleanup of old entries
        if (now - self._last_cleanup).total_seconds() > self._cleanup_interval:
            self._cleanup()

        window_start = now - timedelta(seconds=window)

        if key not in self._requests:
            self._requests[key] = []

        # Remove old requests
        self._requests[key] = [t for t in self._requests[key] if t > window_start]

        if len(self._requests[key]) >= limit:
            return False

        self._requests[key].append(now)
        return True

    def _cleanup(self):
        """Remove old entries to prevent memory growth."""
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=3600)  # 1 hour

        to_remove = []
        for key, times in self._requests.items():
            self._requests[key] = [t for t in times if t > cutoff]
            if not self._requests[key]:
                to_remove.append(key)

        for key in to_remove:
            del self._requests[key]

        self._last_cleanup = now


# Global rate limiter instance
rate_limiter = RateLimiter()


def rate_limit(limit: int = 60, window: int = 60, key_func=None):
    """
    Decorator for rate limiting endpoints.

    Args:
        limit: Maximum requests allowed in window
        window: Time window in seconds
        key_func: Function to generate rate limit key (default: IP + endpoint)
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if key_func:
                key = key_func()
            else:
                # Default: IP + endpoint
                ip = request.remote_addr or 'unknown'
                key = f"{ip}:{request.endpoint}"

            if not rate_limiter.is_allowed(key, limit, window):
                return {'error': 'Too many requests. Please try again later.'}, 429

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def get_client_ip() -> str:
    """
    Get the real client IP address.

    ProxyFix middleware handles X-Forwarded-For headers and sets
    request.remote_addr correctly. No manual header parsing needed.

    Returns:
        Client IP address string
    """
    return request.remote_addr or 'unknown'