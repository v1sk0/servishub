"""
Admin Bank Transactions API - Upravljanje bankovnim transakcijama.

Endpointi za:
- Lista neuparenih transakcija
- Ručno uparivanje
- Ignorisanje transakcija
- Poništavanje uparivanja
"""

from datetime import datetime
from flask import Blueprint, request, jsonify, g
from sqlalchemy import or_

from app.extensions import db
from app.models.bank_import import BankTransaction, BankStatementImport, MatchStatus, TransactionType
from app.models.representative import SubscriptionPayment
from app.models import Tenant
from app.models.admin_activity import AdminActivityLog, AdminActionType
from app.api.middleware.auth import platform_admin_required
from app.services.payment_matcher import PaymentMatcher
from app.services.reconciliation import reconcile_payment

bp = Blueprint('admin_bank_transactions', __name__, url_prefix='/bank-transactions')


# ============================================================================
# LISTA TRANSAKCIJA
# ============================================================================

@bp.route('', methods=['GET'])
@platform_admin_required
def list_transactions():
    """
    Lista svih transakcija sa filterima.

    Query params:
        - match_status: UNMATCHED, MATCHED, MANUAL, IGNORED
        - import_id: Filter po konkretnom importu
        - date_from: YYYY-MM-DD
        - date_to: YYYY-MM-DD
        - search: Pretraga po imenu platioca, svrsi, referenci
        - limit: int (default 20)
        - offset: int (default 0)

    Response:
    {
        "transactions": [...],
        "total": 100,
        "stats": {"unmatched": 10, "matched": 80, ...}
    }
    """
    query = BankTransaction.query.filter(
        BankTransaction.transaction_type == TransactionType.CREDIT
    ).order_by(BankTransaction.transaction_date.desc())

    # Filter by status
    match_status = request.args.get('match_status')
    if match_status:
        query = query.filter_by(match_status=match_status)

    # Filter by import
    import_id = request.args.get('import_id', type=int)
    if import_id:
        query = query.filter_by(import_id=import_id)

    # Filter by date
    date_from = request.args.get('date_from')
    if date_from:
        query = query.filter(BankTransaction.transaction_date >= date_from)

    date_to = request.args.get('date_to')
    if date_to:
        query = query.filter(BankTransaction.transaction_date <= date_to)

    # Search
    search = request.args.get('search', '').strip()
    if search:
        search_term = f'%{search}%'
        query = query.filter(
            or_(
                BankTransaction.payer_name.ilike(search_term),
                BankTransaction.purpose.ilike(search_term),
                BankTransaction.payment_reference.ilike(search_term)
            )
        )

    total = query.count()

    limit = request.args.get('limit', 20, type=int)
    offset = request.args.get('offset', 0, type=int)
    transactions = query.offset(offset).limit(limit).all()

    # Get stats
    from sqlalchemy import func
    stats_query = db.session.query(
        BankTransaction.match_status,
        func.count(BankTransaction.id)
    ).filter(
        BankTransaction.transaction_type == TransactionType.CREDIT
    ).group_by(BankTransaction.match_status).all()

    stats = {str(status): count for status, count in stats_query}

    result = []
    for txn in transactions:
        txn_dict = txn.to_dict()
        txn_dict['import_filename'] = txn.import_batch.filename if txn.import_batch else None

        # Add matched invoice info
        if txn.matched_payment:
            txn_dict['matched_invoice'] = txn.matched_payment.invoice_number

        result.append(txn_dict)

    return jsonify({
        'transactions': result,
        'total': total,
        'limit': limit,
        'offset': offset,
        'stats': stats
    })


