#!/usr/bin/env python
"""Test SMS sending via D7 Networks."""

from app import create_app
from app.services.sms_service import sms_service

app = create_app()
with app.app_context():
    phone = '0649090060'
    message = 'SHub test - provera SMS sistema.'

    formatted = sms_service._format_phone(phone)
    print(f'Formatted phone: {formatted}')
    print(f'Sender ID: {sms_service.sender_id}')
    print(f'API token present: {bool(sms_service.api_token)}')

    success, error = sms_service._send_via_d7(formatted, message)
    print(f'Success: {success}')
    print(f'Error: {error}')
