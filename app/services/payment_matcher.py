"""
Payment Matcher - Automatsko uparivanje bankovnih transakcija sa fakturama.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
import re

from ..models import SubscriptionPayment, Tenant
from ..models.bank_import import BankTransaction, MatchStatus
from ..extensions import db


class MatchResult:
    """Rezultat pokušaja match-a."""
    def __init__(
        self,
        success: bool,
        payment: Optional[SubscriptionPayment] = None,
        confidence: float = 0.0,
        method: str = None,
        notes: str = None
    ):
        self.success = success
        self.payment = payment
        self.confidence = confidence
        self.method = method
        self.notes = notes


class PaymentMatcher:
    """
    Uparuje bankovne transakcije sa fakturama.

    Strategije po prioritetu:
    1. EXACT_REF (confidence=1.0) - Tačan poziv na broj
    2. FUZZY_REF (confidence=0.9) - Poziv sa manjim razlikama
    3. AMOUNT_TENANT (confidence=0.7) - Iznos + tenant name match
    4. AMOUNT_DATE (confidence=0.5) - Iznos + datum blizu due_date
    """

    # Tolerance za amount matching (dozvoljeno odstupanje)
    AMOUNT_TOLERANCE = Decimal('0.01')  # 1 para

    # Tolerance za date matching (dana pre/posle)
    DATE_TOLERANCE_DAYS = 7

    def match_transaction(self, txn: BankTransaction) -> MatchResult:
        """
        Pokušava da upari transakciju sa fakturom.

        VAŽNO: Auto-match se radi SAMO za EXACT_REF sa confidence=1.0!
        Sve ostale strategije (fuzzy, amount, date) služe samo za sugestije
        koje admin ručno potvrđuje u UI-ju.

        Args:
            txn: BankTransaction to match

        Returns:
            MatchResult sa payment i confidence

        Side effects:
            Updates txn with match status ONLY if EXACT_REF match found
        """
        # Samo EXACT_REF sa punim confidence-om radi auto-match
        result = self._match_by_exact_reference(txn)
        if result.success and result.confidence >= 1.0:
            self._apply_match(txn, result)
            return result

        # Ostale strategije NE rade auto-match!
        # One se koriste samo u get_suggestions() za UI predloge.
        # Transakcija ostaje UNMATCHED dok admin ručno ne potvrdi.

        return MatchResult(success=False, notes='No exact reference match - use manual matching')

    def get_suggestions(self, txn: BankTransaction, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Vraća listu mogućih match-eva sa confidence score-om.

        Koristi se za manual matching UI.
        """
        suggestions = []

        # Kandidati: neplaćene fakture
        candidates = SubscriptionPayment.query.filter(
            SubscriptionPayment.status.in_(['PENDING', 'OVERDUE'])
        ).all()

        for payment in candidates:
            score = self._calculate_match_score(txn, payment)
            if score > 0:
                tenant = Tenant.query.get(payment.tenant_id)
                suggestions.append({
                    'payment_id': payment.id,
                    'invoice': payment.invoice_number,
                    'tenant_name': tenant.name if tenant else 'Unknown',
                    'amount': float(payment.total_amount),
                    'due_date': payment.due_date.isoformat() if payment.due_date else None,
                    'confidence': score,
                    'match_reasons': self._get_match_reasons(txn, payment)
                })

        # Sortiraj po confidence (desc)
        suggestions.sort(key=lambda x: x['confidence'], reverse=True)

        return suggestions[:limit]

    def _match_by_exact_reference(self, txn: BankTransaction) -> MatchResult:
        """Match po tačnom pozivu na broj."""
        if not txn.payment_reference:
            return MatchResult(success=False)

        # Normalizuj - ukloni razmake i crte
        ref_clean = re.sub(r'[\s\-]', '', txn.payment_reference)

        # Traži fakturu sa istim pozivom na broj
        payments = SubscriptionPayment.query.filter(
            SubscriptionPayment.status.in_(['PENDING', 'OVERDUE'])
        ).all()

        for p in payments:
            if not p.payment_reference:
                continue
            p_ref_clean = re.sub(r'[\s\-]', '', p.payment_reference)
            if ref_clean == p_ref_clean:
                # Proveri i iznos
                if abs(p.total_amount - txn.amount) <= self.AMOUNT_TOLERANCE:
                    return MatchResult(
                        success=True,
                        payment=p,
                        confidence=1.0,
                        method='EXACT_REF',
                        notes=f'Exact reference match: {ref_clean}'
                    )
                else:
                    # Reference match ali iznos se razlikuje
                    return MatchResult(
                        success=True,
                        payment=p,
                        confidence=0.85,
                        method='EXACT_REF_AMOUNT_DIFF',
                        notes=f'Reference match but amount differs: expected {p.total_amount}, got {txn.amount}'
                    )

        return MatchResult(success=False)

    def _match_by_fuzzy_reference(self, txn: BankTransaction) -> MatchResult:
        """Match po delimičnom pozivu na broj."""
        if not txn.payment_reference:
            return MatchResult(success=False)

        ref_clean = re.sub(r'[\s\-]', '', txn.payment_reference)

        # Izvuci tenant_id i invoice_seq iz reference (format: 97{tenant:06d}{seq:05d})
        if len(ref_clean) >= 13 and ref_clean.startswith('97'):
            try:
                tenant_id = int(ref_clean[2:8])

                # Traži fakturu tog tenanta
                payment = SubscriptionPayment.query.filter(
                    SubscriptionPayment.tenant_id == tenant_id,
                    SubscriptionPayment.status.in_(['PENDING', 'OVERDUE'])
                ).order_by(SubscriptionPayment.created_at.desc()).first()

                if payment and abs(payment.total_amount - txn.amount) <= self.AMOUNT_TOLERANCE:
                    return MatchResult(
                        success=True,
                        payment=payment,
                        confidence=0.9,
                        method='FUZZY_REF',
                        notes=f'Reference contains tenant_id={tenant_id}'
                    )
            except (ValueError, IndexError):
                pass

        return MatchResult(success=False)

    def _match_by_amount_and_tenant(self, txn: BankTransaction) -> MatchResult:
        """Match po iznosu i imenu tenanta u svrsi/platiocu."""
        if not txn.payer_name:
            return MatchResult(success=False)

        payer_name_lower = txn.payer_name.lower()

        # Traži tenante čije ime sadrži payer_name (ili obrnuto)
        payments = SubscriptionPayment.query.filter(
            SubscriptionPayment.status.in_(['PENDING', 'OVERDUE'])
        ).all()

        for payment in payments:
            tenant = Tenant.query.get(payment.tenant_id)
            if not tenant or not tenant.name:
                continue

            tenant_name_lower = tenant.name.lower()

            # Proveri da li se imena podudaraju
            name_match = (
                tenant_name_lower in payer_name_lower or
                payer_name_lower in tenant_name_lower or
                self._fuzzy_name_match(payer_name_lower, tenant_name_lower)
            )

            if name_match and abs(payment.total_amount - txn.amount) <= self.AMOUNT_TOLERANCE:
                return MatchResult(
                    success=True,
                    payment=payment,
                    confidence=0.7,
                    method='AMOUNT_TENANT',
                    notes=f'Amount and tenant name match: {tenant.name}'
                )

        return MatchResult(success=False)

    def _match_by_amount_and_date(self, txn: BankTransaction) -> MatchResult:
        """Match po iznosu i blizini datuma."""
        payments = SubscriptionPayment.query.filter(
            SubscriptionPayment.status.in_(['PENDING', 'OVERDUE'])
        ).all()

        best_match = None
        best_score = 0

        for payment in payments:
            if abs(payment.total_amount - txn.amount) > self.AMOUNT_TOLERANCE:
                continue

            # Izračunaj koliko je transakcija blizu due_date
            if payment.due_date:
                days_diff = abs((txn.transaction_date - payment.due_date).days)
                if days_diff <= self.DATE_TOLERANCE_DAYS:
                    # Score: bliže = bolje
                    score = 0.5 - (days_diff * 0.05)  # Max 0.5, min 0.15
                    if score > best_score:
                        best_score = score
                        best_match = payment

        if best_match:
            return MatchResult(
                success=True,
                payment=best_match,
                confidence=best_score,
                method='AMOUNT_DATE',
                notes=f'Amount match, date within {self.DATE_TOLERANCE_DAYS} days of due date'
            )

        return MatchResult(success=False)

    def _fuzzy_name_match(self, name1: str, name2: str) -> bool:
        """Jednostavan fuzzy match za imena firmi."""
        # Izvuci ključne reči (ignoriši DOO, SZR, etc.)
        stop_words = {'doo', 'szr', 'str', 'ad', 'dd', 'or', 'pr'}

        words1 = set(name1.split()) - stop_words
        words2 = set(name2.split()) - stop_words

        # Ako se bar 50% reči poklapa
        if not words1 or not words2:
            return False

        common = words1 & words2
        return len(common) >= min(len(words1), len(words2)) * 0.5

    def _calculate_match_score(self, txn: BankTransaction, payment: SubscriptionPayment) -> float:
        """Računa ukupni match score za sugestije."""
        score = 0.0

        # Amount match: +0.4
        if abs(payment.total_amount - txn.amount) <= self.AMOUNT_TOLERANCE:
            score += 0.4
        elif abs(payment.total_amount - txn.amount) <= Decimal('100'):
            score += 0.2  # Blizu

        # Reference match: +0.4
        if txn.payment_reference and payment.payment_reference:
            ref1 = re.sub(r'[\s\-]', '', txn.payment_reference)
            ref2 = re.sub(r'[\s\-]', '', payment.payment_reference)
            if ref1 == ref2:
                score += 0.4
            elif ref1 in ref2 or ref2 in ref1:
                score += 0.2

        # Tenant name match: +0.2
        if txn.payer_name:
            tenant = Tenant.query.get(payment.tenant_id)
            if tenant and tenant.name:
                if tenant.name.lower() in txn.payer_name.lower():
                    score += 0.2

        return min(score, 1.0)

    def _get_match_reasons(self, txn: BankTransaction, payment: SubscriptionPayment) -> List[str]:
        """Vraća listu razloga za match (za UI)."""
        reasons = []

        if abs(payment.total_amount - txn.amount) <= self.AMOUNT_TOLERANCE:
            reasons.append('Iznos se poklapa')

        if txn.payment_reference and payment.payment_reference:
            ref1 = re.sub(r'[\s\-]', '', txn.payment_reference)
            ref2 = re.sub(r'[\s\-]', '', payment.payment_reference)
            if ref1 == ref2:
                reasons.append('Poziv na broj se poklapa')

        if txn.payer_name:
            tenant = Tenant.query.get(payment.tenant_id)
            if tenant and tenant.name and tenant.name.lower() in txn.payer_name.lower():
                reasons.append('Ime platioca sadrži ime tenanta')

        return reasons

    def _apply_match(self, txn: BankTransaction, result: MatchResult):
        """Primenjuje match na transakciju."""
        txn.match_status = MatchStatus.MATCHED
        txn.matched_payment_id = result.payment.id
        txn.match_confidence = result.confidence
        txn.match_method = result.method
        txn.match_notes = result.notes
        txn.matched_at = datetime.utcnow()