@bp.route('/unmatched', methods=['GET'])
@platform_admin_required
def list_unmatched():
    """
    Lista neuparenih transakcija (svih importa).

    Query params:
        - import_id: Filter po konkretnom importu
        - min_amount: Minimalni iznos
        - max_amount: Maksimalni iznos
        - date_from: YYYY-MM-DD
        - date_to: YYYY-MM-DD
        - search: Pretraga po imenu platioca ili svrsi
        - include_suggestions: true/false (default true)
        - limit: int (default 100)
        - offset: int (default 0)

    Response:
    {
        "transactions": [
            {
                "id": 123,
                "date": "2026-01-24",
                "amount": 5400.00,
                "payer": {...},
                "reference": {...},
                "purpose": "Pretplata...",
                "suggestions": [...]
            }
        ],
        "total": 3
    }
    """
    query = BankTransaction.query.filter(
        BankTransaction.transaction_type == TransactionType.CREDIT,
        BankTransaction.match_status == MatchStatus.UNMATCHED
    ).order_by(BankTransaction.transaction_date.desc())

    # Filter by import
    import_id = request.args.get('import_id', type=int)
    if import_id:
        query = query.filter_by(import_id=import_id)

    # Filter by amount
    min_amount = request.args.get('min_amount', type=float)
    if min_amount:
        query = query.filter(BankTransaction.amount >= min_amount)

    max_amount = request.args.get('max_amount', type=float)
    if max_amount:
        query = query.filter(BankTransaction.amount <= max_amount)

    # Filter by date
    date_from = request.args.get('date_from')
    if date_from:
        query = query.filter(BankTransaction.transaction_date >= date_from)

    date_to = request.args.get('date_to')
    if date_to:
        query = query.filter(BankTransaction.transaction_date <= date_to)

    # Search
    search = request.args.get('search', '').strip()
    if search:
        search_term = f'%{search}%'
        query = query.filter(
            or_(
                BankTransaction.payer_name.ilike(search_term),
                BankTransaction.purpose.ilike(search_term),
                BankTransaction.payment_reference.ilike(search_term)
            )
        )

    total = query.count()

    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    transactions = query.offset(offset).limit(limit).all()

    include_suggestions = request.args.get('include_suggestions', 'true').lower() == 'true'
    matcher = PaymentMatcher() if include_suggestions else None

    result = []
    for txn in transactions:
        txn_dict = txn.to_dict()

        # Add import info
        txn_dict['import_filename'] = txn.import_batch.filename if txn.import_batch else None

        # Add suggestions
        if matcher:
            txn_dict['suggestions'] = matcher.get_suggestions(txn, limit=3)

        result.append(txn_dict)

    return jsonify({
        'transactions': result,
        'total': total,
        'limit': limit,
        'offset': offset
    })


@bp.route('/<int:txn_id>', methods=['GET'])
@platform_admin_required
def get_transaction(txn_id):
    """
    Detalji pojedinačne transakcije.

    Response:
    {
        "transaction": {...},
        "suggestions": [...],
        "matched_payment": {...} if matched
    }
    """
    txn = BankTransaction.query.get_or_404(txn_id)

    result = {
        'transaction': txn.to_dict()
    }

    # Add import info
    if txn.import_batch:
        result['transaction']['import'] = {
            'id': txn.import_batch.id,
            'filename': txn.import_batch.filename,
            'statement_date': txn.import_batch.statement_date.isoformat() if txn.import_batch.statement_date else None
        }

    # Add suggestions if unmatched
    if txn.match_status == MatchStatus.UNMATCHED:
        matcher = PaymentMatcher()
        result['suggestions'] = matcher.get_suggestions(txn, limit=5)

    # Add matched payment details if matched
    if txn.matched_payment:
        payment = txn.matched_payment
        tenant = Tenant.query.get(payment.tenant_id)
        result['matched_payment'] = {
            **payment.to_dict(),
            'tenant_name': tenant.name if tenant else None,
            'tenant_email': tenant.email if tenant else None
        }
        result['match_info'] = {
            'method': txn.match_method,
            'confidence': float(txn.match_confidence) if txn.match_confidence else None,
            'matched_at': txn.matched_at.isoformat() if txn.matched_at else None,
            'matched_by': txn.matched_by.name if txn.matched_by else 'Auto'
        }

    return jsonify(result)


# ============================================================================
# SUGGESTIONS
# ============================================================================

