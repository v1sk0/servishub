"""
Admin Bank Import API - Upload i upravljanje bankovnim izvodima.

Endpointi za:
- Upload izvoda (CSV/XML)
- Lista importa sa filterima
- Pokretanje auto-matching-a
- Detalji importa sa transakcijama
"""

import hashlib
from datetime import datetime
from flask import Blueprint, request, jsonify, g
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.bank_import import (
    BankStatementImport, BankTransaction, ImportStatus, MatchStatus, TransactionType
)
from app.models.admin_activity import AdminActivityLog, AdminActionType
from app.api.middleware.auth import platform_admin_required
from app.services.bank_parsers import detect_bank_and_parse, get_supported_banks
from app.services.payment_matcher import PaymentMatcher
from app.services.reconciliation import reconcile_payment

bp = Blueprint('admin_bank_import', __name__, url_prefix='/bank-import')

ALLOWED_EXTENSIONS = {'csv', 'xml', 'txt'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ============================================================================
# LISTA I DETALJI IMPORTA
# ============================================================================

@bp.route('', methods=['GET'])
@platform_admin_required
def list_imports():
    """
    Lista svih importa bankovnih izvoda.

    Query params:
        - status: PENDING, PROCESSING, COMPLETED, FAILED, PARTIAL
        - bank_code: ALTA, RAIF, etc.
        - date_from: YYYY-MM-DD
        - date_to: YYYY-MM-DD
        - limit: int (default 50)
        - offset: int (default 0)

    Response:
    {
        "imports": [...],
        "total": 123,
        "limit": 50,
        "offset": 0
    }
    """
    query = BankStatementImport.query.order_by(BankStatementImport.imported_at.desc())

    # Filter by status
    status = request.args.get('status')
    if status:
        query = query.filter_by(status=status)

    # Filter by bank
    bank_code = request.args.get('bank_code')
    if bank_code:
        query = query.filter_by(bank_code=bank_code)

    # Filter by date range
    date_from = request.args.get('date_from')
    if date_from:
        query = query.filter(BankStatementImport.statement_date >= date_from)

    date_to = request.args.get('date_to')
    if date_to:
        query = query.filter(BankStatementImport.statement_date <= date_to)

    total = query.count()

    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)

    imports = query.offset(offset).limit(limit).all()

    return jsonify({
        'imports': [imp.to_dict() for imp in imports],
        'total': total,
        'limit': limit,
        'offset': offset
    })


@bp.route('/<int:import_id>', methods=['GET'])
@platform_admin_required
def get_import_details(import_id):
    """
    Detalji importa sa transakcijama.

    Query params:
        - include_transactions: true/false (default true)
        - match_status: UNMATCHED, MATCHED, MANUAL, IGNORED
        - transaction_type: CREDIT, DEBIT (default CREDIT)

    Response:
    {
        "import": {...},
        "transactions": [...]
    }
    """
    bank_import = BankStatementImport.query.get_or_404(import_id)

    result = {'import': bank_import.to_dict()}

    if request.args.get('include_transactions', 'true').lower() == 'true':
        txn_query = bank_import.transactions

        # Filter by match status
        match_status = request.args.get('match_status')
        if match_status:
            txn_query = txn_query.filter_by(match_status=match_status)

        # Filter by transaction type (default: CREDIT)
        txn_type = request.args.get('transaction_type', 'CREDIT')
        txn_query = txn_query.filter_by(transaction_type=txn_type)

        # Order by date
        txn_query = txn_query.order_by(BankTransaction.transaction_date.desc())

        result['transactions'] = [txn.to_dict() for txn in txn_query.all()]

    return jsonify(result)


# ============================================================================
# UPLOAD IZVODA
# ============================================================================

