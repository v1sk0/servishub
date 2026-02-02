#!/usr/bin/env python
"""
Skripta za popunjavanje cost polja za stare SMS zapise.
Pokreni sa: heroku run python scripts/backfill_sms_cost.py -a servicehubdolce
"""

from app import create_app
from app.extensions import db
from app.models import TenantSmsUsage
from decimal import Decimal

app = create_app()
with app.app_context():
    # Dohvati sve SMS sa status='sent' gde cost nije postavljen
    sms_records = TenantSmsUsage.query.filter(
        TenantSmsUsage.status == 'sent',
        db.or_(TenantSmsUsage.cost == None, TenantSmsUsage.cost == 0)
    ).all()

    print(f'Pronadjeno {len(sms_records)} SMS zapisa bez cost-a')

    if sms_records:
        for sms in sms_records:
            sms.cost = Decimal('0.20')
            print(f'  - SMS ID {sms.id}: {sms.sms_type} -> 0.20 kr')

        db.session.commit()
        print('\nSvi zapisi azurirani!')
    else:
        print('Nema zapisa za azuriranje.')
