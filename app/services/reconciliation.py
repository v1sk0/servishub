"""
Reconciliation Service - Uparivanje bankovnih transakcija sa fakturama.

Funkcije za:
- Označavanje fakture kao plaćene nakon bank match-a
- Update tenant dugovanja
- Audit trail za sve promene
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any

from ..extensions import db
from ..models.representative import SubscriptionPayment
from ..models.bank_import import BankTransaction, MatchStatus
from ..models import Tenant, TenantMessage
from ..models.tenant import TenantStatus
from ..models.tenant_message import MessageCategory, MessagePriority


def reconcile_payment(
    payment: SubscriptionPayment,
    bank_transaction: BankTransaction,
    matched_by: str = 'AUTO',
    admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Reconciluje uplatu nakon bank match-a.

    Ova funkcija:
    1. Povezuje payment sa bank transakcijom
    2. Označava payment kao PAID
    3. Ažurira tenant dugovanje
    4. Šalje sistemsku poruku tenantu

    Args:
        payment: SubscriptionPayment to reconcile
        bank_transaction: Matched BankTransaction
        matched_by: 'AUTO' or 'MANUAL'
        admin_id: Admin ID if manual match

    Returns:
        Dict with reconciliation details

    Side Effects:
        - Updates payment status
        - Updates tenant debt
        - Creates system message
        - Does NOT commit - caller must commit!
    """
    tenant = Tenant.query.get(payment.tenant_id)
    if not tenant:
        return {'success': False, 'error': 'Tenant not found'}

    result = {
        'success': True,
        'payment_id': payment.id,
        'transaction_id': bank_transaction.id,
        'changes': []
    }

    # 1. Link payment to transaction
    payment.bank_transaction_id = bank_transaction.id
    payment.reconciled_at = datetime.utcnow()
    payment.reconciled_via = f'BANK_IMPORT_{matched_by}'
    result['changes'].append('payment_linked')

    # 2. Update payment status
    old_status = payment.status
    if old_status != 'PAID':
        payment.status = 'PAID'
        payment.paid_at = bank_transaction.transaction_date
        result['changes'].append(f'status_changed:{old_status}->PAID')

    # 3. Update tenant debt
    old_debt = tenant.current_debt or Decimal('0')
    if old_debt > 0:
        new_debt = max(Decimal('0'), old_debt - payment.total_amount)
        tenant.current_debt = new_debt
        result['changes'].append(f'debt_updated:{float(old_debt)}->{float(new_debt)}')
        result['debt_change'] = float(old_debt - new_debt)

    # 4. Update tenant billing status
    tenant.last_payment_at = datetime.utcnow()
    if tenant.days_overdue and tenant.days_overdue > 0:
        tenant.days_overdue = 0
        result['changes'].append('days_overdue_reset')

    # 5. Trust score update (if paid on time)
    from datetime import date
    if payment.due_date:
        if bank_transaction.transaction_date <= payment.due_date:
            # Paid on time
            if hasattr(tenant, 'update_trust_score'):
                tenant.update_trust_score(+5, 'Automatska potvrda uplate na vreme')
            tenant.consecutive_on_time_payments = (tenant.consecutive_on_time_payments or 0) + 1
            result['changes'].append('trust_score_+5')

            # Yearly bonus
            if tenant.consecutive_on_time_payments >= 12:
                if hasattr(tenant, 'update_trust_score'):
                    tenant.update_trust_score(+15, '12 meseci uzastopnih uplata')
                tenant.consecutive_on_time_payments = 0
                result['changes'].append('yearly_bonus_+15')
        else:
            # Paid late but paid
            tenant.consecutive_on_time_payments = 0
            result['changes'].append('consecutive_payments_reset')

    # 6. Unblock tenant if needed
    if tenant.status in [TenantStatus.SUSPENDED, TenantStatus.EXPIRED]:
        # Check if all debt is cleared
        if (tenant.current_debt or Decimal('0')) <= Decimal('0'):
            if hasattr(tenant, 'unblock'):
                tenant.unblock()
            else:
                tenant.status = TenantStatus.ACTIVE
            result['changes'].append('tenant_unblocked')

    # 7. System message to tenant
    try:
        TenantMessage.create_system_message(
            tenant_id=tenant.id,
            subject='Uplata potvrđena - hvala!',
            body=f'''Vaša uplata za fakturu {payment.invoice_number} je automatski potvrđena.

Iznos: {float(payment.total_amount):,.2f} {payment.currency}
Datum uplate: {bank_transaction.transaction_date.strftime("%d.%m.%Y")}

Vaše trenutno dugovanje: {float(tenant.current_debt or 0):,.2f} RSD

Hvala na poverenju!''',
            category=MessageCategory.BILLING,
            priority=MessagePriority.NORMAL,
            related_payment_id=payment.id
        )
        result['changes'].append('message_sent')
    except Exception as e:
        result['message_error'] = str(e)

    return result