@bp.route('', methods=['POST'])
@platform_admin_required
def upload_statement():
    """
    Upload bankovnog izvoda.

    Request: multipart/form-data
        - file: Bank statement file (CSV/XML)
        - bank_code: (optional) Force specific bank parser
        - statement_date: (optional) Override statement date (YYYY-MM-DD)

    Response:
    {
        "import_id": 123,
        "filename": "izvod_2026-01-24.csv",
        "bank_code": "ALTA",
        "bank_name": "Alta Banka",
        "status": "PENDING",
        "transactions_found": 45
    }
    """
    if 'file' not in request.files:
        return jsonify({'error': 'Fajl nije priložen'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Nije izabran fajl'}), 400

    if not allowed_file(file.filename):
        return jsonify({
            'error': f'Nepodržan format fajla. Dozvoljeni: {", ".join(ALLOWED_EXTENSIONS)}'
        }), 400

    # Read file content
    file_content = file.read()
    file_size = len(file_content)

    if file_size == 0:
        return jsonify({'error': 'Fajl je prazan'}), 400

    # Calculate hash for deduplication
    file_hash = hashlib.sha256(file_content).hexdigest()

    # Check for duplicate
    existing = BankStatementImport.query.filter_by(file_hash=file_hash).first()
    if existing:
        return jsonify({
            'error': 'Ovaj izvod je već uvezen',
            'existing_import_id': existing.id,
            'imported_at': existing.imported_at.isoformat() if existing.imported_at else None
        }), 409

    # Parse file
    bank_code = request.form.get('bank_code')
    try:
        parse_result = detect_bank_and_parse(
            file_content,
            filename=file.filename,
            force_bank=bank_code
        )
    except ValueError as e:
        return jsonify({'error': f'Greška pri parsiranju: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': f'Neočekivana greška: {str(e)}'}), 500

    # Parse statement date
    statement_date = request.form.get('statement_date')
    if statement_date:
        try:
            statement_date = datetime.strptime(statement_date, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid statement_date format (use YYYY-MM-DD)'}), 400
    else:
        statement_date = parse_result.get('statement_date') or datetime.utcnow().date()

    # Create import record
    bank_import = BankStatementImport(
        filename=secure_filename(file.filename),
        file_hash=file_hash,
        file_size=file_size,
        bank_code=parse_result.get('bank_code', 'UNK'),
        bank_name=parse_result.get('bank_name'),
        import_format=parse_result.get('format', 'CSV'),
        encoding=parse_result.get('encoding', 'UTF-8'),
        statement_date=statement_date,
        statement_number=parse_result.get('statement_number'),
        imported_by_id=g.current_admin.id,
        status=ImportStatus.PENDING,
        warnings=parse_result.get('warnings', [])
    )
    db.session.add(bank_import)
    db.session.flush()  # Get ID

    # Create transactions
    transactions = parse_result.get('transactions', [])
    credit_count = 0
    debit_count = 0
    total_credit = 0
    total_debit = 0
    skipped = 0

    for txn_data in transactions:
        # Generate idempotency hash
        txn_hash = BankTransaction.generate_hash(
            date=txn_data.get('date'),
            amount=txn_data.get('amount'),
            payer_account=txn_data.get('payer_account'),
            reference=txn_data.get('reference')
        )

        # Check for duplicate transaction
        existing_txn = BankTransaction.query.filter_by(transaction_hash=txn_hash).first()
        if existing_txn:
            skipped += 1
            continue

        txn = BankTransaction(
            import_id=bank_import.id,
            transaction_hash=txn_hash,
            transaction_type=txn_data.get('type', TransactionType.CREDIT),
            transaction_date=txn_data.get('date'),
            value_date=txn_data.get('value_date'),
            booking_date=txn_data.get('booking_date'),
            amount=txn_data.get('amount', 0),
            currency=txn_data.get('currency', 'RSD'),
            payer_name=txn_data.get('payer_name'),
            payer_account=txn_data.get('payer_account'),
            payer_address=txn_data.get('payer_address'),
            payment_reference=txn_data.get('reference'),
            payment_reference_model=txn_data.get('reference_model'),
            payment_reference_raw=txn_data.get('reference_raw'),
            purpose=txn_data.get('purpose'),
            purpose_code=txn_data.get('purpose_code'),
            bank_transaction_id=txn_data.get('bank_id'),
            raw_data=txn_data.get('raw')
        )
        db.session.add(txn)

        if txn.transaction_type == TransactionType.CREDIT:
            credit_count += 1
            total_credit += float(txn.amount)
        else:
            debit_count += 1
            total_debit += float(txn.amount)

    # Update import stats
    bank_import.total_transactions = credit_count + debit_count
    bank_import.credit_transactions = credit_count
    bank_import.debit_transactions = debit_count
    bank_import.total_credit_amount = total_credit
    bank_import.total_debit_amount = total_debit
    bank_import.unmatched_count = credit_count  # Initially all credits are unmatched

    # Audit log
    AdminActivityLog.log(
        action_type=AdminActionType.BANK_IMPORT,
        target_type='bank_import',
        target_id=bank_import.id,
        target_name=bank_import.filename,
        details={
            'bank_code': bank_import.bank_code,
            'transactions': bank_import.total_transactions,
            'credits': credit_count,
            'debits': debit_count,
            'skipped': skipped,
            'total_credit': total_credit
        }
    )

    db.session.commit()

    return jsonify({
        'import_id': bank_import.id,
        'filename': bank_import.filename,
        'bank_code': bank_import.bank_code,
        'bank_name': bank_import.bank_name,
        'status': bank_import.status,
        'transactions_found': bank_import.total_transactions,
        'credits': credit_count,
        'debits': debit_count,
        'skipped': skipped,
        'warnings': bank_import.warnings
    }), 201


# ============================================================================
# PREVIEW (BEZ ČUVANJA U BAZU)
# ============================================================================

@bp.route('/preview', methods=['POST'])
@platform_admin_required
def preview_statement():
    """
    Parsira fajl i vraća preview bez čuvanja u bazu.

    Korisnik može pregledati transakcije pre nego što potvrdi import.

    Request: multipart/form-data
        - file: Bank statement file (CSV/XML)

    Response:
    {
        "filename": "izvod.csv",
        "bank_code": "ALTA",
        "bank_name": "Alta Banka",
        "format": "XML",
        "statement_date": "2026-01-25",
        "statement_number": "001",
        "transactions": [
            {
                "type": "CREDIT",
                "date": "2026-01-25",
                "amount": 5400.00,
                "currency": "RSD",
                "payer_name": "FIRMA DOO",
                "reference": "97000123400042",
                "purpose": "Pretplata"
            },
            ...
        ],
        "summary": {
            "total_count": 45,
            "credit_count": 42,
            "debit_count": 3,
            "total_credit": 150000.00,
            "total_debit": 5000.00
        },
        "warnings": [],
        "is_duplicate": false,
        "existing_import_id": null
    }
    """
    if 'file' not in request.files:
        return jsonify({'error': 'Fajl nije priložen'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Nije izabran fajl'}), 400

    if not allowed_file(file.filename):
        return jsonify({
            'error': f'Nepodržan format fajla. Dozvoljeni: {", ".join(ALLOWED_EXTENSIONS)}'
        }), 400

    # Read file content
    file_content = file.read()
    file_size = len(file_content)

    if file_size == 0:
        return jsonify({'error': 'Fajl je prazan'}), 400

    # Calculate hash for deduplication check
    file_hash = hashlib.sha256(file_content).hexdigest()

    # Check for duplicate
    existing = BankStatementImport.query.filter_by(file_hash=file_hash).first()
    is_duplicate = existing is not None

    # Parse file
    try:
        parse_result = detect_bank_and_parse(
            file_content,
            filename=file.filename,
            force_bank=None
        )
    except ValueError as e:
        return jsonify({'error': f'Greška pri parsiranju: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': f'Neočekivana greška: {str(e)}'}), 500

    # Build transaction list for preview
    transactions_preview = []
    credit_count = 0
    debit_count = 0
    total_credit = 0
    total_debit = 0

    for txn_data in parse_result.get('transactions', []):
        txn_type = txn_data.get('type', 'CREDIT')
        amount = float(txn_data.get('amount', 0))

        transactions_preview.append({
            'type': txn_type,
            'date': txn_data.get('date').isoformat() if txn_data.get('date') else None,
            'amount': amount,
            'currency': txn_data.get('currency', 'RSD'),
            'payer_name': txn_data.get('payer_name'),
            'payer_account': txn_data.get('payer_account'),
            'reference': txn_data.get('reference'),
            'reference_raw': txn_data.get('reference_raw'),
            'purpose': txn_data.get('purpose')
        })

        if txn_type == 'CREDIT':
            credit_count += 1
            total_credit += amount
        else:
            debit_count += 1
            total_debit += amount

    statement_date = parse_result.get('statement_date')

    return jsonify({
        'filename': file.filename,
        'file_hash': file_hash,
        'file_size': file_size,
        'bank_code': parse_result.get('bank_code', 'UNK'),
        'bank_name': parse_result.get('bank_name', 'Nepoznata banka'),
        'format': parse_result.get('format', 'CSV'),
        'encoding': parse_result.get('encoding', 'UTF-8'),
        'statement_date': statement_date.isoformat() if statement_date else None,
        'statement_number': parse_result.get('statement_number'),
        'transactions': transactions_preview,
        'summary': {
            'total_count': credit_count + debit_count,
            'credit_count': credit_count,
            'debit_count': debit_count,
            'total_credit': total_credit,
            'total_debit': total_debit
        },
        'warnings': parse_result.get('warnings', []),
        'is_duplicate': is_duplicate,
        'existing_import_id': existing.id if existing else None,
        'existing_import_date': existing.imported_at.isoformat() if existing else None
    })


# ============================================================================
# PROCESS / AUTO-MATCH
# ============================================================================

@bp.route('/<int:import_id>/process', methods=['POST'])
@platform_admin_required
def process_import(import_id):
    """
    Pokreće auto-matching za import.

    Response:
    {
        "matched": 42,
        "unmatched": 3,
        "partial": 0,
        "skipped": 0,
        "details": [
            {
                "transaction_id": 123,
                "status": "MATCHED",
                "payment_id": 456,
                "confidence": 1.0,
                "method": "EXACT_REF"
            },
            ...
        ]
    }
    """
    bank_import = BankStatementImport.query.get_or_404(import_id)

    if bank_import.status == ImportStatus.PROCESSING:
        return jsonify({'error': 'Import se već procesira'}), 409

    bank_import.status = ImportStatus.PROCESSING
    db.session.commit()

    matcher = PaymentMatcher()
    results = []
    matched = 0
    unmatched = 0
    partial = 0
    skipped = 0

    # Only CREDIT transactions that are UNMATCHED
    transactions = bank_import.transactions.filter(
        BankTransaction.transaction_type == TransactionType.CREDIT,
        BankTransaction.match_status == MatchStatus.UNMATCHED
    ).all()

    for txn in transactions:
        try:
            match_result = matcher.match_transaction(txn)

            results.append({
                'transaction_id': txn.id,
                'status': txn.match_status,
                'payment_id': txn.matched_payment_id,
                'confidence': float(txn.match_confidence) if txn.match_confidence else None,
                'method': txn.match_method
            })

            if txn.match_status == MatchStatus.MATCHED:
                matched += 1
                # Reconcile payment - označi kao PAID, ažuriraj dugovanje
                if txn.matched_payment:
                    try:
                        reconcile_payment(
                            payment=txn.matched_payment,
                            bank_transaction=txn,
                            matched_by='AUTO',
                            admin_id=g.current_admin.id
                        )
                    except Exception as rec_error:
                        results[-1]['reconcile_error'] = str(rec_error)
            elif txn.match_status == MatchStatus.PARTIAL:
                partial += 1
            else:
                unmatched += 1
        except Exception as e:
            # Don't fail entire batch on single error
            results.append({
                'transaction_id': txn.id,
                'status': 'ERROR',
                'error': str(e)
            })
            skipped += 1

    # Update import stats
    bank_import.matched_count = matched
    bank_import.unmatched_count = unmatched
    bank_import.processed_at = datetime.utcnow()

    if unmatched == 0 and skipped == 0:
        bank_import.status = ImportStatus.COMPLETED
    elif matched > 0:
        bank_import.status = ImportStatus.PARTIAL
    else:
        bank_import.status = ImportStatus.PENDING

    # Audit log
    AdminActivityLog.log(
        action_type=AdminActionType.BANK_IMPORT_PROCESS,
        target_type='bank_import',
        target_id=bank_import.id,
        target_name=bank_import.filename,
        details={
            'matched': matched,
            'unmatched': unmatched,
            'partial': partial,
            'skipped': skipped
        }
    )

    db.session.commit()

    return jsonify({
        'matched': matched,
        'unmatched': unmatched,
        'partial': partial,
        'skipped': skipped,
        'details': results
    })


# ============================================================================
# HELPER ENDPOINTS
# ============================================================================

@bp.route('/banks', methods=['GET'])
@platform_admin_required
def list_supported_banks():
    """
    Lista podržanih banaka za import.

    Response:
    {
        "banks": [
            {"code": "ALTA", "name": "Alta Banka"},
            ...
        ]
    }
    """
    return jsonify({
        'banks': get_supported_banks()
    })


@bp.route('/<int:import_id>', methods=['DELETE'])
@platform_admin_required
def delete_import(import_id):
    """
    Briše import i sve povezane transakcije.

    OPREZ: Ovo briše sve transakcije! Koristi samo ako je import pogrešan.
    """
    bank_import = BankStatementImport.query.get_or_404(import_id)

    # Check if any transactions are already matched
    matched_count = bank_import.transactions.filter(
        BankTransaction.match_status.in_([MatchStatus.MATCHED, MatchStatus.MANUAL])
    ).count()

    if matched_count > 0:
        return jsonify({
            'error': f'Nije moguće obrisati import jer ima {matched_count} uparenih transakcija',
            'hint': 'Prvo poništi uparivanja pa onda obriši'
        }), 400

    filename = bank_import.filename

    # Delete all transactions
    bank_import.transactions.delete()

    # Delete import
    db.session.delete(bank_import)

    # Audit log
    AdminActivityLog.log(
        action_type=AdminActionType.BANK_IMPORT_DELETE,
        target_type='bank_import',
        target_id=import_id,
        target_name=filename
    )

    db.session.commit()

    return jsonify({
        'message': f'Import "{filename}" obrisan'
    })