@bp.route('/<int:txn_id>/suggestions', methods=['GET'])
@platform_admin_required
def get_suggestions(txn_id):
    """
    Dobija predloge za uparivanje transakcije.

    Query params:
        - limit: int (default 5)

    Response:
    {
        "suggestions": [
            {
                "payment_id": 123,
                "invoice": "SH-2026-000001",
                "tenant_name": "Test Servis",
                "amount": 5400.00,
                "confidence": 0.9,
                "match_reasons": ["Iznos se poklapa", "Poziv na broj slican"]
            }
        ]
    }
    """
    txn = BankTransaction.query.get_or_404(txn_id)

    if txn.match_status != MatchStatus.UNMATCHED:
        return jsonify({
            'suggestions': [],
            'message': 'Transakcija je vec uparena ili ignorisana'
        })

    limit = request.args.get('limit', 5, type=int)
    matcher = PaymentMatcher()
    suggestions = matcher.get_suggestions(txn, limit=limit)

    return jsonify({
        'suggestions': suggestions
    })


# ============================================================================
# MANUAL MATCHING
# ============================================================================

@bp.route('/<int:txn_id>/match', methods=['POST'])
@platform_admin_required
def manual_match(txn_id):
    """
    Ručno uparuje transakciju sa fakturom.

    Request body:
    {
        "payment_id": 456,
        "notes": "Optional notes"
    }

    Response:
    {
        "success": true,
        "transaction_id": 123,
        "payment_id": 456,
        "payment_status": "PAID",
        "tenant_name": "..."
    }
    """
    txn = BankTransaction.query.get_or_404(txn_id)

    if txn.match_status in [MatchStatus.MATCHED, MatchStatus.MANUAL]:
        return jsonify({
            'error': f'Transakcija je već uparena (status: {txn.match_status})',
            'existing_payment_id': txn.matched_payment_id
        }), 400

    data = request.get_json() or {}
    payment_id = data.get('payment_id')

    if not payment_id:
        return jsonify({'error': 'payment_id je obavezan'}), 400

    payment = SubscriptionPayment.query.get_or_404(payment_id)
    tenant = Tenant.query.get(payment.tenant_id)

    # Check if payment already matched
    if payment.bank_transaction_id:
        return jsonify({
            'error': 'Faktura je već uparena sa drugom transakcijom',
            'existing_transaction_id': payment.bank_transaction_id
        }), 409

    # Update transaction
    txn.match_status = MatchStatus.MANUAL
    txn.matched_payment_id = payment_id
    txn.match_confidence = 1.0  # Manual = 100%
    txn.match_method = 'MANUAL'
    txn.match_notes = data.get('notes')
    txn.matched_by_id = g.current_admin.id
    txn.matched_at = datetime.utcnow()

    # Reconcile payment (marks as PAID, updates tenant debt, etc.)
    reconcile_result = reconcile_payment(
        payment=payment,
        bank_transaction=txn,
        matched_by='MANUAL',
        admin_id=g.current_admin.id
    )

    # Update import stats
    if txn.import_batch:
        txn.import_batch.matched_count = (txn.import_batch.matched_count or 0) + 1
        txn.import_batch.manual_match_count = (txn.import_batch.manual_match_count or 0) + 1
        txn.import_batch.unmatched_count = max(0, (txn.import_batch.unmatched_count or 0) - 1)

    # Audit log
    AdminActivityLog.log(
        action_type=AdminActionType.MANUAL_MATCH,
        target_type='bank_transaction',
        target_id=txn.id,
        details={
            'payment_id': payment_id,
            'invoice_number': payment.invoice_number,
            'tenant_id': payment.tenant_id,
            'tenant_name': tenant.name if tenant else None,
            'amount': float(txn.amount),
            'notes': data.get('notes')
        }
    )

    db.session.commit()

    return jsonify({
        'success': True,
        'transaction_id': txn.id,
        'payment_id': payment_id,
        'payment_status': payment.status,
        'tenant_name': tenant.name if tenant else None,
        'reconcile_result': reconcile_result
    })