def bulk_reconcile(transactions: list, admin_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Reconciluje više transakcija odjednom.

    Args:
        transactions: List of matched BankTransactions
        admin_id: Admin ID for audit

    Returns:
        Summary dict with success/failure counts
    """
    results = {
        'total': len(transactions),
        'success': 0,
        'failed': 0,
        'errors': []
    }

    for txn in transactions:
        if txn.match_status not in [MatchStatus.MATCHED, MatchStatus.MANUAL]:
            results['failed'] += 1
            results['errors'].append({
                'transaction_id': txn.id,
                'error': f'Invalid status: {txn.match_status}'
            })
            continue

        if not txn.matched_payment:
            results['failed'] += 1
            results['errors'].append({
                'transaction_id': txn.id,
                'error': 'No matched payment'
            })
            continue

        try:
            result = reconcile_payment(
                payment=txn.matched_payment,
                bank_transaction=txn,
                matched_by='AUTO',
                admin_id=admin_id
            )
            if result['success']:
                results['success'] += 1
            else:
                results['failed'] += 1
                results['errors'].append({
                    'transaction_id': txn.id,
                    'error': result.get('error', 'Unknown error')
                })
        except Exception as e:
            results['failed'] += 1
            results['errors'].append({
                'transaction_id': txn.id,
                'error': str(e)
            })

    return results


def get_reconciliation_summary(days: int = 30) -> Dict[str, Any]:
    """
    Vraća sažetak reconciliation aktivnosti.

    Args:
        days: Number of days to look back

    Returns:
        Summary statistics
    """
    from datetime import timedelta
    from sqlalchemy import func

    cutoff = datetime.utcnow() - timedelta(days=days)

    # Payments reconciled in period
    reconciled = SubscriptionPayment.query.filter(
        SubscriptionPayment.reconciled_at >= cutoff,
        SubscriptionPayment.reconciled_via.like('BANK_IMPORT%')
    ).count()

    # Total reconciled amount
    reconciled_amount = db.session.query(
        func.sum(SubscriptionPayment.total_amount)
    ).filter(
        SubscriptionPayment.reconciled_at >= cutoff,
        SubscriptionPayment.reconciled_via.like('BANK_IMPORT%')
    ).scalar() or 0

    # Pending payments (unreconciled)
    pending = SubscriptionPayment.query.filter(
        SubscriptionPayment.status.in_(['PENDING', 'OVERDUE']),
        SubscriptionPayment.bank_transaction_id.is_(None)
    ).count()

    # Pending amount
    pending_amount = db.session.query(
        func.sum(SubscriptionPayment.total_amount)
    ).filter(
        SubscriptionPayment.status.in_(['PENDING', 'OVERDUE']),
        SubscriptionPayment.bank_transaction_id.is_(None)
    ).scalar() or 0

    # Unmatched transactions
    unmatched_txns = BankTransaction.query.filter(
        BankTransaction.match_status == MatchStatus.UNMATCHED,
        BankTransaction.transaction_type == 'CREDIT'
    ).count()

    unmatched_amount = db.session.query(
        func.sum(BankTransaction.amount)
    ).filter(
        BankTransaction.match_status == MatchStatus.UNMATCHED,
        BankTransaction.transaction_type == 'CREDIT'
    ).scalar() or 0

    return {
        'period_days': days,
        'reconciled': {
            'count': reconciled,
            'amount': float(reconciled_amount)
        },
        'pending_payments': {
            'count': pending,
            'amount': float(pending_amount)
        },
        'unmatched_transactions': {
            'count': unmatched_txns,
            'amount': float(unmatched_amount)
        }
    }