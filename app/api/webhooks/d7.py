"""
D7 Networks Webhook - Delivery Report (DLR) callback.

Endpoint koji D7 Networks poziva kada se promeni status SMS poruke:
- delivered: Poruka uspešno isporučena primaocu
- failed: Poruka nije isporučena (greška operatora)
- expired: Poruka istekla (primalac nedostupan)

Sigurnosne mere:
1. HMAC-SHA256 signature verification
2. Replay protection (max 5 min stara poruka)
3. Idempotency (DlrLog sprečava duplu obradu)

Konfiguracija:
- D7 Dashboard: podesiti webhook URL https://app.servishub.rs/webhooks/d7/dlr
- Heroku: dodati D7_WEBHOOK_SECRET environment varijablu
"""

import os
import hmac
import hashlib
import json
from datetime import datetime, timedelta

from flask import request, jsonify

from . import bp
from ...extensions import db
from ...models.sms_management import TenantSmsUsage, SmsDlrLog
from ...services.sms_billing_service import SmsBillingService


@bp.route('/d7/dlr', methods=['POST'])
def d7_delivery_report():
    """
    D7 Networks Delivery Report Callback.

    Expected payload:
    {
        "message_id": "abc123",
        "status": "delivered" | "failed" | "expired",
        "timestamp": "2026-02-01T12:00:00Z",
        "error_code": "123" (optional, for failed)
    }

    Response:
    - 200: OK, DLR processed
    - 400: Bad request (missing fields, replay detected)
    - 401: Unauthorized (invalid signature)
    """
    # 1. SIGNATURE VERIFICATION
    signature = request.headers.get('X-D7-Signature')
    if not _verify_signature(request.data, signature):
        print("[DLR] Invalid signature")
        return jsonify({'error': 'Invalid signature'}), 401

    # Parse payload
    try:
        data = request.get_json()
    except Exception as e:
        print(f"[DLR] Invalid JSON: {e}")
        return jsonify({'error': 'Invalid JSON'}), 400

    message_id = data.get('message_id')
    status = data.get('status')
    timestamp = data.get('timestamp')
    error_code = data.get('error_code')

    if not message_id or not status:
        return jsonify({'error': 'Missing message_id or status'}), 400

    # 2. REPLAY PROTECTION (max 5 min old)
    if timestamp:
        try:
            # Parse ISO format timestamp
            if timestamp.endswith('Z'):
                timestamp = timestamp[:-1] + '+00:00'
            msg_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            # Remove timezone info for comparison
            msg_time = msg_time.replace(tzinfo=None)
            if datetime.utcnow() - msg_time > timedelta(minutes=5):
                print(f"[DLR] Replay detected: {message_id} is {datetime.utcnow() - msg_time} old")
                return jsonify({'error': 'Replay detected'}), 400
        except (ValueError, TypeError) as e:
            print(f"[DLR] Invalid timestamp format: {e}")
            # Ne odbijaj poruku zbog lošeg timestamp formata

    # 3. IDEMPOTENCY CHECK
    existing_dlr = SmsDlrLog.query.filter_by(message_id=message_id).first()
    if existing_dlr:
        print(f"[DLR] Already processed: {message_id}")
        return jsonify({'status': 'already_processed'}), 200

    # 4. FIND SMS LOG AND UPDATE
    sms_log = TenantSmsUsage.query.filter_by(
        provider_message_id=message_id
    ).first()

    if sms_log:
        # Update delivery status
        sms_log.delivery_status = status
        sms_log.delivery_status_at = datetime.utcnow()
        if error_code:
            sms_log.delivery_error_code = error_code

        print(f"[DLR] Updated SMS {sms_log.id}: {status}")

        # 5. AUTO-REFUND FOR FAILED/EXPIRED
        if status in ('failed', 'expired'):
            _process_refund(sms_log, status, error_code)
    else:
        print(f"[DLR] SMS not found for message_id: {message_id}")

    # 6. LOG DLR FOR IDEMPOTENCY
    dlr_log = SmsDlrLog(
        message_id=message_id,
        status=status,
        raw_payload=json.dumps(data),
        error_code=error_code
    )
    db.session.add(dlr_log)
    db.session.commit()

    return jsonify({'status': 'ok'}), 200


def _verify_signature(payload: bytes, signature: str) -> bool:
    """
    HMAC-SHA256 signature verification.

    D7 šalje potpis u X-D7-Signature header.
    Secret je D7_WEBHOOK_SECRET environment varijabla.

    U development modu (bez secret-a), prihvata sve zahteve.
    """
    secret = os.environ.get('D7_WEBHOOK_SECRET', '')

    # Dev mode - skip verification
    if not secret:
        print("[DLR] Warning: D7_WEBHOOK_SECRET not set, skipping verification")
        return True

    if not signature:
        return False

    # Compute expected signature
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    # Timing-safe comparison
    return hmac.compare_digest(expected, signature)


def _process_refund(sms_log: TenantSmsUsage, status: str, error_code: str = None):
    """
    Automatski refund kredita za neuspešan SMS.

    Pronalazi originalnu transakciju preko reference_id i vraća kredit.
    """
    from ...models import CreditTransaction, CreditTransactionType

    try:
        # Pronađi originalnu SMS transakciju
        original_transaction = CreditTransaction.query.filter_by(
            reference_type='sms_usage',
            reference_id=sms_log.id,
            transaction_type=CreditTransactionType.SMS_NOTIFICATION
        ).first()

        if not original_transaction:
            # Pokušaj pronaći preko ticket ID ako je reference_id ticket
            if sms_log.reference_type == 'ticket' and sms_log.reference_id:
                original_transaction = CreditTransaction.query.filter(
                    CreditTransaction.reference_type == 'sms_usage',
                    CreditTransaction.transaction_type == CreditTransactionType.SMS_NOTIFICATION,
                    CreditTransaction.description.like(f'%SRV-%')
                ).order_by(CreditTransaction.created_at.desc()).first()

        if original_transaction:
            reason = f"DLR {status}"
            if error_code:
                reason += f" (code: {error_code})"

            success, msg = SmsBillingService.refund_sms(original_transaction.id, reason)
            if success:
                print(f"[DLR] Refund successful for SMS {sms_log.id}: {msg}")
            else:
                print(f"[DLR] Refund failed for SMS {sms_log.id}: {msg}")
        else:
            print(f"[DLR] No transaction found for SMS {sms_log.id}")

    except Exception as e:
        print(f"[DLR] Refund error: {e}")


@bp.route('/d7/test', methods=['GET'])
def d7_test():
    """
    Test endpoint za proveru da li je webhook dostupan.

    Koristi se za D7 dashboard verifikaciju.
    """
    return jsonify({
        'status': 'ok',
        'message': 'D7 DLR webhook is ready',
        'timestamp': datetime.utcnow().isoformat()
    }), 200
