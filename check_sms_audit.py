"""Check SMS audit - credits, transactions, usage."""
from app import create_app
from app.extensions import db
from sqlalchemy import text

app = create_app()
with app.app_context():
    # Credit balance for tenant 68
    result = db.session.execute(text('''
        SELECT balance, total_spent FROM credit_balance
        WHERE owner_type = 'tenant' AND tenant_id = 68
    '''))
    row = result.fetchone()
    print(f'=== CREDIT BALANCE (Tenant 68) ===')
    print(f'Balance: {row[0]}')
    print(f'Total spent: {row[1]}')

    # Recent credit transactions
    print(f'\n=== RECENT CREDIT TRANSACTIONS ===')
    result = db.session.execute(text('''
        SELECT ct.id, ct.transaction_type, ct.amount, ct.description, ct.created_at
        FROM credit_transaction ct
        JOIN credit_balance cb ON ct.credit_balance_id = cb.id
        WHERE cb.tenant_id = 68
        ORDER BY ct.created_at DESC
        LIMIT 5
    '''))
    for row in result:
        print(f'  #{row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]}')

    # SMS Usage for tenant 68
    print(f'\n=== SMS USAGE (Tenant 68) ===')
    result = db.session.execute(text('''
        SELECT id, ticket_id, message_type, status, credits_charged, sent_at
        FROM tenant_sms_usage
        WHERE tenant_id = 68
        ORDER BY sent_at DESC
        LIMIT 5
    '''))
    for row in result:
        print(f'  #{row[0]} | Ticket:{row[1]} | {row[2]} | {row[3]} | Credits:{row[4]} | {row[5]}')

    # SMS Config
    print(f'\n=== SMS CONFIG ===')
    result = db.session.execute(text('''
        SELECT sms_enabled, monthly_limit,
               (SELECT COUNT(*) FROM tenant_sms_usage WHERE tenant_id = 68
                AND date_trunc('month', sent_at) = date_trunc('month', CURRENT_DATE)) as current_usage
        FROM tenant_sms_config
        WHERE tenant_id = 68
    '''))
    row = result.fetchone()
    if row:
        print(f'SMS Enabled: {row[0]}')
        print(f'Monthly Limit: {row[1]}')
        print(f'Current Month Usage: {row[2]}')