@bp.route('/<int:txn_id>/unmatch', methods=['POST'])
@platform_admin_required
def unmatch_transaction(txn_id):
    """
    Poništava uparivanje transakcije.

    Request body:
    {
        "reason": "Reason for unmatching"
    }

    Response:
    {
        "success": true,
        "transaction_id": 123,
        "previous_payment_id": 456
    }
    """
    txn = BankTransaction.query.get_or_404(txn_id)

    if txn.match_status not in [MatchStatus.MATCHED, MatchStatus.MANUAL]:
        return jsonify({'error': 'Transakcija nije uparena'}), 400

    data = request.get_json() or {}
    reason = data.get('reason', 'Admin unmatch')

    previous_payment_id = txn.matched_payment_id

    # Clear payment link
    if txn.matched_payment:
        payment = txn.matched_payment
        payment.bank_transaction_id = None
        payment.reconciled_at = None
        payment.reconciled_via = None

        # Reset payment status if it was auto-reconciled
        if payment.status == 'PAID' and payment.payment_proof_url is None:
            payment.status = 'PENDING'

    # Reset transaction
    old_status = txn.match_status
    txn.match_status = MatchStatus.UNMATCHED
    txn.matched_payment_id = None
    txn.match_confidence = None
    txn.match_method = None
    txn.match_notes = f'Unmatched: {reason}'
    txn.matched_by_id = None
    txn.matched_at = None

    # Update import stats
    if txn.import_batch:
        txn.import_batch.matched_count = max(0, (txn.import_batch.matched_count or 0) - 1)
        if old_status == MatchStatus.MANUAL:
            txn.import_batch.manual_match_count = max(0, (txn.import_batch.manual_match_count or 0) - 1)
        txn.import_batch.unmatched_count = (txn.import_batch.unmatched_count or 0) + 1

    # Audit log
    AdminActivityLog.log(
        action_type=AdminActionType.UNMATCH,
        target_type='bank_transaction',
        target_id=txn.id,
        details={
            'previous_payment_id': previous_payment_id,
            'reason': reason
        }
    )

    db.session.commit()

    return jsonify({
        'success': True,
        'transaction_id': txn.id,
        'previous_payment_id': previous_payment_id
    })


# ============================================================================
# IGNORE TRANSACTION
# ============================================================================

@bp.route('/<int:txn_id>/ignore', methods=['POST'])
@platform_admin_required
def ignore_transaction(txn_id):
    """
    Označava transakciju kao ignorisanu (nije za nas).

    Request body:
    {
        "reason": "Reason for ignoring (required)"
    }

    Response:
    {
        "success": true,
        "transaction_id": 123
    }
    """
    txn = BankTransaction.query.get_or_404(txn_id)

    if txn.match_status == MatchStatus.IGNORED:
        return jsonify({'error': 'Transakcija je već ignorisana'}), 400

    if txn.match_status in [MatchStatus.MATCHED, MatchStatus.MANUAL]:
        return jsonify({'error': 'Ne možete ignorisati uparenu transakciju'}), 400

    data = request.get_json() or {}
    reason = data.get('reason', 'Ignorisano od strane admina')

    txn.match_status = MatchStatus.IGNORED
    txn.ignore_reason = reason
    txn.ignored_by_id = g.current_admin.id
    txn.ignored_at = datetime.utcnow()

    # Update import stats
    if txn.import_batch:
        txn.import_batch.unmatched_count = max(0, (txn.import_batch.unmatched_count or 0) - 1)

    # Audit log
    AdminActivityLog.log(
        action_type=AdminActionType.IGNORE_TRANSACTION,
        target_type='bank_transaction',
        target_id=txn.id,
        details={
            'reason': reason,
            'amount': float(txn.amount),
            'payer': txn.payer_name
        }
    )

    db.session.commit()

    return jsonify({
        'success': True,
        'transaction_id': txn.id
    })


@bp.route('/<int:txn_id>/unignore', methods=['POST'])
@platform_admin_required
def unignore_transaction(txn_id):
    """
    Poništava ignorisanje transakcije.

    Response:
    {
        "success": true,
        "transaction_id": 123
    }
    """
    txn = BankTransaction.query.get_or_404(txn_id)

    if txn.match_status != MatchStatus.IGNORED:
        return jsonify({'error': 'Transakcija nije ignorisana'}), 400

    txn.match_status = MatchStatus.UNMATCHED
    txn.ignore_reason = None
    txn.ignored_by_id = None
    txn.ignored_at = None

    # Update import stats
    if txn.import_batch:
        txn.import_batch.unmatched_count = (txn.import_batch.unmatched_count or 0) + 1

    # Audit log
    AdminActivityLog.log(
        action_type=AdminActionType.UNIGNORE_TRANSACTION,
        target_type='bank_transaction',
        target_id=txn.id
    )

    db.session.commit()

    return jsonify({
        'success': True,
        'transaction_id': txn.id
    })


