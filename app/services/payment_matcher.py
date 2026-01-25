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
        """
        Match po tacnom pozivu na broj.

        Podrzava formate:
        - NOVI 18-cifreni: "970001232026000042" -> (123, 2026, 42)
        - Stari 13-cifreni: "9700012300042" -> (123, None, 42)
        - Bank format sa separatorima: normalizuje pre parsiranja

        Matching poredi (tenant_id, seq) - godina se ignorise za backward compat.
        """
        if not txn.payment_reference:
            return MatchResult(success=False)

        from .ips_service import IPSService

        # Parsiraj transakciju u (tenant_id, year, seq) - year moze biti None
        txn_parsed = IPSService.parse_payment_reference(txn.payment_reference)

        # Trazi fakturu sa istim pozivom na broj
        payments = SubscriptionPayment.query.filter(
            SubscriptionPayment.status.in_(['PENDING', 'OVERDUE'])
        ).all()

        for p in payments:
            if not p.payment_reference:
                continue

            # Parsiraj payment reference
            p_parsed = IPSService.parse_payment_reference(p.payment_reference)

            # Ako oba nisu parsabilna, pokusaj direktan string match (normalizovan)
            if txn_parsed is None or p_parsed is None:
                # Fallback na string normalizaciju (ukloni sve osim cifara)
                txn_ref_clean = re.sub(r'\D', '', txn.payment_reference)
                p_ref_clean = re.sub(r'\D', '', p.payment_reference)
                if txn_ref_clean != p_ref_clean:
                    continue
            else:
                # Poredi parsirane tuple-ove: (tenant_id, year, seq)
                # Za EXACT match: tenant_id i seq moraju biti isti
                # Godina se ignorise ako je None u bilo kom od njih (backward compat)
                txn_tenant, txn_year, txn_seq = txn_parsed
                p_tenant, p_year, p_seq = p_parsed

                if txn_tenant != p_tenant or txn_seq != p_seq:
                    continue

                # Ako oba imaju godinu, moraju se poklapati
                if txn_year is not None and p_year is not None and txn_year != p_year:
                    continue

            # Match! Proveri i iznos
            if abs(p.total_amount - txn.amount) <= self.AMOUNT_TOLERANCE:
                return MatchResult(
                    success=True,
                    payment=p,
                    confidence=1.0,
                    method='EXACT_REF',
                    notes=f'Exact reference match: {txn.payment_reference} -> {p.payment_reference}'
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
        """
        Match po delimicnom pozivu na broj.

        Koristi parse_payment_reference() da izvuce tenant_id,
        zatim trazi najnoviju neplacenu fakturu tog tenanta.
        """
        if not txn.payment_reference:
            return MatchResult(success=False)

        from .ips_service import IPSService

        # Parsiraj referencu da dobijis tenant_id - sada vraca 3-tuple
        parsed = IPSService.parse_payment_reference(txn.payment_reference)

        if parsed:
            tenant_id = parsed[0]  # (tenant_id, year, seq) - uzmi samo tenant_id

            # Trazi fakturu tog tenanta
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
        """Racuna ukupni match score za sugestije."""
        from .ips_service import IPSService

        score = 0.0

        # Amount match: +0.4
        if abs(payment.total_amount - txn.amount) <= self.AMOUNT_TOLERANCE:
            score += 0.4
        elif abs(payment.total_amount - txn.amount) <= Decimal('100'):
            score += 0.2  # Blizu

        # Reference match: +0.4 (koristi parsing za oba formata)
        # Sada vraca 3-tuple: (tenant_id, year, seq)
        if txn.payment_reference and payment.payment_reference:
            txn_parsed = IPSService.parse_payment_reference(txn.payment_reference)
            pay_parsed = IPSService.parse_payment_reference(payment.payment_reference)

            if txn_parsed and pay_parsed:
                # Poredi tenant_id i seq (ignorisi godinu za backward compat)
                if txn_parsed[0] == pay_parsed[0] and txn_parsed[2] == pay_parsed[2]:
                    score += 0.4  # Potpuni match (tenant + seq)
                elif txn_parsed[0] == pay_parsed[0]:
                    score += 0.2  # Isti tenant_id

        # Tenant name match: +0.2
        if txn.payer_name:
            tenant = Tenant.query.get(payment.tenant_id)
            if tenant and tenant.name:
                if tenant.name.lower() in txn.payer_name.lower():
                    score += 0.2

        return min(score, 1.0)

    def _get_match_reasons(self, txn: BankTransaction, payment: SubscriptionPayment) -> List[str]:
        """Vraca listu razloga za match (za UI)."""
        from .ips_service import IPSService

        reasons = []

        if abs(payment.total_amount - txn.amount) <= self.AMOUNT_TOLERANCE:
            reasons.append('Iznos se poklapa')

        if txn.payment_reference and payment.payment_reference:
            txn_parsed = IPSService.parse_payment_reference(txn.payment_reference)
            pay_parsed = IPSService.parse_payment_reference(payment.payment_reference)
            # Sada su 3-tuple: (tenant_id, year, seq)
            if txn_parsed and pay_parsed:
                if txn_parsed[0] == pay_parsed[0] and txn_parsed[2] == pay_parsed[2]:
                    reasons.append('Poziv na broj se poklapa')

        if txn.payer_name:
            tenant = Tenant.query.get(payment.tenant_id)
            if tenant and tenant.name and tenant.name.lower() in txn.payer_name.lower():
                reasons.append('Ime platioca sadrzi ime tenanta')

        return reasons

    def _apply_match(self, txn: BankTransaction, result: MatchResult):
        """Primenjuje match na transakciju."""
        txn.match_status = MatchStatus.MATCHED
        txn.matched_payment_id = result.payment.id
        txn.match_confidence = result.confidence
        txn.match_method = result.method
        txn.match_notes = result.notes
        txn.matched_at = datetime.utcnow()