"""
Middleware moduli za ServisHub.

- security_headers: Dodaje sigurnosne HTTP headers na sve responses
"""

from .security_headers import init_security_headers, get_security_headers

__all__ = ['init_security_headers', 'get_security_headers']