# ============================================================================
# STATISTICS
# ============================================================================

@bp.route('/stats', methods=['GET'])
@platform_admin_required
def get_stats():
    """
    Statistika transakcija.

    Query params:
        - import_id: Filter po importu (opciono)

    Response:
    {
        "total": 150,
        "by_status": {
            "UNMATCHED": 10,
            "MATCHED": 130,
            "MANUAL": 5,
            "IGNORED": 5
        },
        "total_unmatched_amount": 54000.00,
        "oldest_unmatched": "2026-01-15"
    }
    """
    base_query = BankTransaction.query.filter(
        BankTransaction.transaction_type == TransactionType.CREDIT
    )

    import_id = request.args.get('import_id', type=int)
    if import_id:
        base_query = base_query.filter_by(import_id=import_id)

    # Count by status
    from sqlalchemy import func

    status_counts = db.session.query(
        BankTransaction.match_status,
        func.count(BankTransaction.id)
    ).filter(
        BankTransaction.transaction_type == TransactionType.CREDIT
    )

    if import_id:
        status_counts = status_counts.filter(BankTransaction.import_id == import_id)

    status_counts = status_counts.group_by(BankTransaction.match_status).all()

    by_status = {status: count for status, count in status_counts}
    total = sum(by_status.values())

    # Unmatched amount
    unmatched_query = base_query.filter(
        BankTransaction.match_status == MatchStatus.UNMATCHED
    )
    unmatched_sum = db.session.query(
        func.sum(BankTransaction.amount)
    ).filter(
        BankTransaction.transaction_type == TransactionType.CREDIT,
        BankTransaction.match_status == MatchStatus.UNMATCHED
    )
    if import_id:
        unmatched_sum = unmatched_sum.filter(BankTransaction.import_id == import_id)
    unmatched_amount = unmatched_sum.scalar() or 0

    # Oldest unmatched
    oldest = base_query.filter(
        BankTransaction.match_status == MatchStatus.UNMATCHED
    ).order_by(BankTransaction.transaction_date.asc()).first()

    return jsonify({
        'total': total,
        'by_status': by_status,
        'total_unmatched_amount': float(unmatched_amount),
        'oldest_unmatched': oldest.transaction_date.isoformat() if oldest else None
    })


# ============================================================================
# BULK OPERATIONS (v3.04)
# ============================================================================

@bp.route('/bulk-ignore', methods=['POST'])
@platform_admin_required
def bulk_ignore_transactions():
    """
    Bulk ignorisanje vise transakcija odjednom.
    Koristi se za bankarske provizije, duplikate, itd.

    Body JSON:
        - transaction_ids: [1, 2, 3] - lista ID-eva transakcija
        - reason: str - razlog ignorisanja (opciono)

    Response:
    {
        "ignored": 3,
        "already_processed": 1
    }
    """
    data = request.get_json() or {}
    txn_ids = data.get('transaction_ids', [])
    reason = data.get('reason', 'No reason provided')

    if not txn_ids:
        return jsonify({'error': 'transaction_ids is required'}), 400

    if len(txn_ids) > 100:
        return jsonify({'error': 'Max 100 transactions per request'}), 400

    # Fetch only UNMATCHED transactions
    transactions = BankTransaction.query.filter(
        BankTransaction.id.in_(txn_ids)
    ).all()

    ignored = 0
    already_processed = 0

    for txn in transactions:
        if txn.match_status == MatchStatus.UNMATCHED:
            txn.match_status = MatchStatus.IGNORED
            txn.match_notes = f'Bulk ignored: {reason}'
            txn.matched_at = datetime.utcnow()
            ignored += 1
        else:
            already_processed += 1

    # Audit log za bulk operaciju
    AdminActivityLog.log(
        action_type=AdminActionType.BULK_IGNORE if hasattr(AdminActionType, 'BULK_IGNORE') else 'BULK_IGNORE',
        target_type='bank_transactions',
        target_id=None,
        target_name=f'{len(txn_ids)} transactions',
        details={
            'transaction_ids': txn_ids,
            'reason': reason,
            'ignored': ignored,
            'already_processed': already_processed
        }
    )

    db.session.commit()

    return jsonify({
        'ignored': ignored,
        'already_processed': already_processed
    })