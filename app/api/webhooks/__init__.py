"""
Webhooks Blueprint - endpoints za primanje callback-ova od eksternih servisa.

Sadrzi:
- D7 Networks DLR (Delivery Reports)
- (Buduce: Stripe, PayPal, itd.)
"""

from flask import Blueprint

bp = Blueprint('webhooks', __name__, url_prefix='/webhooks')

from . import d7  # noqa: F401, E402
