"""
SMS Billing Service - naplata SMS notifikacija iz kredit sistema.

Upravlja:
- Proveru da li tenant ima dovoljno kredita
- Rezervaciju/naplatu kredita za SMS
- Refund ako SMS ne uspe
- Logovanje transakcija
"""

from decimal import Decimal
from datetime import datetime
from typing import Tuple, Optional

from sqlalchemy import select

from ..extensions import db
from ..models import (
    Tenant, CreditBalance, CreditTransaction, CreditTransactionType,
    OwnerType, TenantSmsUsage
)


# Default vrednost (koristi se ako PlatformSettings nije dostupan)
DEFAULT_SMS_COST_CREDITS = Decimal('0.20')


def get_sms_price() -> Decimal:
    """
    Vraća trenutnu cenu SMS-a iz PlatformSettings.

    Returns:
        Decimal cena u kreditima
    """
    try:
        from ..models import PlatformSettings
        settings = PlatformSettings.get_settings()
        return settings.sms_price_credits or DEFAULT_SMS_COST_CREDITS
    except Exception:
        return DEFAULT_SMS_COST_CREDITS


# Za backward compatibility - koristi funkciju umesto konstante
SMS_COST_CREDITS = get_sms_price()


class SmsBillingService:
    """
    Servis za naplatu SMS notifikacija.

    Koristi se pre slanja SMS-a da:
    1. Proveri da li tenant ima SMS uključen
    2. Proveri da li ima dovoljno kredita
    3. Naplati kredit (ako uspe)
    4. Vrati kredit ako SMS ne uspe (refund)
    """

    @staticmethod
    def can_send_sms(tenant_id: int) -> Tuple[bool, str]:
        """
        Proverava da li tenant može da pošalje SMS.

        Args:
            tenant_id: ID tenanta

        Returns:
            Tuple (can_send, reason)
            - can_send: True ako može, False ako ne može
            - reason: Razlog zašto ne može (ako can_send=False)
        """
        tenant = Tenant.query.get(tenant_id)
        if not tenant:
            return False, "Servis nije pronađen"

        # 1. Proveri da li je SMS uključen
        if not tenant.sms_notifications_enabled:
            return False, "SMS notifikacije nisu uključene"

        # 2. Proveri da li ima consent
        if not tenant.sms_notifications_consent_given:
            return False, "Nije data saglasnost za SMS notifikacije"

        # 3. Proveri kredit balance
        credit_balance = CreditBalance.query.filter_by(
            owner_type=OwnerType.TENANT,
            tenant_id=tenant_id
        ).first()

        if not credit_balance:
            return False, "Nema kredit račun"

        sms_cost = get_sms_price()  # Dinamička cena iz PlatformSettings
        if credit_balance.balance < sms_cost:
            return False, f"Nedovoljno kredita (potrebno: {sms_cost}, stanje: {credit_balance.balance})"

        return True, "OK"

    @staticmethod
    def charge_for_sms(
        tenant_id: int,
        sms_type: str,
        reference_id: int = None,
        description: str = None
    ) -> Tuple[bool, Optional[int], str]:
        """
        Naplaćuje kredit za SMS.

        Args:
            tenant_id: ID tenanta
            sms_type: Tip SMS-a (TICKET_READY, PICKUP_REMINDER_10, etc.)
            reference_id: ID reference (npr. ticket_id)
            description: Opis transakcije

        Returns:
            Tuple (success, transaction_id, message)
            - success: True ako je naplata uspela
            - transaction_id: ID CreditTransaction (za eventualni refund)
            - message: Poruka o statusu
        """
        # Proveri da li može da pošalje (osnovne provere)
        tenant = Tenant.query.get(tenant_id)
        if not tenant:
            return False, None, "Servis nije pronađen"

        if not tenant.sms_notifications_enabled:
            return False, None, "SMS notifikacije nisu uključene"

        if not tenant.sms_notifications_consent_given:
            return False, None, "Nije data saglasnost za SMS notifikacije"

        # Dohvati dinamičku cenu
        sms_cost = get_sms_price()

        # Kreiraj idempotency key
        idempotency_key = f"sms:{tenant_id}:{sms_type}:{reference_id}:{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        # Proveri da li je već naplaćeno (idempotency)
        existing = CreditTransaction.query.filter_by(
            idempotency_key=idempotency_key
        ).first()
        if existing:
            return True, existing.id, "Već naplaćeno"

        # ================================================================
        # ATOMIC CHARGING: SELECT FOR UPDATE
        # Zaključava red u bazi dok traje transakcija
        # Sprečava race condition kod paralelnih SMS-ova
        # ================================================================
        stmt = select(CreditBalance).where(
            CreditBalance.owner_type == OwnerType.TENANT,
            CreditBalance.tenant_id == tenant_id
        ).with_for_update(nowait=False)  # Čekaj ako je zaključano

        result = db.session.execute(stmt)
        credit_balance = result.scalar_one_or_none()

        if not credit_balance:
            return False, None, "Nema kredit račun"

        # Proveri balance SA LOCK-om (atomski)
        balance_before = credit_balance.balance
        balance_after = balance_before - sms_cost

        if balance_after < 0:
            return False, None, f"Nedovoljno kredita (potrebno: {sms_cost}, stanje: {balance_before})"

        # Kreiraj transakciju
        if not description:
            description = f"SMS notifikacija - {sms_type}"

        transaction = CreditTransaction(
            credit_balance_id=credit_balance.id,
            transaction_type=CreditTransactionType.SMS_NOTIFICATION,
            amount=-sms_cost,  # Negativno jer oduzimamo
            balance_before=balance_before,
            balance_after=balance_after,
            description=description,
            reference_type='sms_usage',
            reference_id=reference_id,
            idempotency_key=idempotency_key
        )

        # Ažuriraj balance (još uvek pod lock-om)
        credit_balance.balance = balance_after
        credit_balance.total_spent += sms_cost

        db.session.add(transaction)
        db.session.commit()  # Commit oslobađa lock

        return True, transaction.id, "Uspešno naplaćeno"

    @staticmethod
    def refund_sms(transaction_id: int, reason: str = "SMS slanje neuspešno") -> Tuple[bool, str]:
        """
        Vraća kredit za neuspešan SMS.

        Args:
            transaction_id: ID originalne transakcije
            reason: Razlog refund-a

        Returns:
            Tuple (success, message)
        """
        original = CreditTransaction.query.get(transaction_id)
        if not original:
            return False, "Transakcija nije pronađena"

        if original.transaction_type != CreditTransactionType.SMS_NOTIFICATION:
            return False, "Nije SMS transakcija"

        # Proveri da li je već refund-ovan
        refund_key = f"refund:{transaction_id}"
        existing_refund = CreditTransaction.query.filter_by(
            idempotency_key=refund_key
        ).first()
        if existing_refund:
            return True, "Već refund-ovano"

        # Dohvati balance
        credit_balance = CreditBalance.query.get(original.credit_balance_id)
        if not credit_balance:
            return False, "Kredit račun nije pronađen"

        # Izračunaj refund amount (apsolutna vrednost originalnog iznosa)
        refund_amount = abs(original.amount)

        # Kreiraj refund transakciju
        balance_before = credit_balance.balance
        balance_after = balance_before + refund_amount

        refund_transaction = CreditTransaction(
            credit_balance_id=credit_balance.id,
            transaction_type=CreditTransactionType.REFUND,
            amount=refund_amount,  # Pozitivno jer vraćamo
            balance_before=balance_before,
            balance_after=balance_after,
            description=f"Refund: {reason}",
            reference_type='sms_refund',
            reference_id=original.id,
            idempotency_key=refund_key
        )

        # Ažuriraj balance
        credit_balance.balance = balance_after
        credit_balance.total_spent -= refund_amount  # Smanjujemo total_spent

        db.session.add(refund_transaction)
        db.session.commit()

        return True, "Refund uspešan"

    @staticmethod
    def get_tenant_sms_stats(tenant_id: int, month: str = None) -> dict:
        """
        Dohvata statistiku SMS potrošnje za tenanta.

        Args:
            tenant_id: ID tenanta
            month: Mesec u formatu "YYYY-MM" (default: tekući mesec)

        Returns:
            Dict sa statistikama
        """
        from sqlalchemy import func, extract

        if not month:
            month = datetime.utcnow().strftime('%Y-%m')

        year, month_num = map(int, month.split('-'))

        # Broj poslanih
        sent_count = TenantSmsUsage.query.filter(
            TenantSmsUsage.tenant_id == tenant_id,
            TenantSmsUsage.status == 'sent',
            extract('year', TenantSmsUsage.created_at) == year,
            extract('month', TenantSmsUsage.created_at) == month_num
        ).count()

        # Ukupna cena
        total_cost = db.session.query(func.sum(TenantSmsUsage.cost)).filter(
            TenantSmsUsage.tenant_id == tenant_id,
            TenantSmsUsage.status == 'sent',
            extract('year', TenantSmsUsage.created_at) == year,
            extract('month', TenantSmsUsage.created_at) == month_num
        ).scalar() or Decimal('0')

        # Po tipu
        by_type = db.session.query(
            TenantSmsUsage.sms_type,
            func.count(TenantSmsUsage.id),
            func.sum(TenantSmsUsage.cost)
        ).filter(
            TenantSmsUsage.tenant_id == tenant_id,
            TenantSmsUsage.status == 'sent',
            extract('year', TenantSmsUsage.created_at) == year,
            extract('month', TenantSmsUsage.created_at) == month_num
        ).group_by(TenantSmsUsage.sms_type).all()

        return {
            'month': month,
            'sent': sent_count,
            'total_cost': float(total_cost),
            'by_type': {
                stype: {'count': count, 'cost': float(cost or 0)}
                for stype, count, cost in by_type
            }
        }

    @staticmethod
    def get_credit_balance(tenant_id: int) -> Optional[Decimal]:
        """
        Dohvata trenutno stanje kredita za tenanta.

        Args:
            tenant_id: ID tenanta

        Returns:
            Decimal balance ili None ako nema račun
        """
        credit_balance = CreditBalance.query.filter_by(
            owner_type=OwnerType.TENANT,
            tenant_id=tenant_id
        ).first()

        return credit_balance.balance if credit_balance else None


# Singleton instanca
sms_billing_service = SmsBillingService()
