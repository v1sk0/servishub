"""
Security Headers Middleware - Dodaje sigurnosne HTTP headers.

Headers koji se dodaju:
- Content-Security-Policy (CSP) - Sprecava XSS napade
- Strict-Transport-Security (HSTS) - Forsira HTTPS
- X-Frame-Options - Sprecava clickjacking
- X-Content-Type-Options - Sprecava MIME sniffing
- X-XSS-Protection - Legacy XSS zastita
- Referrer-Policy - Kontrolise Referer header
- Permissions-Policy - Kontrolise browser features
"""

from flask import Flask, request
from typing import Dict


def get_security_headers(is_production: bool = False) -> Dict[str, str]:
    """
    Vraca dictionary sigurnosnih headers-a.

    Args:
        is_production: Da li je produkciono okruzenje (strozi HSTS)
    """
    headers = {
        # X-Content-Type-Options - sprecava MIME type sniffing
        # Bez ovoga browser moze da "pogadja" tip fajla i izvrsava ga
        'X-Content-Type-Options': 'nosniff',

        # X-Frame-Options - sprecava clickjacking (ugradivanje u iframe)
        # SAMEORIGIN dozvoljava samo sa istog domena
        'X-Frame-Options': 'SAMEORIGIN',

        # X-XSS-Protection - legacy header za starije browsere
        # Moderni browseri koriste CSP, ali ovo ne skodi
        'X-XSS-Protection': '1; mode=block',

        # Referrer-Policy - kontrolise sta se salje u Referer headeru
        # strict-origin-when-cross-origin: pun URL za isti origin, samo origin za cross-origin
        'Referrer-Policy': 'strict-origin-when-cross-origin',

        # Permissions-Policy (bivsi Feature-Policy)
        # Onemogucava pristup osetljivim browser API-jima
        'Permissions-Policy': (
            'accelerometer=(), '
            'camera=(), '
            'geolocation=(), '
            'gyroscope=(), '
            'magnetometer=(), '
            'microphone=(), '
            'payment=(), '
            'usb=()'
        ),

        # Content-Security-Policy (CSP) - glavna zastita od XSS
        # Definise odakle se smeju ucitavati resursi
        'Content-Security-Policy': _get_csp_policy(),
    }

    # HSTS - Strict-Transport-Security
    # Forsira browser da koristi HTTPS
    if is_production:
        # 1 godina, ukljuci subdomene, preload lista
        headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
    else:
        # U development okruzenju kraci max-age
        headers['Strict-Transport-Security'] = 'max-age=86400'

    return headers


def _get_csp_policy() -> str:
    """
    Generise Content-Security-Policy header.

    CSP kontrolise odakle browser sme da ucitava resurse.
    Ovo je glavna zastita od XSS napada.
    """
    # Definiasano po direktive za citljivost
    directives = {
        # default-src: default za sve sto nije eksplicitno definisano
        "default-src": "'self'",

        # script-src: JavaScript izvori
        # 'self' - samo sa naseg domena
        # 'unsafe-inline' - inline scripts (potrebno za Alpine.js x-data)
        # 'unsafe-eval' - eval() (potrebno za neke libs)
        # Eksterni: Google API (OAuth, reCAPTCHA, Maps), Tailwind CDN, Alpine.js CDN
        "script-src": "'self' 'unsafe-inline' 'unsafe-eval' https://apis.google.com https://www.google.com https://www.gstatic.com https://maps.googleapis.com https://cdnjs.cloudflare.com https://cdn.tailwindcss.com https://cdn.jsdelivr.net",

        # style-src: CSS izvori
        # 'unsafe-inline' - inline styles (Tailwind utilities)
        "style-src": "'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com",

        # font-src: Font fajlovi
        "font-src": "'self' https://fonts.gstatic.com data:",

        # img-src: Slike
        # data: - data URLs (base64 slike)
        # blob: - blob URLs (uploads)
        # Cloudinary za LK slike
        "img-src": "'self' data: blob: https://res.cloudinary.com https://*.googleusercontent.com",

        # connect-src: AJAX/Fetch zahtevi
        # Nas API, Google OAuth, Cloudinary upload
        "connect-src": "'self' https://oauth2.googleapis.com https://api.cloudinary.com https://www.googleapis.com",

        # frame-src: iframe izvori
        # Google reCAPTCHA i OAuth popups
        "frame-src": "'self' https://accounts.google.com https://www.google.com",

        # object-src: Plugin content (Flash, Java)
        # 'none' - potpuno onemoguceno (sigurnije)
        "object-src": "'none'",

        # base-uri: Ogranicava <base> tag
        "base-uri": "'self'",

        # form-action: Gde forme mogu da submituju
        "form-action": "'self' https://accounts.google.com",

        # frame-ancestors: Ko moze da nas ugradi u iframe
        "frame-ancestors": "'self'",

        # upgrade-insecure-requests: Upgrade HTTP na HTTPS
        "upgrade-insecure-requests": "",
    }

    # Spoji sve direktive u jedan string
    policy_parts = []
    for directive, value in directives.items():
        if value:
            policy_parts.append(f"{directive} {value}")
        else:
            policy_parts.append(directive)

    return "; ".join(policy_parts)


def init_security_headers(app: Flask) -> None:
    """
    Inicijalizuje security headers middleware za Flask app.

    Dodaje after_request handler koji postavlja sigurnosne headers
    na svaki response.

    Args:
        app: Flask aplikacija
    """
    is_production = not app.debug

    @app.after_request
    def add_security_headers(response):
        """Dodaje sigurnosne headers na svaki response."""

        # Preskoce za health check (jednostavniji response)
        if request.path == '/health':
            return response

        # Dobavi headers
        headers = get_security_headers(is_production)

        # Dodaj headers na response
        for header, value in headers.items():
            response.headers[header] = value

        # Cache control - sprecava kesirane osetljivih stranica
        # Vazno za stranice sa podacima (dashboard, nalozi, itd.)
        if request.path.startswith('/api/') or request.path.startswith('/admin/') or request.path.startswith('/dashboard'):
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'

        return response

    # Loguj inicijalizaciju
    app.logger.info(f'Security headers initialized (production={is_production})')